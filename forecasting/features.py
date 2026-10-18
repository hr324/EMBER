"""Ex-ante features for each (cell, issue date). Every window boundary is explicit.

* Season: day-of-year harmonics of the forecast-window midpoint (known in advance).
* Location: cell id and projected centroid (static).
* Weather: trailing windows ending at ``weather_cutoff = issue_date - 7 days``
  (inclusive), from the cell's 50 km block point. Nothing inside the forecast
  window, nor the 6 days before it, is used.
* Fire history: FPA-FOD discoveries in [issue - N days, issue - 1 day] in the
  cell and its eight neighbours. Size and cause are never used.

Usage: python3 -m forecasting.features
"""
from __future__ import annotations

import json
from datetime import timedelta

import numpy as np
import pandas as pd

from . import config
from .fetch_weather import cell_to_point
from .grid import Grid

SEASON_COLS = ['season_sin1', 'season_cos1', 'season_sin2', 'season_cos2']
LOCATION_COLS = ['x_km', 'y_km']
HISTORY_COLS = ['hist_cell_30', 'hist_cell_90', 'hist_cell_365', 'hist_nbr_30', 'hist_nbr_90']
W = dict(tmax='temperature_2m_max', tmean='temperature_2m_mean', precip='precipitation_sum',
         rhmean='relative_humidity_2m_mean', rhmin='relative_humidity_2m_min',
         wind='wind_speed_10m_max', vpd='vapour_pressure_deficit_max',
         et0='et0_fao_evapotranspiration', sm='soil_moisture_0_to_7cm_mean')


def season(labels: pd.DataFrame) -> pd.DataFrame:
    mid = pd.to_datetime(labels['forecast_date']) + pd.Timedelta(days=(config.HORIZON_DAYS - 1) / 2)
    ang = 2 * np.pi * (mid.dt.dayofyear - 1) / 365.25
    return pd.DataFrame({'season_sin1': np.sin(ang), 'season_cos1': np.cos(ang),
                         'season_sin2': np.sin(2 * ang), 'season_cos2': np.cos(2 * ang),
                         'week_of_year': mid.dt.isocalendar().week.astype(int).clip(upper=52).values},
                        index=labels.index)


def location(labels: pd.DataFrame) -> pd.DataFrame:
    g = Grid()
    xy = {c.cell_id: c.centroid_xy for c in g.cells}
    return pd.DataFrame({'x_km': labels['cell_id'].map(lambda c: xy[c][0] / 1000),
                         'y_km': labels['cell_id'].map(lambda c: xy[c][1] / 1000)}, index=labels.index)


def weather_table(path=None) -> pd.DataFrame:
    """Per weather point, the trailing-window features indexed by window END date."""
    wx = pd.read_csv(path or config.PROCESSED_DIR / 'weather_daily.csv', parse_dates=['date'])
    frames = []
    for pid, g in wx.groupby('point_id'):
        g = g.set_index('date').sort_index().asfreq('D')
        f = pd.DataFrame(index=g.index)
        for w in (7, 14, 30):
            f[f'tmax_mean_{w}'] = g[W['tmax']].rolling(w, min_periods=w).mean()
            f[f'rhmin_mean_{w}'] = g[W['rhmin']].rolling(w, min_periods=w).mean()
            f[f'vpd_mean_{w}'] = g[W['vpd']].rolling(w, min_periods=w).mean()
            f[f'wind_mean_{w}'] = g[W['wind']].rolling(w, min_periods=w).mean()
        f['tmean_mean_7'] = g[W['tmean']].rolling(7, min_periods=7).mean()
        f['rhmean_mean_7'] = g[W['rhmean']].rolling(7, min_periods=7).mean()
        f['wind_max_7'] = g[W['wind']].rolling(7, min_periods=7).max()
        f['tmax_max_7'] = g[W['tmax']].rolling(7, min_periods=7).max()
        for w in (7, 30, 90):
            f[f'precip_sum_{w}'] = g[W['precip']].rolling(w, min_periods=w).sum()
        f['et0_sum_30'] = g[W['et0']].rolling(30, min_periods=30).sum()
        f['sm_mean_7'] = g[W['sm']].rolling(7, min_periods=7).mean()
        # Days since the last day with >= 1 mm precipitation, as of the window end (capped).
        wet = (g[W['precip']] >= 1.0).to_numpy()
        since, last = np.empty(len(wet)), None
        for i, w_ in enumerate(wet):
            if w_:
                last = i
            since[i] = 120 if last is None else min(i - last, 120)
        f['dry_days'] = since
        f['point_id'] = pid
        frames.append(f.reset_index().rename(columns={'date': 'weather_end'}))
    return pd.concat(frames, ignore_index=True)


