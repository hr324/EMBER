"""Inverse propagation: infer an ORIGIN REGION from thermal detections.

All ranking inputs are observations and explicit physical hypotheses. Never
import incident-origin labels or electricity/lightning evidence in this module.
"""
from __future__ import annotations
import math
from dataclasses import dataclass,replace,asdict
from datetime import timedelta
from .features import cluster_detections,weather_summary
from .graph import SpatialGrid,SpreadParameters,build_grid,with_covariates,build_adjacency,reverse_shortest_paths
from .ingest import parse_utc,observation_gate

@dataclass(frozen=True)
class InferenceOptions:
    """Precommitted, label-independent inference and uncertainty settings."""
    cell_m:float=850.
    margin_km:float=9.
    max_observation_hours:float=10.
    max_clusters:int=10
    max_grid_cells:int=12000
    ignition_lookback_hours:float=12.
    ignition_step_minutes:int=30
    observation_early_grace_hours:float=2.
    observation_late_grace_hours:float=.25
    early_penalty_multiplier:float=.08
    assumed_detection_delay_hours:float=0.
    score_temperature:float=.9
    ensemble:bool=True
    base_speed_mps:float=.4


def _params(options:InferenceOptions,has_weather:bool,variant:str='fusion')->list[SpreadParameters]:
    """Create a small physically interpretable sensitivity ensemble; no label tuning."""
    v=options.base_speed_mps
    base=SpreadParameters(base_speed_mps=v,wind_gain=.9 if (has_weather and variant!='satellite') else 0.,
                          slope_gain=1.5 if variant=='fusion' else 0.,
                          use_fuel=(variant=='fusion'))
    if not options.ensemble:return [base]
    return [base,replace(base,base_speed_mps=v*.72),replace(base,base_speed_mps=v*1.35),
            replace(base,wind_direction_offset_deg=20),replace(base,wind_direction_offset_deg=-20)]


def _loss_at_ignition_time(s:float,travel_times:list[float],obs_hours:list[float],
                            weights:list[float],opt:InferenceOptions)->float:
    """Asymmetric squared-hinge arrival-time mismatch.

    Predicted arrival after detection (late) is strong contradiction; arrival
    long BEFORE observation is weak evidence because overpasses are sparse.
    """
    loss=0.
    for tt,observed,weight in zip(travel_times,obs_hours,weights):
        if not math.isfinite(tt):return math.inf
        error=s+tt-observed+opt.assumed_detection_delay_hours
        late=max(0.,error-opt.observation_late_grace_hours)
        early=max(0.,-error-opt.observation_early_grace_hours)
        loss+=weight*(late*late+opt.early_penalty_multiplier*early*early)
    return loss


def _scenario_losses(grid:SpatialGrid,clusters:list[dict],obs_hours:list[float],
                     weights:list[float],wind:dict|None,
                     params:SpreadParameters,opt:InferenceOptions)->tuple[list[float],list[float],dict]:
    """Reverse shortest paths once per observed cluster; optimise ignition time per node."""
    adjacency,summary=build_adjacency(grid,wind,params)
    targets=[grid.nearest(c['latitude'],c['longitude']) for c in clusters]
    distances=reverse_shortest_paths(adjacency,targets)
    time_steps=round(opt.ignition_lookback_hours*60/opt.ignition_step_minutes)
    ignition_options=[-j*opt.ignition_step_minutes/60. for j in range(time_steps+1)]
    losses=[];times=[]
    for node in range(len(grid.nodes)):
        travel=[d[node] for d in distances]
        candidates=((_loss_at_ignition_time(t,travel,obs_hours,weights,opt),t) for t in ignition_options)
        loss,t=min(candidates)
        losses.append(loss);times.append(t)
    return losses,times,summary


def _soft_score(losses:list[float],temperature:float)->list[float]:
    """Normalise LOSS, NOT a calibrated posterior probability."""
    best=min(losses)
    if not math.isfinite(best):raise ValueError('No reachable candidate ignition cells')
    values=[math.exp(-min(700,(v-best)/temperature)) if math.isfinite(v) else 0. for v in losses]
    z=sum(values)
    return [v/z for v in values]


def _top_mass_region(grid:SpatialGrid,mass:list[float],threshold:float)->dict:
    """Smallest descending-score collection accumulating given NORMALISED MASS."""
    sorted_ids=sorted(range(len(mass)),key=lambda i:mass[i],reverse=True)
    ids=[];total=0.
    for i in sorted_ids:
        ids.append(i);total+=mass[i]
        if total>=threshold:break
    return {'mass_fraction':threshold,'cell_count':len(ids),
            'area_km2':round(len(ids)*grid.cell_m**2/1e6,2),
            'candidate_indices':ids,
            'warning':'Model-relative score mass, not empirically calibrated coverage'}


