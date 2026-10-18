#!/usr/bin/env python3
"""Fast geographic and temporal checks before approving training fire sequences.

Spatial anomalies are review flags, not definitive evidence of bad data: major
fires can grow tens of km and have multiple fronts/spot fires. Human approval
is necessary before including newly discovered cases in ML training.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from wildfire.ingest import load_firms,load_weather
from wildfire.geo import haversine_km
from gnn_forecast import get_passes


def audit_case(folder: Path) -> dict:
    """Report early hotspot coverage, gaps, region width and source provenance."""
    path=folder/'firms.csv'
    if not path.exists():return {'status':'rejected','warnings':['missing firms.csv']}
    try:observations=load_firms(path)
    except Exception as exc:return {'status':'rejected','warnings':[f'Invalid FIRMS: {exc}']}
    passes=get_passes(observations)
    warnings=[]
    if len(passes)<3:warnings.append('fewer than three independent satellite passes')
    if len(observations)<50:warnings.append('fewer than 50 satellite detections')
    weatherfile=folder/'weather.json'
    weather=load_weather(weatherfile) if weatherfile.exists() else []
    if not weather:warnings.append('no usable hourly wind observations')
    maximum=0.0
    if passes:
        first=passes[0]
        lat=sum(r['latitude'] for r in first)/len(first)
        lon=sum(r['longitude'] for r in first)/len(first)
        maximum=max(haversine_km(lat,lon,r['latitude'],r['longitude']) for r in observations)
        if maximum>45:warnings.append('detections extend >45km from first pass; review for different incidents')
    source={}
    if (folder/'source.json').exists():
        try:source=json.loads((folder/'source.json').read_text())
        except json.JSONDecodeError: warnings.append('invalid source metadata')
    if 'provisional' in str(source.get('data_quality','')).lower():
        warnings.append('EONET event identification is PROVISIONAL; manual region check required')
    return {'status':'review_required' if warnings else 'candidate',
            'observations':len(observations),'passes':len(passes),'max_extent_km':round(maximum,1),
            'weather_records':len(weather),'source':source.get('source','unspecified'),
            'warnings':warnings}


def main():
    """Write a human-readable audit and an initial manifest of existing fires."""
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',default='data/fire_sequences')
    parser.add_argument('--output',default='artifacts/fire_quality_audit.json')
    args=parser.parse_args()
    folders=sorted(p for p in Path(args.data).iterdir() if p.is_dir())
    audit={p.name:audit_case(p) for p in folders}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(audit,indent=2))
    for name,info in audit.items():
        print(f"{name:40} {info['status']:15} passes={info.get('passes',0):2} detections={info.get('observations',0):5}")
        for warning in info.get('warnings',[]):print('  !',warning)
    print('Saved',output)
    print('Only put manually verified case folder names into approved_fires.txt before retraining.')


if __name__=='__main__':main()
