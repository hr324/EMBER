"""Download real FPA-FOD 7th-edition fire records for the study lattice.

Paginated ArcGIS REST queries (max 2,000 records/response), stdlib only.
Raw pages are saved verbatim under ``data/raw/forecasting/fpa_fod/`` with a
SHA-256 manifest; the cleaned table goes to ``data/processed/forecasting``.

Usage: python3 -m forecasting.fetch_fires [--refresh]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import config
from .grid import Grid

OUT_FIELDS = ['objectid', 'fod_id', 'fpa_id', 'source_system', 'nwcg_reporting_agency',
              'fire_name', 'fire_year', 'discovery_date', 'discovery_doy', 'discovery_time',
              'latitude', 'longitude', 'state', 'county', 'nwcg_general_cause',
              'fire_size', 'fire_size_class']
PAGE = 2000
UA = {'User-Agent': 'EMBER-datathon-research/0.1 (non-commercial; retrospective backtest)'}


def _get(url: str, params: dict, tries: int = 5) -> dict:
    body = urlencode(params).encode()
    for k in range(tries):
        try:
            with urlopen(Request(url, data=body, headers=UA), timeout=120) as r:
                data = json.loads(r.read())
            if 'error' in data:
                raise RuntimeError(data['error'])
            return data
        except Exception as exc:  # network hiccup or server-side error: polite backoff
            if k == tries - 1:
                raise
            print(f'  retry {k + 1} after {exc!r}')
            time.sleep(5 * (k + 1))
    raise AssertionError


def where_clause(bounds: dict) -> str:
    y0, y1 = config.FIRE_YEARS
    return (f"fire_year >= {y0} AND fire_year <= {y1} AND "
            f"latitude >= {bounds['lat_min']:.5f} AND latitude <= {bounds['lat_max']:.5f} AND "
            f"longitude >= {bounds['lon_min']:.5f} AND longitude <= {bounds['lon_max']:.5f}")


def download(refresh: bool = False) -> list[dict]:
    """Fetch every page (cached), returning raw attribute dicts."""
    raw_dir = config.RAW_DIR / 'fpa_fod'
    raw_dir.mkdir(parents=True, exist_ok=True)
    where = where_clause(Grid().latlon_bounds())
    url = config.FPA_FOD_LAYER + '/query'
    manifest, rows, offset = [], [], 0
    while True:
        params = dict(where=where, outFields=','.join(OUT_FIELDS), returnGeometry='false',
                      orderByFields='objectid', resultOffset=offset, resultRecordCount=PAGE, f='json')
        page_path = raw_dir / f'page_{offset:06d}.json'
        if page_path.exists() and not refresh:
            raw = page_path.read_bytes()
        else:
            data = _get(url, params)
            raw = json.dumps(data, sort_keys=True).encode()
            page_path.write_bytes(raw)
            time.sleep(1)
        data = json.loads(raw)
        feats = [f['attributes'] for f in data.get('features', [])]
        manifest.append(dict(file=page_path.name, offset=offset, records=len(feats),
                             sha256=hashlib.sha256(raw).hexdigest()))
        rows += feats
        print(f'  offset {offset}: {len(feats)} records')
        if len(feats) < PAGE and not data.get('exceededTransferLimit'):
            break
        offset += len(feats)
    meta = dict(source=config.FPA_FOD_LAYER, doi=config.FPA_FOD_DOI, where=where,
                out_fields=OUT_FIELDS, page_size=PAGE, pages=manifest,
                downloaded_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                total_records=len(rows))
    (raw_dir / 'manifest.json').write_text(json.dumps(meta, indent=2))
    return rows


def epoch_ms_to_date(ms: int):
    """ArcGIS Date (epoch milliseconds, UTC) to a calendar date.

    Validated against ``discovery_doy`` in :func:`clean`: FPA-FOD stores
    date-only values, so the UTC calendar date is used without timezone shifts.
    """
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)).date()


def clean(rows: list[dict]) -> tuple[list[dict], dict]:
    """Deduplicate, validate coordinates/dates, assign grid cells. Returns rows + audit."""
    grid = Grid()
    audit = dict(raw_records=len(rows), duplicate_objectid=0, duplicate_fpa_id=0,
                 missing_date=0, doy_mismatch=0, outside_grid=0, bad_coords=0)
    seen_oid, seen_fpa, out = set(), set(), []
    for r in rows:
        if r['objectid'] in seen_oid:
            audit['duplicate_objectid'] += 1
            continue
        seen_oid.add(r['objectid'])
        if r.get('fpa_id') and r['fpa_id'] in seen_fpa:
            audit['duplicate_fpa_id'] += 1
            continue
        seen_fpa.add(r.get('fpa_id'))
        if r.get('discovery_date') is None:
            audit['missing_date'] += 1
            continue
        d = epoch_ms_to_date(r['discovery_date'])
        if r.get('discovery_doy') is not None and d.timetuple().tm_yday != r['discovery_doy']:
            audit['doy_mismatch'] += 1
        lat, lon = r.get('latitude'), r.get('longitude')
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            audit['bad_coords'] += 1
            continue
        cell = grid.cell_of(lat, lon)
        if cell is None:
            audit['outside_grid'] += 1
            continue
        out.append(dict(objectid=r['objectid'], fod_id=r.get('fod_id'), fpa_id=r.get('fpa_id'),
                        discovery_date=d.isoformat(), fire_year=r['fire_year'],
                        discovery_doy=r.get('discovery_doy'), discovery_time=r.get('discovery_time'),
                        latitude=lat, longitude=lon, cell_id=cell, state=r.get('state'),
                        county=r.get('county'), agency=r.get('nwcg_reporting_agency'),
                        source_system=r.get('source_system'), fire_name=r.get('fire_name'),
                        # audit-only, NEVER a predictor (post-event information):
                        audit_cause=r.get('nwcg_general_cause'), audit_fire_size_ac=r.get('fire_size'),
                        audit_size_class=r.get('fire_size_class')))
    # Same point + same discovery date reported more than once (possible multi-agency duplicates).
    keys = {}
    for r in out:
        keys.setdefault((round(r['latitude'], 4), round(r['longitude'], 4), r['discovery_date']), []).append(r)
    audit['same_point_same_day_groups'] = sum(1 for v in keys.values() if len(v) > 1)
    pos = {}
    for r in out:
        pos.setdefault((round(r['latitude'], 4), round(r['longitude'], 4)), 0)
        pos[(round(r['latitude'], 4), round(r['longitude'], 4))] += 1
    audit['repeated_positions_ge5'] = sum(1 for v in pos.values() if v >= 5)
    audit['clean_records'] = len(out)
    return out, audit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--refresh', action='store_true', help='ignore cached pages')
    args = ap.parse_args()
    rows = download(args.refresh)
    fires, audit = clean(rows)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PROCESSED_DIR / 'fires.csv'
    with path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(fires[0]))
        w.writeheader()
        w.writerows(fires)
    (config.PROCESSED_DIR / 'fires_audit.json').write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit, indent=2))
    print(f'wrote {path} ({len(fires)} fires)')


if __name__ == '__main__':
    main()
