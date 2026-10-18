#!/usr/bin/env python3
"""Optional remote acquisition; run on a networked machine with FIRMS MAP_KEY.

Uses only stdlib. NASA historical API access can be limited; if unavailable,
obtain the 2018 archive CSV manually and run 'fireforensics ingest'. Never
substitute current wildfire observations for the historical incident.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.parse import urlencode


def download(url:str,out:Path)->None:
    """Download with explicit HTTP failure and filename, without printing API keys."""
    req=Request(url,headers={'User-Agent':'WildfireForensics-Research/0.1'})
    with urlopen(req,timeout=65) as r:
        payload=r.read()
        if r.status!=200:raise RuntimeError(f'HTTP {r.status}')
    if not payload:raise RuntimeError('Empty API response')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(payload)
    print(f'Saved {out} ({len(payload)} bytes)')


def main()->int:
    """Get 2018 FIRMS or Open-Meteo data by explicitly selected source."""
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True,choices=['firms','weather'])
    p.add_argument('--out',required=True)
    p.add_argument('--date',default='2018-11-08')
    p.add_argument('--days',type=int,default=3)
    p.add_argument('--bbox',default='-121.85,39.55,-121.20,40.05')
    p.add_argument('--instrument',default='VIIRS_SNPP_SP')
    p.add_argument('--lat',type=float,help='Weather point derived from observed hotspots, NOT known ignition')
    p.add_argument('--lon',type=float,help='Weather point derived from observed hotspots, NOT known ignition')
    a=p.parse_args()
    if a.source=='firms':
        key=os.environ.get('NASA_FIRMS_MAP_KEY')
        if not key: p.error('Set NASA_FIRMS_MAP_KEY or manually export NASA archive CSV')
        if not 1<=a.days<=5: p.error('FIRMS area API day count 1..5')
        url=f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{a.instrument}/{a.bbox}/{a.days}/{a.date}'
    else:
        if a.lat is None or a.lon is None:p.error('--lat and --lon required; derive them from detections')
        from datetime import date,timedelta
        start=date.fromisoformat(a.date)
        params={'latitude':a.lat,'longitude':a.lon,'start_date':start.isoformat(),
                'end_date':(start+timedelta(days=a.days-1)).isoformat(),
                'hourly':'wind_speed_10m,wind_direction_10m,relative_humidity_2m,temperature_2m',
                'wind_speed_unit':'ms','timezone':'UTC'}
        url='https://archive-api.open-meteo.com/v1/archive?'+urlencode(params)
    try:download(url,Path(a.out))
    except Exception as exc:
        print(f'Download failed: {type(exc).__name__}: {str(exc).replace(os.environ.get("NASA_FIRMS_MAP_KEY") or "NEVERMATCHKEY", "[REDACTED]")}',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