def infer_origin(detections:list[dict],weather:list[dict]|None=None,
                 options:InferenceOptions|None=None,covariates_csv:str|None=None,
                 variant:str='fusion')->dict:
    """Run a label-independent retrospective reconstruction of plausible origin.

    Variants: satellite (isotropic grid), wind (satellite + stationary wind),
    fusion (wind + optional pre-fire terrain/fuel). If covariates are absent,
    fusion becomes wind-aware, not falsely 'full multimodal'.
    """
    opt=options or InferenceOptions()
    if variant not in ('satellite','wind','fusion'):raise ValueError('Bad variant')
    gate=observation_gate(detections)
    if not detections:raise ValueError('No satellite observations supplied')
    clusters=cluster_detections(detections,max_hours=opt.max_observation_hours,max_clusters=opt.max_clusters)
    if not clusters:raise ValueError('No eligible early clusters')
    grid=build_grid(clusters,opt.cell_m,opt.margin_km,opt.max_grid_cells)
    if covariates_csv and variant=='fusion':with_covariates(grid,covariates_csv)
    first=parse_utc(clusters[0]['timestamp_utc'])
    hours=[(parse_utc(c['timestamp_utc'])-first).total_seconds()/3600. for c in clusters]
    # Every satellite pass gets equal aggregate influence. This reduces
    # pseudo-replication by densely sampled simultaneous pixels.
    pass_counts={}
    for c in clusters:pass_counts[c['pass_id']]=pass_counts.get(c['pass_id'],0)+1
    weights=[max(.2,c['confidence'])/(1.+c['uncertainty_m']/1500.)/pass_counts[c['pass_id']] for c in clusters]
    normalizer=sum(weights);weights=[w/normalizer for w in weights]
    wind=None
    if weather and variant!='satellite':
        wind=weather_summary(weather,first.isoformat().replace('+00:00','Z'),
                 (first+timedelta(hours=opt.max_observation_hours)).isoformat().replace('+00:00','Z'))
    if variant!='satellite' and weather and wind is None:
        raise ValueError('Requested weather but no matching hourly records')
    ensemble=_params(opt,bool(wind),variant)
    all_mass=[];all_times=[];run_metadata=[]
    for params in ensemble:
        scenario_losses,origin_hours,summary=_scenario_losses(grid,clusters,hours,weights,wind,params,opt)
        all_mass.append(_soft_score(scenario_losses,opt.score_temperature))
        all_times.append(origin_hours)
        run_metadata.append(summary)
    combined=[sum(run[i] for run in all_mass)/len(all_mass) for i in range(len(grid.nodes))]
    ranks=sorted(range(len(combined)),key=lambda i:combined[i],reverse=True)
    best_idx=ranks[0];best=grid.nodes[best_idx]
    # Best time is from nominal run; ensemble timing variation remains in metadata.
    best_time=(first+timedelta(hours=all_times[0][best_idx])).isoformat().replace('+00:00','Z')
    region80=_top_mass_region(grid,combined,.8);region90=_top_mass_region(grid,combined,.9)
    baseline_ids=[c for c in clusters if c['pass_id']==clusters[0]['pass_id']]
    centroid={'latitude':sum(c['latitude'] for c in baseline_ids)/len(baseline_ids),
              'longitude':sum(c['longitude'] for c in baseline_ids)/len(baseline_ids)}
    # Only export up to 1500 of the strongest grid cells to keep browser payload lean.
    show=ranks[:1500]
    cells=[{'cell_id':i,'latitude':round(grid.nodes[i].lat,6),
            'longitude':round(grid.nodes[i].lon,6),'score_mass':round(combined[i],10),
            'rank':j+1,'in_top80':i in set(region80['candidate_indices']),
            'in_top90':i in set(region90['candidate_indices'])} for j,i in enumerate(show)]
    summary0=run_metadata[0]
    warnings=list(gate['warnings'])
    if len(set(c['pass_id'] for c in clusters))<2:warnings.append('Selected early evidence contains fewer than two passes: chronology is weak')
    if not wind and variant!='satellite':warnings.append('No weather supplied: isotropic propagation used')
    if variant=='fusion' and summary0['elevation_coverage']<.8:warnings.append('Elevation covariate mostly missing: terrain is neutral')
    if variant=='fusion' and summary0['fuel_coverage']<.8:warnings.append('Historical vegetation covariate mostly missing: fuel is neutral')
    warnings.append('Normalised model score is NOT a calibrated ignition probability; do not infer legal cause')
    return {'status':'ok' if gate['usable'] else 'low_observability',
        'variant':variant,'model':'directed_grid_reverse_dijkstra_asymmetric_arrival_v1',
        'best_origin':{'latitude':best.lat,'longitude':best.lon,
                       'estimated_ignition_utc':best_time,'cell_id':best_idx,
                       'score_mass':combined[best_idx]},
        'baseline_centroid':centroid,
        'clusters':clusters,'observation_gate':gate,
        'candidate_cells':cells,'regions':{'top80':region80,'top90':region90},
        'grid':{'cell_m':grid.cell_m,'nx':grid.nx,'ny':grid.ny,
                'nodes':len(grid.nodes),'margin_km':opt.margin_km,
                'projection':'local equirectangular, incident-scale only'},
        'weather_summary':wind,'graph_summary':summary0,
        'ensemble_count':len(ensemble),
        'scenario_peak_cells':[max(range(len(p)),key=lambda i:p[i]) for p in all_mass],
        'options':asdict(opt),'warnings':warnings,
        'research_notes':{'objective':'one-sided arrival consistency plus weak delayed-observation penalty',
            'interpretation':'hypothesis-ranked origin region; not physical simulator or causal attribution'},
        # Internal compact full ranking used by evaluation; CLI can strip before sharing.
        '_internal':{'mass':combined,'ranks':ranks,'grid_latlon':[(n.lat,n.lon) for n in grid.nodes]}}


def public_result(result:dict)->dict:
    """Remove high-volume internal arrays before writing files / API responses."""
    return {k:v for k,v in result.items() if k!='_internal'}
