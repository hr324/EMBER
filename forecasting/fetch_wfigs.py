"""Download NIFC WFIGS wildfire incident locations (near-real-time feed).

Rules are fixed in ``forecasting/PREREG_2025.md``: IncidentTypeCategory = 'WF',
discovery date = FireDiscoveryDateTime converted to the America/Los_Angeles
calendar date, location = InitialLatitude/InitialLongitude (else the point
geometry), dedupe by UniqueFireIdentifier then IrwinID. Size and cause fields
are kept for audit only and are never model inputs.

Usage: python3 -m forecasting.fetch_wfigs [--refresh]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from . import config
from .grid import Grid

LAYER = ('https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/'
         'WFIGS_Incident_Locations/FeatureServer/0')
FIELDS = ['OBJECTID', 'UniqueFireIdentifier', 'IrwinID', 'IncidentName', 'FireDiscoveryDateTime',
          'InitialLatitude', 'InitialLongitude', 'IncidentTypeCategory', 'IncidentTypeKind', 'POOState',
          'POOCounty', 'DiscoveryAcres', 'IncidentSize', 'FireCauseGeneral', 'CreatedOnDateTime_dt']
PAGE = 2000
PACIFIC = ZoneInfo('America/Los_Angeles')
UA = {'User-Agent': 'EMBER-datathon-research/0.1 (non-commercial; retrospective backtest)'}


def _get(params: dict, tries: int = 5) -> dict:
    body = urlencode(params).encode()
    for k in range(tries):
        try:
            with urlopen(Request(LAYER + '/query', data=body, headers=UA), timeout=120) as r:
                data = json.loads(r.read())
            if 'error' in data:
                raise RuntimeError(data['error'])
            return data
        except Exception as exc:
            if k == tries - 1:
                raise
            print(f'  retry {k + 1} after {exc!r}')
            time.sleep(5 * (k + 1))
    raise AssertionError


def download(refresh: bool = False) -> list[dict]:
    raw_dir = config.RAW_DIR / 'wfigs'
    raw_dir.mkdir(parents=True, exist_ok=True)
    b = Grid().latlon_bounds()
    envelope = json.dumps(dict(xmin=b['lon_min'], ymin=b['lat_min'], xmax=b['lon_max'], ymax=b['lat_max'],
                               spatialReference=dict(wkid=4326)))
    where = "IncidentTypeCategory='WF' AND FireDiscoveryDateTime >= TIMESTAMP '2014-01-01 00:00:00'"
    rows, manifest, offset = [], [], 0
    while True:
        path = raw_dir / f'page_{offset:06d}.json'
        if path.exists() and not refresh:
            raw = path.read_bytes()
        else:
            data = _get(dict(where=where, geometry=envelope, geometryType='esriGeometryEnvelope', inSR=4326,
                             spatialRel='esriSpatialRelIntersects', outFields=','.join(FIELDS),
                             returnGeometry='true', outSR=4326, orderByFields='OBJECTID',
                             resultOffset=offset, resultRecordCount=PAGE, f='json'))
            raw = json.dumps(data, sort_keys=True).encode()
            path.write_bytes(raw)
            time.sleep(1)
        data = json.loads(raw)
        feats = data.get('features', [])
        for f in feats:
            rows.append(dict(f['attributes'], _gx=(f.get('geometry') or {}).get('x'), _gy=(f.get('geometry') or {}).get('y')))
        manifest.append(dict(file=path.name, offset=offset, records=len(feats), sha256=hashlib.sha256(raw).hexdigest()))
        print(f'  offset {offset}: {len(feats)} records')
        if len(feats) < PAGE and not data.get('exceededTransferLimit'):
            break
        offset += len(feats)
    (raw_dir / 'manifest.json').write_text(json.dumps(dict(
        source=LAYER, where=where, envelope=envelope, out_fields=FIELDS, pages=manifest, total_records=len(rows),
        downloaded_utc=datetime.now(timezone.utc).isoformat(timespec='seconds')), indent=2))
    return rows


def clean(rows: list[dict]) -> tuple[list[dict], dict]:
    grid = Grid()
    audit = dict(raw_records=len(rows), duplicate_unique_id=0, duplicate_irwin=0, missing_date=0,
                 location_from_geometry=0, missing_location=0, outside_grid=0, kinds={})
    seen_u, seen_i, out = set(), set(), []
    for r in rows:
        u, irwin = r.get('UniqueFireIdentifier'), r.get('IrwinID')
        if u and u in seen_u:
            audit['duplicate_unique_id'] += 1
            continue
        if irwin and irwin in seen_i:
            audit['duplicate_irwin'] += 1
            continue
        seen_u.add(u)
        seen_i.add(irwin)
        if r.get('FireDiscoveryDateTime') is None:
            audit['missing_date'] += 1
            continue
        t = datetime.fromtimestamp(r['FireDiscoveryDateTime'] / 1000, timezone.utc)
        local = t.astimezone(PACIFIC)
        lat, lon = r.get('InitialLatitude'), r.get('InitialLongitude')
        if lat is None or lon is None or not lat or not lon:
            lat, lon = r.get('_gy'), r.get('_gx')
            audit['location_from_geometry'] += 1
        if lat is None or lon is None:
            audit['missing_location'] += 1
            continue
        cell = grid.cell_of(lat, lon)
        if cell is None:
            audit['outside_grid'] += 1
            continue
        kind = r.get('IncidentTypeKind') or 'NA'
        audit['kinds'][kind] = audit['kinds'].get(kind, 0) + 1
        out.append(dict(objectid=r['OBJECTID'], unique_fire_id=u, irwin_id=irwin, fire_name=r.get('IncidentName'),
                        discovery_utc=t.isoformat(), discovery_date=local.date().isoformat(), fire_year=local.year,
                        latitude=lat, longitude=lon, cell_id=cell, kind=kind, county=r.get('POOCounty'),
                        audit_discovery_acres=r.get('DiscoveryAcres'), audit_fire_size_ac=r.get('IncidentSize'),
                        audit_cause=r.get('FireCauseGeneral')))
    audit['utc_date_differs_from_pacific_date'] = sum(1 for r in out if r['discovery_utc'][:10] != r['discovery_date'])
    audit['clean_records'] = len(out)
    audit['by_year'] = {}
    for r in out:
        audit['by_year'][r['fire_year']] = audit['by_year'].get(r['fire_year'], 0) + 1
    audit['by_year'] = dict(sorted(audit['by_year'].items()))
    return out, audit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--refresh', action='store_true')
    rows = download(ap.parse_args().refresh)
    fires, audit = clean(rows)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with (config.PROCESSED_DIR / 'wfigs_fires.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(fires[0]))
        w.writeheader()
        w.writerows(fires)
    (config.PROCESSED_DIR / 'wfigs_audit.json').write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
