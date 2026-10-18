"""Graph-DB-ready, typed graph of propagating spatial cells and linked evidence.

Crucial separation: physical PROPAGATES_TO is an inferred transport edge.
NEAR_POWERLINE and NEAR_LIGHTNING are mere spatial/temporal associations.
No infrastructure edge changes reverse-Dijkstra rankings in this MVP.
"""
from __future__ import annotations
from collections import defaultdict
from .geo import LocalProjection
from .graph import build_grid,with_covariates,build_adjacency,SpreadParameters
from .evidence import powerline_hypotheses,lightning_hypotheses


def build_heterograph(inference:dict,*,covariates_csv:str|None=None,
                      powerlines_path:str|None=None,lightning_path:str|None=None,
                      max_ranked:int=80)->dict:
    """Create typed candidate-grid + observation + evidence relationships.

    Select the first max_ranked cells and their neighbours to keep graph export
    compact. Cell indexes, grid settings, and nominal wind match inference.
    """
    opt=inference['options']
    grid=build_grid(inference['clusters'],opt['cell_m'],opt['margin_km'],opt['max_grid_cells'])
    if covariates_csv and inference['variant']=='fusion':with_covariates(grid,covariates_csv)
    nominal=SpreadParameters(base_speed_mps=opt['base_speed_mps'],
        wind_gain=.9 if inference.get('weather_summary') and inference['variant']!='satellite' else 0.,
        slope_gain=1.5 if inference['variant']=='fusion' else 0.,
        use_fuel=inference['variant']=='fusion')
    adj,_=build_adjacency(grid,inference.get('weather_summary'),nominal)
    top_cells=[c['cell_id'] for c in inference['candidate_cells'][:max_ranked]]
    selected=set(top_cells)
    for i in top_cells:
        selected.update(j for j,_ in adj[i])
    for c in inference['clusters']:
        selected.add(grid.nearest(c['latitude'],c['longitude']))
    nodes=[];edges=[]
    scores={c['cell_id']:c for c in inference['candidate_cells']}
    for i in sorted(selected):
        n=grid.nodes[i];s=scores.get(i,{})
        nodes.append({'id':f'cell:{i}','label':'SPATIAL_CELL',
           'properties':{'latitude':n.lat,'longitude':n.lon,'score_mass':s.get('score_mass'),
                         'rank':s.get('rank'),'elevation_m':n.elevation_m,'fuel_factor':n.fuel_factor}})
    for i in sorted(selected):
        for j,cost in adj[i]:
            if j in selected:
                edges.append({'source':f'cell:{i}','target':f'cell:{j}',
                              'relation':'PROPAGATES_TO',
                              'properties':{'model_travel_hours':round(cost,5),
                                  'hypothesis_type':'transport model, not observed spread'}})
    for c in inference['clusters']:
        node_id='hotspot:'+c['cluster_id']
        nodes.append({'id':node_id,'label':'THERMAL_OBSERVATION','properties':c})
        target=grid.nearest(c['latitude'],c['longitude'])
        edges.append({'source':node_id,'target':f'cell:{target}',
                      'relation':'OBSERVED_AT','properties':{'uncertainty_m':c['uncertainty_m'],
                                        'instrument':c['instrument']}})
    # Include all candidate-to-evidence links only if the geometry is available.
    # These associations remain a different edge type from transport costs.
    candidate_count=0
    for i in top_cells[:15]:
        cell=grid.nodes[i]
        candidate={'latitude':cell.lat,'longitude':cell.lon,
                   'estimated_ignition_utc':inference['best_origin']['estimated_ignition_utc']}
        if powerlines_path:
            for line in powerline_hypotheses(candidate,powerlines_path,3500)[:8]:
                source='infrastructure:'+line['id']
                if not any(n['id']==source for n in nodes):
                    nodes.append({'id':source,'label':'INFRASTRUCTURE',
                                  'properties':{'description':line['description'],
                                                'date_status':'not verified historic'}})
                edges.append({'source':source,'target':f'cell:{i}',
                              'relation':'NEAR_POWERLINE',
                              'properties':{'distance_m':line['distance_m'],
                                  'association_only':True}})
                candidate_count+=1
        if lightning_path:
            for strike in lightning_hypotheses(candidate,lightning_path,48,25)[:8]:
                source='lightning:'+strike['id']
                if not any(n['id']==source for n in nodes):
                    nodes.append({'id':source,'label':'LIGHTNING_EVENT','properties':strike})
                edges.append({'source':source,'target':f'cell:{i}',
                              'relation':'NEAR_LIGHTNING',
                              'properties':{'distance_km':strike['distance_km'],
                                  'hours_before_nominal_ignition':strike['hours_before_model_ignition'],
                                  'association_only':True,
                                  'warning':'uses shared nominal inferred ignition time'}})
    return {'nodes':nodes,'edges':edges,'metadata':{
        'inference_model':inference['model'],
        'typed_edges':sorted(set(e['relation'] for e in edges)),
        'infrastructure_is_explanatory_not_part_of_origin_ranking':True,
        'graph_is_nominal_parameter_snapshot':True,
        'selected_top_ranked':len(top_cells),
        'data_provenance':'See separate CLI manifest and individual input datasets'}}
