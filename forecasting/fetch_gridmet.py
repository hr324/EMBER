"""gridMET fire-danger and fuel-moisture indices at each cell centroid (4 km grid).

Source: University of Idaho / Northwest Knowledge Network THREDDS NetCDF Subset
Service (free, no account). Variables: energy release component (ERC), burning
index (BI), 100-hour and 1000-hour dead fuel moisture (scale factor 0.1 applied).
Observed archive latency on 18 Oct 2026: latest day 16 Oct, so features use a
3-day lag (latest gridMET day = issue date - 3). Historical values are the
archive's current (final) versions, not the provisional values published at the
time: a stated limitation.

Usage: python3 -m forecasting.fetch_gridmet
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import pandas as pd

from . import config
from .grid import Grid

BASE = 'http://thredds.northwestknowledge.net:8080/thredds/ncss/grid'
VARS = {  # short name: (dataset, variable, scale)
    'erc': ('agg_met_erc_1979_CurrentYear_CONUS.nc', 'daily_mean_energy_release_component-g', 1.0),
    'bi': ('agg_met_bi_1979_CurrentYear_CONUS.nc', 'daily_mean_burning_index_g', 1.0),
    'fm100': ('agg_met_fm100_1979_CurrentYear_CONUS.nc', 'dead_fuel_moisture_100hr', 0.1),
    'fm1000': ('agg_met_fm1000_1979_CurrentYear_CONUS.nc', 'dead_fuel_moisture_1000hr', 0.1),
}
START, END = '2014-09-01', '2026-10-16'
LAG_DAYS = 3
UA = {'User-Agent': 'EMBER-datathon-research/0.1 (non-commercial; retrospective backtest)'}
CACHE = config.CACHE_DIR / 'gridmet'


def fetch(cell_id: str, lat: float, lon: float, short: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f'{cell_id}_{short}.csv'
    if p.exists():
        return p.read_bytes()
    ds, var, _ = VARS[short]
    url = (f'{BASE}/{ds}?var={var}&latitude={lat:.5f}&longitude={lon:.5f}'
           f'&time_start={START}T00:00:00Z&time_end={END}T00:00:00Z&accept=csv')
    for k in range(5):
        try:
            with urlopen(Request(url, headers=UA), timeout=180) as r:
                raw = r.read()
            break
        except Exception as exc:
            if k == 4:
                raise
            print(f'  retry {cell_id} {short}: {exc!r}', flush=True)
            time.sleep(10 * (k + 1))
    p.write_bytes(raw)
    time.sleep(0.3)
    return raw


def main() -> None:
    rows, files = {}, []
    for c in Grid().cells:
        lat, lon = c.centroid_latlon
        for short, (_, _, scale) in VARS.items():
            raw = fetch(c.cell_id, lat, lon, short)
            files.append(dict(cell_id=c.cell_id, var=short, sha256=hashlib.sha256(raw).hexdigest()))
            r = csv.reader(io.StringIO(raw.decode()))
            next(r)
            for line in r:
                v = float(line[-1])
                key = (c.cell_id, line[0][:10])
                rows.setdefault(key, {})[short] = None if v >= 32767 * scale or v != v else round(v * scale, 3)
        print(f'  {c.cell_id} done', flush=True)
    df = pd.DataFrame([dict(cell_id=k[0], date=k[1], **v) for k, v in rows.items()]).sort_values(['cell_id', 'date'])
    df.to_csv(config.PROCESSED_DIR / 'gridmet_daily.csv', index=False)
    meta = dict(source=BASE, variables={k: dict(dataset=v[0], variable=v[1], scale=v[2]) for k, v in VARS.items()},
                start=START, end=END, lag_days=LAG_DAYS, points='80 cell centroids', rows=int(len(df)),
                missing={k: int(df[k].isna().sum()) for k in VARS}, files=files,
                built_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                limitation='Archive values are final versions; provisional near-real-time values may have differed.')
    (config.PROCESSED_DIR / 'gridmet_manifest.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: v for k, v in meta.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
