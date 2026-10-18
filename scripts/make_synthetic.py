#!/usr/bin/env python3
"""SYNTHETIC fixture: never call these observations NASA/CAL FIRE data."""
from __future__ import annotations
import csv
import json
import math
import random
from datetime import datetime,timedelta,timezone
from pathlib import Path


def main()->None:
    """Generate a deterministic, visually demonstrable, labelled toy fire."""
    out=Path('data/synthetic');out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(2026)
    origin=(39.86,-121.52)  # INVENTED; not official Camp Fire origin
    fire_start=datetime(2018,11,8,11,0,tzinfo=timezone.utc)
    # Three stylised satellite overpasses looking at moving spread-fronts.
    records=[]
    for hour,dx_km in ((2,2.3),(4,5.3),(6,8.3),(8,11.0)):
        for idx in range(5):
            along=dx_km+(idx-2)*0.32+rng.uniform(-.15,.15)
            lateral=(idx-2)*.3+rng.uniform(-.12,.12)
            lat=origin[0]+lateral/111.2
            lon=origin[1]+along/(111.2*math.cos(math.radians(origin[0])))
            t=fire_start+timedelta(hours=hour,minutes=rng.choice([1,2,3,4]))
            records.append({'latitude':round(lat,6),'longitude':round(lon,6),
                'acq_date':t.date().isoformat(),'acq_time':t.strftime('%H%M'),
                'satellite':'S-NPP','instrument':'VIIRS','confidence':'n','scan':.375,'track':.375,
                'frp':round(10+rng.random()*80,2)})
    with open(out/'toy_firms.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    hours=[fire_start+timedelta(hours=h) for h in range(0,18)]
    weather={'hourly':{'time':[h.strftime('%Y-%m-%dT%H:%M') for h in hours],
        'wind_speed_10m':[7.2]*len(hours),'wind_direction_10m':[270.]*len(hours),
        'relative_humidity_2m':[22.]*len(hours)},
        'hourly_units':{'wind_speed_10m':'m/s','wind_direction_10m':'°','relative_humidity_2m':'%'}}
    (out/'toy_weather.json').write_text(json.dumps(weather,indent=2))
    # Fake infrastructure geometry deliberately nearby; no historical claim.
    wire={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'NAME':'FICTIONAL demonstration line'},
          'geometry':{'type':'LineString','coordinates':[[origin[1]-.015,origin[0]-.02],
                     [origin[1]+.01,origin[0]+.03]]}}]}
    (out/'toy_powerlines.geojson').write_text(json.dumps(wire,indent=2))
    with open(out/'toy_lightning.csv','w',newline='') as f:
        w=csv.writer(f);w.writerow(['latitude','longitude','timestamp_utc']);
        w.writerow([origin[0]+.01,origin[1]+.01,(fire_start-timedelta(hours=3)).isoformat()])
    (out/'toy_reference.json').write_text(json.dumps({'fire_id':'SYNTHETIC_TOY_FIRE',
                'latitude':origin[0],'longitude':origin[1],
                'source_url':'SYNTHETIC_GENERATOR_ONLY'},indent=2))
    (out/'DISCLAIMER.md').write_text('**SYNTHETIC, NOT HISTORICAL.** All observations, weather, infrastructure and lightning in this directory were fabricated for software demonstration and unit tests. Do not report toy evaluation as real validation.\n')
    print('Created fictional demo data in data/synthetic')

if __name__=='__main__':main()
