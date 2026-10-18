"""gridMET fire-danger and fuel-moisture indices, averaged over each 25 km cell.

Source: University of Idaho / Northwest Knowledge Network THREDDS NetCDF Subset
Service (free, no account). One bounding-box request per variable per year
(NetCDF3, read with scipy); each cell value is the mean of the ~4 km gridMET
pixels whose centres fall inside the cell. Variables: energy release component
(ERC), burning index (BI), 100-hour and 1000-hour dead fuel moisture.

Observed archive latency on 18 Oct 2026: latest day 16 Oct, so features use a
3-day lag (latest gridMET day = issue date - 3). Historical values are the
archive's current (final) versions, not the provisional values published at the
time: a stated limitation.

Usage: python3 -m forecasting.fetch_gridmet
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.io import netcdf_file

from . import config
from .grid import Grid

BASE = 'http://thredds.northwestknowledge.net:8080/thredds/ncss/grid'
VARS = {
    'erc': ('agg_met_erc_1979_CurrentYear_CONUS.nc', 'daily_mean_energy_release_component-g'),
    'bi': ('agg_met_bi_1979_CurrentYear_CONUS.nc', 'daily_mean_burning_index_g'),
    'fm100': ('agg_met_fm100_1979_CurrentYear_CONUS.nc', 'dead_fuel_moisture_100hr'),
    'fm1000': ('agg_met_fm1000_1979_CurrentYear_CONUS.nc', 'dead_fuel_moisture_1000hr'),
}
YEARS = range(2014, 2027)
LAST_DAY = date(2026, 10, 16)
LAG_DAYS = 3
UA = {'User-Agent': 'EMBER-datathon-research/0.1 (non-commercial; retrospective backtest)'}
CACHE = config.CACHE_DIR / 'gridmet'


def fetch(short: str, year: int) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f'{short}_{year}.nc'
    if p.exists():
        return p.read_bytes()
    ds, var = VARS[short]
    b = Grid().latlon_bounds(pad_deg=0.05)
    end = min(date(year, 12, 31), LAST_DAY)
    url = (f'{BASE}/{ds}?var={var}&north={b["lat_max"]:.3f}&south={b["lat_min"]:.3f}&west={b["lon_min"]:.3f}'
           f'&east={b["lon_max"]:.3f}&horizStride=1&time_start={year}-01-01T00:00:00Z'
           f'&time_end={end.isoformat()}T00:00:00Z&accept=netcdf')
    for k in range(5):
        try:
            with urlopen(Request(url, headers=UA), timeout=300) as r:
                raw = r.read()
            break
        except Exception as exc:
            if k == 4:
                raise
            print(f'  retry {short} {year}: {exc!r}', flush=True)
            time.sleep(15 * (k + 1))
    p.write_bytes(raw)
    time.sleep(0.5)
    return raw


def read(short: str, year: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    path = CACHE / f'{short}_{year}.nc'
    f = netcdf_file(str(path), 'r', mmap=False)
    v = f.variables[VARS[short][1]]
    data = v.data.astype(float)
    fill = getattr(v, '_FillValue', None)
    if fill is not None:
        data[data == float(fill)] = np.nan
    data = data * float(getattr(v, 'scale_factor', 1.0)) + float(getattr(v, 'add_offset', 0.0))
    days = [date(1900, 1, 1) + timedelta(days=int(d)) for d in f.variables['day'].data]
    lat, lon = f.variables['lat'].data.copy(), f.variables['lon'].data.copy()
    # gridMET carries an attribute literally named "dimensions" that masks scipy's
    # property, so axes are identified by their lengths (all three differ here).
    sizes = {len(days): 'day', len(lat): 'lat', len(lon): 'lon'}
    assert len(sizes) == 3, 'ambiguous axis lengths'
    names = [sizes[n] for n in data.shape]
    data = np.transpose(data, [names.index(d) for d in ('day', 'lat', 'lon')])
    f.close()
    return data, lat, lon, days


def main() -> None:
    grid = Grid()
    cells = [c.cell_id for c in grid.cells]
    files, frames = [], []
    pix_cell = None
    for short in VARS:
        for y in YEARS:
            raw = fetch(short, y)
            files.append(dict(var=short, year=y, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
            data, lat, lon, days = read(short, y)
            if pix_cell is None:
                pix_cell = np.array([[grid.cell_of(float(la), float(lo)) or '' for lo in lon] for la in lat])
                members = {c: np.where(pix_cell == c) for c in cells}
                npix = {c: int(len(members[c][0])) for c in cells}
            vals = {c: np.nanmean(data[:, members[c][0], members[c][1]], axis=1) for c in cells}
            frames.append(pd.DataFrame({'date': np.repeat(days, len(cells)),
                                        'cell_id': np.tile(cells, len(days)),
                                        short: np.column_stack([vals[c] for c in cells]).ravel()}))
        print(f'  {short} done', flush=True)
    df = None
    for short in VARS:
        part = pd.concat([f for f in frames if short in f.columns], ignore_index=True)
        df = part if df is None else df.merge(part, on=['date', 'cell_id'], how='outer')
    df = df.sort_values(['cell_id', 'date'])
    df.to_csv(config.PROCESSED_DIR / 'gridmet_daily.csv', index=False)
    meta = dict(source=BASE, variables={k: dict(dataset=v[0], variable=v[1]) for k, v in VARS.items()},
                years=[min(YEARS), max(YEARS)], last_day=LAST_DAY.isoformat(), lag_days=LAG_DAYS,
                aggregation='mean of gridMET pixels whose centres fall inside each 25 km cell',
                pixels_per_cell=dict(min=min(npix.values()), max=max(npix.values())), rows=int(len(df)),
                missing={k: int(df[k].isna().sum()) for k in VARS}, files=files,
                built_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                limitation='Archive values are final versions; provisional near-real-time values may have differed.')
    (config.PROCESSED_DIR / 'gridmet_manifest.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: v for k, v in meta.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
