#!/usr/bin/env python3
"""Discover candidate US West wildfires from NASA EONET, acquire FIRMS and weather.

This is a QC-first downloader, NOT a claim that each EONET event is a clean
single-fire training case. Only accepted cases enter GNN training. Event
coordinates and dates select archive downloads; they are never model inputs.
No access key is written to the repository or printed in normal logs.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from wildfire.ingest import load_firms, observation_gate
from wildfire.geo import haversine_km

EONET = 'https://eonet.gsfc.nasa.gov/api/v3/events'


def retrieve_events(year: int) -> list[dict]:
    """Read archived EONET wildfires for one calendar year (official NASA API)."""
    query = urlencode(dict(category='wildfires', status='closed',
                           start=f'{year}-01-01', end=f'{year}-12-31', limit=10000))
    request = Request(EONET+'?'+query, headers={'User-Agent':'EMBER-Research/1.0'})
    with urlopen(request, timeout=50) as response:
        document = json.load(response)
    return document.get('events', [])


def event_candidate(event: dict, west: float, south: float, east: float, north: float):
    """Take first recorded EONET point; reject polygons and out-of-area events."""
    points=[]
    for geo in event.get('geometry') or []:
        coords=geo.get('coordinates')
        if geo.get('type')!='Point' or not isinstance(coords,list) or len(coords)<2: continue
        try:
            lon,lat = float(coords[0]), float(coords[1])
            t = str(geo['date'])[:10]
            datetime.strptime(t,'%Y-%m-%d')
            if west <= lon <= east and south <= lat <= north:
                points.append((t,lat,lon))
        except (ValueError,TypeError,KeyError): continue
    if not points: return None
    date,lat,lon=min(points)
    event_id=str(event.get('id') or '')
    slug=re.sub(r'[^a-z0-9]+','_', str(event.get('title') or event_id).lower()).strip('_')[:36]
    slug=re.sub(r'_fire$','',slug)
    return dict(name=f'eonet_{date[:4]}_{slug}_{re.sub(r"[^a-z0-9]", "", event_id.lower())[-8:]}',
                title=event.get('title',''), date=date, lat=lat, lon=lon,
                event_id=event_id, source=event.get('link') or EONET,
                sources=event.get('sources',[]))


def nearby_duplicate(item: dict, already: list[dict], radius_km: float) -> bool:
    """Avoid selecting overlapping events that could duplicate a fire incident."""
    for prev in already:
        gap=abs((datetime.fromisoformat(item['date'])-datetime.fromisoformat(prev['date'])).days)
        if gap<=7 and haversine_km(item['lat'],item['lon'],prev['lat'],prev['lon'])<2.5*radius_km:
            return True
    return False


def archive_bbox(item: dict, radius_km: float) -> str:
    """Convert an approximate kilometre radius to a small bounding box."""
    lat_delta=radius_km/111.2
    lon_delta=radius_km/(111.2*max(0.3,math.cos(math.radians(item['lat']))))
    return ','.join(f'{x:.5f}' for x in (item['lon']-lon_delta,item['lat']-lat_delta,
                                         item['lon']+lon_delta,item['lat']+lat_delta))


def call_download(params: list[str]) -> bool:
    """Use existing acquisition script, which redacts a leaked API key on error."""
    command=[sys.executable,str(ROOT/'scripts/download_data.py')]+params
    return subprocess.run(command,check=False).returncode==0


def download_candidate(item: dict, args) -> dict:
    """Download and quality-gate one event; quarantine datasets that don't qualify."""
    directory=Path(args.out)/item['name']
    directory.mkdir(parents=True,exist_ok=True)
    bbox=archive_bbox(item,args.radius_km)
    firms=directory/'firms.csv';weather=directory/'weather.json'
    if not firms.exists():
        ok=call_download(['--source','firms','--date',item['date'],'--days',str(args.days),
                          '--instrument',args.instrument,f'--bbox={bbox}','--out',str(firms)])
        if not ok: return {'status':'rejected','reason':'FIRMS download failed'}
    try:
        observations=load_firms(firms)
    except Exception as exc:
        return {'status':'rejected','reason':f'invalid FIRMS CSV: {type(exc).__name__}'}
    gate=observation_gate(observations)
    result={'status':'rejected','detections':gate['detections'],'passes':gate['passes'],
            'first_utc':gate.get('first_utc'),'source':item['source']}
    if gate['detections']<args.min_detections or gate['passes']<args.min_passes:
        result['reason']='insufficient observations / independent passes'
        return result
    # Reject events if their earliest observations are far from EONET's area of interest.
    # This is a plausibility check, not proof of single-fire membership.
    first_time=observations[0]['observed_utc']
    early=[r for r in observations if r['observed_utc']==first_time]
    alat=sum(r['latitude'] for r in early)/len(early)
    alon=sum(r['longitude'] for r in early)/len(early)
    result['initial_centroid_distance_km']=round(haversine_km(alat,alon,item['lat'],item['lon']),2)
    if result['initial_centroid_distance_km']>args.radius_km*0.9:
        result['reason']='first observations far from EONET event location (possible unrelated hotspot)'
        return result
    if not weather.exists():
        ok=call_download(['--source','weather','--date',item['date'],'--days',str(args.days),
                          '--lat',str(alat),'--lon',str(alon),'--out',str(weather)])
        if not ok:return {**result,'reason':'weather download failed'}
    # Raw data provenance and unresolved membership concerns are explicit.
    metadata={**item,'bbox':bbox,'instrument':args.instrument,'event_location_only_for_download':True,
              'data_quality':'provisional: visually inspect for other fires; EONET event date is not precise ignition',
              'historical_weather_sample':[alat,alon],'gate':gate}
    (directory/'source.json').write_text(json.dumps(metadata,indent=2))
    return {**result,'status':'accepted_provisional','reason':'passes and centroid checks passed; spatial review still required',
            'weather_downloaded':True}


