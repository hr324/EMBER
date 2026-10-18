"""Optional power-line / lightning hypothesis graph; NEVER influences ranking.

Geometry proximity is an association, not evidence of ignition or liability.
HIFLD lines may omit distribution lines and not represent infrastructure in 2018.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
from .geo import LocalProjection,segment_distance_m
from .ingest import parse_utc


def _geometries(obj:dict):
    """Yield valid LineString components from (Multi)LineString GeoJSON."""
    if obj['type']=='LineString':yield obj['coordinates']
    elif obj['type']=='MultiLineString':yield from obj['coordinates']


def powerline_hypotheses(best_origin:dict,geojson_file:str|Path,max_distance_m:float=5000)->list[dict]:
    """Locate nearby *mapped* lines; current geometry does not establish 2018 state."""
    lat,lon=best_origin['latitude'],best_origin['longitude']
    p=LocalProjection(lat,lon);data=json.loads(Path(geojson_file).read_text())
    if data.get('type')!='FeatureCollection':raise ValueError('Expected GeoJSON FeatureCollection')
    records=[]
    for idx,feature in enumerate(data['features']):
        distances=[]
        for line in _geometries(feature.get('geometry') or {}):
            points=[p.xy(float(q[1]),float(q[0])) for q in line]
            for (ax,ay),(bx,by) in zip(points,points[1:]):
                distances.append(segment_distance_m(0.,0.,ax,ay,bx,by))
        if not distances:continue
        d=min(distances)
        if d<=max_distance_m:
            props=feature.get('properties') or {}
            records.append({'id':f'line-{idx}','type':'powerline',
                'distance_m':round(d,1),'description':str(props.get('NAME') or props.get('name') or props.get('ID') or 'Mapped transmission line'),
                'evidence_level':'spatial association only',
                'historical_warning':'geometry may not represent smaller distribution lines or the historic fire date'})
    return sorted(records,key=lambda r:r['distance_m'])[:20]


def lightning_hypotheses(best_origin:dict,lightning_csv:str|Path,
                         prior_hours:float=48,max_distance_km:float=25)->list[dict]:
    """Find records spatially and temporally near inferred ignition (not proof)."""
    from .geo import haversine_km
    when=parse_utc(best_origin['estimated_ignition_utc']);rows=[]
    with open(lightning_csv,newline='',encoding='utf-8-sig') as f:
        for idx,r in enumerate(csv.DictReader(f)):
            try:
                lat=float(r['latitude']);lon=float(r['longitude'])
                t=parse_utc(r['timestamp_utc']);delta=(when-t).total_seconds()/3600
                dist=haversine_km(lat,lon,best_origin['latitude'],best_origin['longitude'])
                if 0<=delta<=prior_hours and dist<=max_distance_km:
                    rows.append({'id':f'lightning-{idx}','type':'lightning',
                       'distance_km':round(dist,2),'hours_before_model_ignition':round(delta,2),
                       'timestamp_utc':r['timestamp_utc'],
                       'evidence_level':'space/time association only',
                       'historical_warning':'large lightning footprints cannot pinpoint ignition'})
            except (ValueError,KeyError):continue
    return sorted(rows,key=lambda r:(r['distance_km'],r['hours_before_model_ignition']))[:20]


def build_evidence_graph(result:dict,powerline_path:str|None=None,lightning_path:str|None=None)->dict:
    """Create lightweight heterogeneous entity/relation payload for UI / graph DB."""
    best=result['best_origin'];origin_id=f"candidate:{best['cell_id']}"
    nodes=[{'id':origin_id,'kind':'candidate_origin','lat':best['latitude'],'lon':best['longitude']}]
    edges=[]
    for c in result['clusters']:
        node_id='hotspot:'+c['cluster_id']
        nodes.append({'id':node_id,'kind':'satellite_cluster','lat':c['latitude'],'lon':c['longitude'],
                      'timestamp_utc':c['timestamp_utc'],'pixels':c['n_pixels']})
        edges.append({'source':origin_id,'target':node_id,'type':'EXPLAINS_ARRIVAL',
                      'evidence_status':'modelled, not observed fire pathway'})
    if powerline_path:
        for e in powerline_hypotheses(best,powerline_path):
            nodes.append({'id':e['id'],'kind':'powerline','properties':e})
            edges.append({'source':e['id'],'target':origin_id,'type':'NEAR_CANDIDATE',
                          'evidence_status':'association only'})
    if lightning_path:
        for e in lightning_hypotheses(best,lightning_path):
            nodes.append({'id':e['id'],'kind':'lightning','properties':e})
            edges.append({'source':e['id'],'target':origin_id,'type':'PRECEDES_AND_NEAR',
                          'evidence_status':'association only'})
    return {'nodes':nodes,'edges':edges,'metadata':{'candidate_ranking_is_independent_of_hypothesis_edges':True,
        'causal_attribution':False,'graph_ready_for_turingdb_import':True}}
