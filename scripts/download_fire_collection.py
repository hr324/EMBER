#!/usr/bin/env python3
"""Fetch several documented historical wildfire AOIs for future-hotspot training.

The incident coordinates are used ONLY to delimit API requests. They are not
included in any ML feature, label, or candidate-grid computation.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wildfire.ingest import load_firms, observation_gate

# Source coordinates are publicly listed incident locations, not ML ignition targets.
FIRES = {
    'camp_2018': dict(date='2018-11-08', lat=39.8134, lon=-121.4347, span_lat=.30, span_lon=.42,
                      source='https://www.fire.ca.gov/incidents/2018/11/8/camp-fire'),
    'dixie_2021': dict(date='2021-07-13', lat=39.871306, lon=-121.389439, span_lat=.36, span_lon=.40,
                       source='https://www.fire.ca.gov/incidents/2021/7/13/dixie-fire'),
    'park_2024': dict(date='2024-07-24', lat=39.7789, lon=-121.76168, span_lat=.32, span_lon=.38,
                      source='https://www.fire.ca.gov/incidents/2024/7/24/park-fire'),
    'eaton_2025': dict(date='2025-01-07', lat=34.203483, lon=-118.069155, span_lat=.12, span_lon=.16,
                       source='https://www.fire.ca.gov/incidents/2025/1/7/eaton-fire'),
    'palisades_2025': dict(date='2025-01-07', lat=34.07022, lon=-118.54453, span_lat=.13, span_lon=.19,
                           source='https://www.fire.ca.gov/incidents/2025/1/7/palisades-fire'),
}


def main() -> None:
    """Download FIRMS and historical weather, reporting usable temporal coverage."""
    parser=argparse.ArgumentParser()
    parser.add_argument('--only', nargs='*', choices=sorted(FIRES), default=list(FIRES))
    parser.add_argument('--out', default='data/fire_sequences')
    parser.add_argument('--days',type=int,default=3)
    parser.add_argument('--instrument', default='VIIRS_SNPP_SP')
    args=parser.parse_args()
    if not os.environ.get('NASA_FIRMS_MAP_KEY'):
        raise SystemExit('Set NASA_FIRMS_MAP_KEY in this shell first; do not commit the key.')
    summary={}
    for name in args.only:
        fire=FIRES[name]
        folder=Path(args.out)/name
        folder.mkdir(parents=True,exist_ok=True)
        bbox=','.join(str(n) for n in (fire['lon']-fire['span_lon'],fire['lat']-fire['span_lat'],
                 fire['lon']+fire['span_lon'],fire['lat']+fire['span_lat']))
        firm=folder/'firms.csv'
        weather=folder/'weather.json'
        if not firm.exists():
            command=[sys.executable,str(ROOT/'scripts/download_data.py'),
                      '--source','firms','--date',fire['date'],'--days',str(args.days),
                      '--instrument',args.instrument,f'--bbox={bbox}','--out',str(firm)]
            if subprocess.run(command).returncode:
                summary[name]={'error':'NASA download failed'}
                continue
        observations=load_firms(firm)
        gate=observation_gate(observations)
        # Weather position is selected from FIRST observed detections, not
        # the incident coordinate or future observations.
        if observations and not weather.exists():
            first_time=observations[0]['observed_utc']
            first=[p for p in observations if p['observed_utc']==first_time]
            latitude=sum(p['latitude'] for p in first)/len(first)
            longitude=sum(p['longitude'] for p in first)/len(first)
            command=[sys.executable,str(ROOT/'scripts/download_data.py'),
                     '--source','weather','--date',fire['date'],'--days',str(args.days),
                     '--lat',str(latitude),'--lon',str(longitude),'--out',str(weather)]
            subprocess.run(command)
        (folder/'source.json').write_text(json.dumps({'incident':name,'source':fire['source'],
           'bounding_box':bbox,'note':'AOI is for archive retrieval only; never used as model features or labels.'},indent=2))
        summary[name]={**gate,'weather_downloaded':weather.exists()}
        print(name,json.dumps(summary[name]),flush=True)
    print('SUMMARY',json.dumps(summary,indent=2),flush=True)
    print('IMPORTANT: Visually check that each bounding box captures one fire rather than unrelated hotspots.')

if __name__=='__main__':main()