def main():
    """Discover, download, and explicitly audit candidate training fire sequences."""
    parser=argparse.ArgumentParser(description='Discover + quality check extra historical fires')
    parser.add_argument('--years',nargs='+',type=int,default=[2020,2021,2022,2023,2024,2025])
    parser.add_argument('--bbox',default='-125,32,-114,42',help='West,south,east,north; US West')
    parser.add_argument('--discover-only',action='store_true')
    parser.add_argument('--max-new',type=int,default=25)
    parser.add_argument('--max-candidates',type=int,default=80)
    parser.add_argument('--out',default='data/fire_sequences')
    parser.add_argument('--radius-km',type=float,default=25)
    parser.add_argument('--days',type=int,default=3)
    parser.add_argument('--min-passes',type=int,default=3)
    parser.add_argument('--min-detections',type=int,default=50)
    parser.add_argument('--instrument',default='VIIRS_SNPP_SP')
    args=parser.parse_args()
    try: west,south,east,north=map(float,args.bbox.split(','))
    except ValueError:parser.error('bbox must contain west,south,east,north')
    if not (-180<west<east<180 and -90<south<north<90):parser.error('invalid bbox')
    if not 1<=args.days<=5:parser.error('--days must be 1..5 for FIRMS')
    if not args.discover_only and not os.environ.get('NASA_FIRMS_MAP_KEY'):
        parser.error('Set NASA_FIRMS_MAP_KEY in this shell; never put it in code or the command line.')
    found=[]
    for year in args.years:
        try:
            for event in retrieve_events(year):
                item=event_candidate(event,west,south,east,north)
                if item:found.append(item)
            print(f'EONET {year}: {len(found)} cumulative in area',flush=True)
        except Exception as exc:
            print(f'EONET {year} unavailable: {type(exc).__name__}: {exc}',file=sys.stderr)
    # Round-robin across years, so an early year cannot consume every request.
    by_year={year:sorted((e for e in found if int(e['date'][:4])==year),
                         key=lambda e:(e['date'],e['name'])) for year in args.years}
    interleaved=[]
    while any(by_year.values()):
        for year in args.years:
            if by_year[year]: interleaved.append(by_year[year].pop(0))
    unique=[]
    for item in interleaved:
        if not nearby_duplicate(item,unique,args.radius_km): unique.append(item)
    unique=unique[:args.max_candidates]
    report={'discovered_in_area':len(found),'after_nearby_dedup':len(unique),
            'accepted_provisional':[], 'rejected':{}, 'candidates':unique}
    if args.discover_only:
        print(json.dumps(report,indent=2));return
    for item in unique:
        if len(report['accepted_provisional'])>=args.max_new:break
        status=download_candidate(item,args)
        if status['status']=='accepted_provisional':report['accepted_provisional'].append(item['name'])
        else:report['rejected'][item['name']]=status
        print(item['name'],json.dumps(status),flush=True)
    output=Path(args.out)/'expansion_report.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2))
    print('SUMMARY',json.dumps({'accepted_provisional':report['accepted_provisional'],
           'accepted_count':len(report['accepted_provisional']),
           'rejected_count':len(report['rejected']),'report':str(output)},indent=2))
    print('All newly accepted fires are PROVISIONAL until manually checked against unrelated hotspots.')


if __name__=='__main__':main()
