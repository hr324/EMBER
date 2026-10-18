"""Canonical NASA FIRMS and Open-Meteo ingest. No inference label access."""
from __future__ import annotations
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from .geo import haversine_km


def parse_utc(value: str) -> datetime:
    """Parse timezone-aware ISO string and normalize to UTC."""
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError(f'UTC offset required for timestamp: {value!r}')
    return dt.astimezone(timezone.utc)


def datetime_utc(date: str, hhmm: str) -> str:
    """Normalize NASA acquisition date and zero-padded HHMM to UTC ISO8601."""
    t = str(hhmm).split('.')[0].zfill(4)
    if len(t) != 4 or not t.isdigit() or int(t[:2]) > 23 or int(t[2:]) > 59:
        raise ValueError(f'Bad FIRMS acq_time {hhmm!r}')
    return f'{date}T{t[:2]}:{t[2:]}:00Z'


def _confidence(value: object, instrument: str) -> float:
    """Map confidence into a coarse relative weight without claiming calibration."""
    value = str(value).strip().lower()
    if value in ('h','high'): return 1.0
    if value in ('n','nominal'): return 0.75
    if value in ('l','low'): return 0.35
    try: return max(.1, min(1., float(value)/100.))
    except (ValueError, TypeError): return .6


def load_firms(path: str | Path, bbox: list[float] | None = None,
               start_utc: str | None = None, end_utc: str | None = None,
               source: str | None = None) -> list[dict]:
    """Read mixed VIIRS/MODIS NASA-style CSV into sorted canonical observations.

    Important: instrument centroids are not ignition points and detections in a
    bounding box are not guaranteed to belong to one incident.
    """
    result, seen = [], set()
    with open(path, newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {'latitude','longitude'}.issubset(reader.fieldnames):
            raise ValueError('FIRMS CSV must contain latitude and longitude')
        for index, row in enumerate(reader):
            try:
                lat, lon = float(row['latitude']), float(row['longitude'])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): continue
                if bbox and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]): continue
                ts = row.get('observed_utc') or datetime_utc(row['acq_date'], row['acq_time'])
                dtime = parse_utc(ts)
                if start_utc and dtime < parse_utc(start_utc): continue
                if end_utc and dtime > parse_utc(end_utc): continue
                instrument = row.get('instrument') or source or 'unknown'
                key = (round(lat,6), round(lon,6), dtime.isoformat(), instrument)
                if key in seen: continue
                seen.add(key)
                frp = float(row.get('frp') or 0)
                scan = float(row.get('scan') or 0.375)
                track = float(row.get('track') or 0.375)
                # FIRMS scan / track widths are in kilometres.
                result.append({'detection_id': f'{Path(path).stem}-{index}',
                    'latitude': lat, 'longitude': lon, 'observed_utc': dtime.isoformat().replace('+00:00','Z'),
                    'frp': max(0,frp), 'confidence': _confidence(row.get('confidence','n'), instrument),
                    'instrument': instrument, 'source': row.get('satellite') or source or 'NASA FIRMS',
                    'scan_m': max(100, scan*1000), 'track_m': max(100,track*1000)})
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
    return sorted(result, key=lambda r: r['observed_utc'])


def load_weather(path: str | Path) -> list[dict]:
    """Read Open-Meteo archive JSON or normalized weather CSV into hourly records.

    Open-Meteo direction is where the wind COMES FROM; graph speed uses where
    it BLOWS TO (plus 180 degrees). Units are converted to m/s.
    """
    path = Path(path)
    if path.suffix.lower() == '.json':
        payload = json.loads(path.read_text())
        if 'hourly' not in payload: raise ValueError('Missing hourly field in Open-Meteo JSON')
        hourly = payload['hourly']
        units = payload.get('hourly_units',{})
        speed_unit = units.get('wind_speed_10m','km/h')
        rows = [dict(timestamp_utc=t,
                     wind_speed=hourly.get('wind_speed_10m',[None]*len(hourly['time']))[i],
                     wind_direction=hourly.get('wind_direction_10m',[None]*len(hourly['time']))[i],
                     relative_humidity=hourly.get('relative_humidity_2m',[None]*len(hourly['time']))[i],
                     speed_unit=speed_unit)
                for i,t in enumerate(hourly['time'])]
    else:
        with open(path, newline='', encoding='utf-8-sig') as handle: rows = list(csv.DictReader(handle))
    output = []
    for r in rows:
        try:
            t = r.get('timestamp_utc') or r.get('time')
            if t and not any(t.endswith(x) for x in ('Z','+00:00')) and len(t) == 16:
                # Only the project's UTC-configured Open-Meteo snapshots use naive-looking ISO labels.
                t += ':00Z'
            speed = r.get('wind_speed_mps') if 'wind_speed_mps' in r else r.get('wind_speed',r.get('wind_speed_10m'))
            direction = r.get('wind_from_deg') if 'wind_from_deg' in r else r.get('wind_direction',r.get('wind_direction_10m'))
            if speed in ('',None) or direction in ('',None): continue
            value = float(speed)
            unit = r.get('speed_unit') or ('m/s' if 'wind_speed_mps' in r else 'km/h')
            if unit in ('km/h','kmh'): value /= 3.6
            elif unit in ('mph',): value *= .44704
            elif unit not in ('m/s','ms-1'): raise ValueError(f'Unknown speed unit {unit}')
            output.append({'timestamp_utc': parse_utc(t).isoformat().replace('+00:00','Z'),
                'wind_speed_mps': max(0,value), 'wind_from_deg': float(direction)%360,
                'relative_humidity': float(r.get('relative_humidity') or r.get('relative_humidity_2m') or 40)})
        except (ValueError, TypeError, AttributeError): continue
    return sorted(output, key=lambda x:x['timestamp_utc'])


def observation_gate(detections: list[dict], pass_gap_minutes: int = 30) -> dict:
    """Describe whether enough independent overpasses exist for a meaningful pilot."""
    if not detections: return {'usable':False, 'passes':0,'detections':0,'warnings':['No satellite detections']}
    times = sorted(parse_utc(r['observed_utc']) for r in detections)
    passes = 1
    for i in range(1,len(times)):
        if (times[i]-times[i-1]).total_seconds() > pass_gap_minutes*60: passes+=1
    warnings=[]
    if passes < 2: warnings.append('Only one temporally independent overpass: cannot validate propagation chronology')
    if len(times) < 3: warnings.append('Fewer than three observations')
    return {'usable':passes>=2 and len(times)>=3, 'passes':passes,
            'detections':len(times), 'first_utc':times[0].isoformat(), 'last_utc':times[-1].isoformat(), 'warnings':warnings}


def normalize_detection_file(input_csv: str, output_json: str, case_config: dict) -> dict:
    """Canonicalize raw FIRMS data for portable deployment and report data quality."""
    det = load_firms(input_csv,case_config.get('bbox_lonlat'),case_config.get('start_utc'),case_config.get('end_utc'))
    Path(output_json).parent.mkdir(parents=True,exist_ok=True)
    Path(output_json).write_text(json.dumps(det,indent=2))
    return observation_gate(det)