WEATHER_COLS: list[str] = []  # filled on first build (column order of weather_table)


def weather(labels: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    c2p = cell_to_point()
    key = pd.DataFrame({'point_id': labels['cell_id'].map(c2p),
                        'weather_end': pd.to_datetime(labels['weather_cutoff'])}, index=labels.index)
    out = key.merge(table, on=['point_id', 'weather_end'], how='left')
    out.index = labels.index
    out = out.rename(columns={'weather_end': 'weather_latest_date', 'point_id': 'weather_point'})
    return out


def history(labels: pd.DataFrame, fires: pd.DataFrame) -> pd.DataFrame:
    """Counts of discoveries strictly before the issue date (no same-day or future fires)."""
    g = Grid()
    cells = [c.cell_id for c in g.cells]
    day0 = pd.Timestamp('2014-01-01')
    last = max(pd.Timestamp(config.LAST_ISSUE), pd.to_datetime(labels['forecast_date']).max())
    days = pd.date_range(day0, last + pd.Timedelta(days=7), freq='D')
    idx = {c: i for i, c in enumerate(cells)}
    counts = np.zeros((len(cells), len(days) + 1))
    for c, d in zip(fires['cell_id'], pd.to_datetime(fires['discovery_date'])):
        k = (d - day0).days
        if 0 <= k < len(days):
            counts[idx[c], k + 1] += 1
    cum = counts.cumsum(axis=1)  # cum[:, k] = fires on days [0, k-1]
    nbr = {c: [idx[n] for n in g.neighbours(c)] for c in cells}
    ci = labels['cell_id'].map(idx).to_numpy()
    k_issue = (pd.to_datetime(labels['forecast_date']) - day0).dt.days.to_numpy()  # excludes issue day

    def window(rows, ks, n):
        """Fires in [issue - n, issue - 1] for the given lattice rows."""
        return cum[rows, ks] - cum[rows, np.maximum(ks - n, 0)]

    out = pd.DataFrame(index=labels.index)
    for n in (30, 90, 365):
        out[f'hist_cell_{n}'] = window(ci, k_issue, n)
    for n in (30, 90):
        tot = np.zeros(len(labels))
        for j, c in enumerate(cells):
            m = ci == j
            for nb in nbr[c]:
                tot[m] += window(nb, k_issue[m], n)
        out[f'hist_nbr_{n}'] = tot
    out['history_latest_date'] = (pd.to_datetime(labels['forecast_date']) - pd.Timedelta(days=1)).dt.date
    return out


def build() -> pd.DataFrame:
    labels = pd.read_csv(config.PROCESSED_DIR / 'labels.csv',
                         parse_dates=['forecast_date', 'window_end', 'weather_cutoff'])
    fires = pd.read_csv(config.PROCESSED_DIR / 'fires.csv', parse_dates=['discovery_date'])
    wt = weather_table()
    df = pd.concat([labels, season(labels), location(labels), history(labels, fires),
                    weather(labels, wt)], axis=1)
    WEATHER_COLS[:] = [c for c in wt.columns if c not in ('weather_end', 'point_id')]
    assert_no_leakage(df)
    return df


def assert_no_leakage(df: pd.DataFrame) -> None:
    issue = pd.to_datetime(df['forecast_date'])
    wl = pd.to_datetime(df['weather_latest_date'])
    assert (wl <= issue - pd.Timedelta(days=config.WEATHER_LAG_DAYS)).all(), 'weather newer than issue - lag'
    hl = pd.to_datetime(df['history_latest_date'])
    assert (hl < issue).all(), 'fire history reaches the issue date'


def main() -> None:
    df = build()
    df.to_csv(config.PROCESSED_DIR / 'features.csv', index=False)
    miss = df[WEATHER_COLS].isna().mean().round(4)
    info = dict(rows=len(df), weather_cols=WEATHER_COLS, history_cols=HISTORY_COLS,
                season_cols=SEASON_COLS, location_cols=LOCATION_COLS,
                weather_missing_fraction=miss[miss > 0].to_dict(),
                weather_lag_days=config.WEATHER_LAG_DAYS)
    (config.PROCESSED_DIR / 'features_info.json').write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2)[:1500])


if __name__ == '__main__':
    main()
