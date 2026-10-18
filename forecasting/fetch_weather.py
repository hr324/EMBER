"""Download real daily reanalysis weather from the free Open-Meteo archive API.

Sampling design: one point per 2x2 block of 25 km cells (~50 km), at the block
centroid. Ten years at every cell centroid would exceed the free tier's daily
quota (each location x 14 days counts as one call). Every cell inherits the
weather of its block. Daily aggregates use the America/Los_Angeles calendar day,
matching the date-only fire discovery labels.

Responses are cached per (point, year) under ``data/cache/forecasting/weather``.
HTTP 429 (quota) triggers a polite wait-and-retry, never a paid plan.

Usage: python3 -m forecasting.fetch_weather
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import date, datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import config
from .grid import Grid, from_albers

DAILY_VARS = ['temperature_2m_max', 'temperature_2m_mean', 'precipitation_sum',
              'relative_humidity_2m_mean', 'relative_humidity_2m_min', 'wind_speed_10m_max',
              'vapour_pressure_deficit_max', 'et0_fao_evapotranspiration',
              'soil_moisture_0_to_7cm_mean']
UNITS = {'temperature_2m_max': 'degC', 'temperature_2m_mean': 'degC', 'precipitation_sum': 'mm',
         'relative_humidity_2m_mean': '%', 'relative_humidity_2m_min': '%',
         'wind_speed_10m_max': 'km/h', 'vapour_pressure_deficit_max': 'kPa',
         'et0_fao_evapotranspiration': 'mm', 'soil_moisture_0_to_7cm_mean': 'm3/m3'}
BLOCK = 2                          # cells per weather block side
START = date(2014, 9, 1)           # leaves >= 90 days of history before the first issue date
END = date(2024, 12, 23)
TZ = 'America/Los_Angeles'
UA = {'User-Agent': 'EMBER-datathon-research/0.1 (non-commercial; retrospective backtest)'}


def weather_points(grid: Grid | None = None) -> dict[str, dict]:
    """Block id -> centroid lat/lon and member cells."""
    grid = grid or Grid()
    pts: dict[str, dict] = {}
    for cell in grid.cells:
        br, bc = cell.row // BLOCK, cell.col // BLOCK
        bid = f'w{br:02d}_{bc:02d}'
        p = pts.setdefault(bid, dict(block_row=br, block_col=bc, cells=[]))
        p['cells'].append(cell.cell_id)
    for bid, p in pts.items():
        span_r = min(BLOCK, grid.nrows - p['block_row'] * BLOCK)
        span_c = min(BLOCK, grid.ncols - p['block_col'] * BLOCK)
        x = grid.x0 + (p['block_col'] * BLOCK + span_c / 2) * grid.size
        y = grid.y0 + (p['block_row'] * BLOCK + span_r / 2) * grid.size
        p['lat'], p['lon'] = from_albers(x, y)
    return pts


def cell_to_point(grid: Grid | None = None) -> dict[str, str]:
    return {c: bid for bid, p in weather_points(grid).items() for c in p['cells']}


def _fetch(params: dict, tries: int = 30) -> bytes:
    url = config.OPEN_METEO_ARCHIVE + '?' + urlencode(params)
    for k in range(tries):
        try:
            with urlopen(Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except HTTPError as exc:
            if exc.code == 429:
                print(f'  429 quota reached ({exc.read()[:120]!r}); waiting 5 min (attempt {k + 1})', flush=True)
                time.sleep(300)
                continue
            if k >= 4:
                raise
            time.sleep(10 * (k + 1))
        except Exception as exc:
            if k >= 4:
                raise
            print(f'  retry after {exc!r}', flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError('Open-Meteo still rate-limited after retries; rerun later (cache is kept).')


def download() -> list[dict]:
    cache = config.CACHE_DIR / 'weather'
    cache.mkdir(parents=True, exist_ok=True)
    pts = weather_points()
    manifest = []
    for bid, p in sorted(pts.items()):
        for year in range(START.year, END.year + 1):
            s = max(START, date(year, 1, 1))
            e = min(END, date(year, 12, 31))
            path = cache / f'{bid}_{year}.json'
            if not path.exists():
                params = dict(latitude=f"{p['lat']:.5f}", longitude=f"{p['lon']:.5f}",
                              start_date=s.isoformat(), end_date=e.isoformat(),
                              daily=','.join(DAILY_VARS), timezone=TZ)
                raw = _fetch(params)
                json.loads(raw)  # validate before caching
                path.write_bytes(raw)
                print(f'  {bid} {year}: fetched', flush=True)
                time.sleep(2.5)  # stay well under the per-minute limit
            raw = path.read_bytes()
            manifest.append(dict(point=bid, year=year, file=path.name,
                                 sha256=hashlib.sha256(raw).hexdigest()))
    return manifest


def assemble(manifest: list[dict]) -> None:
    pts = weather_points()
    cache = config.CACHE_DIR / 'weather'
    rows = []
    for m in manifest:
        d = json.loads((cache / m['file']).read_bytes())
        daily = d['daily']
        for i, t in enumerate(daily['time']):
            rows.append(dict(point_id=m['point'], date=t, **{v: daily[v][i] for v in DAILY_VARS}))
        m['grid_lat'], m['grid_lon'], m['elevation_m'] = d['latitude'], d['longitude'], d.get('elevation')
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / 'weather_daily.csv'
    with out.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    meta = dict(source=config.OPEN_METEO_ARCHIVE, docs='https://open-meteo.com/en/docs/historical-weather-api',
                model='Open-Meteo best_match historical reanalysis (ERA5 / ERA5-Land family)',
                daily_vars=DAILY_VARS, units=UNITS, timezone=TZ, start=START.isoformat(), end=END.isoformat(),
                sampling='one point per 2x2 block of 25 km EPSG:3310 cells, at block centroid',
                points={k: dict(lat=v['lat'], lon=v['lon'], cells=v['cells']) for k, v in pts.items()},
                files=manifest, assembled_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                rows=len(rows))
    (config.PROCESSED_DIR / 'weather_manifest.json').write_text(json.dumps(meta, indent=2))
    missing = sum(1 for r in rows for v in DAILY_VARS if r[v] is None)
    print(f'wrote {out}: {len(rows)} point-days, {missing} missing values')


def main() -> None:
    pts = weather_points()
    print(f'{len(pts)} weather points, {START}..{END}', flush=True)
    assemble(download())


if __name__ == '__main__':
    main()
