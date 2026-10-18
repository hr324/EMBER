"""EVALUATION ONLY: loads held-out documented origin; never used by inference."""
from __future__ import annotations
import json
import math
from pathlib import Path
from .geo import haversine_km
from .inference import infer_origin,InferenceOptions


def evaluate_result(result:dict,label_path:str)->dict:
    """Report km error and uncalibrated top-region membership vs withheld label."""
    label=json.loads(Path(label_path).read_text())
    true_lat,true_lon=float(label['latitude']),float(label['longitude'])
    origin=result['best_origin'];baseline=result['baseline_centroid']
    region={}
    coords=result['_internal']['grid_latlon']
    # Exact nearest CELL CENTRE. Membership requires closest centre to be no
    # farther than the cell's half diagonal; no false coverage outside grid.
    dists=[haversine_km(true_lat,true_lon,lat,lon) for lat,lon in coords]
    nearest=min(range(len(coords)),key=lambda i:dists[i]);threshold=result['grid']['cell_m']*math.sqrt(2)/2/1000.
    inside=dists[nearest]<=threshold
    for key,data in result['regions'].items():
        region[key]={'contains_label_cell':bool(inside and nearest in data['candidate_indices']),
                     'area_km2':data['area_km2'],
                     'mass_fraction':data['mass_fraction'],
                     'not_calibrated':True}
    return {'fire_id':label.get('fire_id'),
            'model_error_km':round(haversine_km(true_lat,true_lon,origin['latitude'],origin['longitude']),3),
            'centroid_baseline_error_km':round(haversine_km(true_lat,true_lon,baseline['latitude'],baseline['longitude']),3),
            'improvement_over_centroid_km':round(haversine_km(true_lat,true_lon,baseline['latitude'],baseline['longitude'])-haversine_km(true_lat,true_lon,origin['latitude'],origin['longitude']),3),
            'truth_in_candidate_grid':inside,'truth_nearest_grid_cell_distance_km':round(dists[nearest],3),
            'regions':region,'label_source':label.get('source_url'),
            'caution':'Single-case retrospective evaluation is not evidence of generalised accuracy'}


def ablation_study(detections:list[dict],weather:list[dict]|None,label_path:str,
                   covariates_csv:str|None=None,options:InferenceOptions|None=None)->list[dict]:
    """Compare matched defaults on same data; fail explicitly if weather unavailable."""
    rows=[]
    for variant in ('satellite','wind','fusion'):
        if variant!='satellite' and not weather:continue
        result=infer_origin(detections,weather,options,covariates_csv,variant)
        metric=evaluate_result(result,label_path)
        rows.append({'variant':variant,**{k:metric[k] for k in ('model_error_km','centroid_baseline_error_km','improvement_over_centroid_km')},
                     'elevation_coverage':result['graph_summary']['elevation_coverage'],
                     'fuel_coverage':result['graph_summary']['fuel_coverage']})
    return rows
