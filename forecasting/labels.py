"""Build the real cell x week lattice and its 7-day new-ignition labels.

Each row is one real 25 km cell and one Monday issue date. ``label`` is 1 when
at least one FPA-FOD fire has ``discovery_date`` in [issue_date, issue_date+6];
0 means *zero reported fires*, not proof that no fire occurred.

Usage: python3 -m forecasting.labels
"""
from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd

from . import config
from .grid import Grid


def issue_dates() -> list:
    d, out = config.FIRST_ISSUE, []
    assert d.weekday() == config.ISSUE_WEEKDAY
    while d <= config.LAST_ISSUE:
        out.append(d)
        d += timedelta(days=7)
    return out


def load_fires() -> pd.DataFrame:
    f = pd.read_csv(config.PROCESSED_DIR / 'fires.csv', dtype={'fpa_id': str})
    f['discovery_date'] = pd.to_datetime(f['discovery_date']).dt.date
    return f


def build(fires: pd.DataFrame | None = None) -> pd.DataFrame:
    fires = load_fires() if fires is None else fires
    grid = Grid()
    issues = issue_dates()
    lattice = pd.MultiIndex.from_product([[c.cell_id for c in grid.cells], issues],
                                         names=['cell_id', 'forecast_date']).to_frame(index=False)
    # Map each fire to the Monday-issued window that contains its discovery date.
    fd = pd.to_datetime(fires['discovery_date'])
    week_start = (fd - pd.to_timedelta(fd.dt.weekday, unit='D')).dt.date
    counts = (pd.DataFrame({'cell_id': fires['cell_id'], 'forecast_date': week_start})
              .groupby(['cell_id', 'forecast_date']).size().rename('event_count').reset_index())
    lab = lattice.merge(counts, on=['cell_id', 'forecast_date'], how='left')
    lab['event_count'] = lab['event_count'].fillna(0).astype(int)
    lab['label'] = (lab['event_count'] > 0).astype(int)
    lab['horizon_days'] = config.HORIZON_DAYS
    lab['window_end'] = lab['forecast_date'] + timedelta(days=config.HORIZON_DAYS - 1)
    lab['weather_cutoff'] = lab['forecast_date'] - timedelta(days=config.WEATHER_LAG_DAYS)
    lab['split'] = lab['forecast_date'].map(config.split_of)
    cen = {c.cell_id: c.centroid_latlon for c in grid.cells}
    lab['centroid_lat'] = lab['cell_id'].map(lambda c: round(cen[c][0], 5))
    lab['centroid_lon'] = lab['cell_id'].map(lambda c: round(cen[c][1], 5))
    return lab.sort_values(['forecast_date', 'cell_id']).reset_index(drop=True)


def audit(lab: pd.DataFrame, fires: pd.DataFrame) -> dict:
    in_window = fires[(pd.to_datetime(fires['discovery_date']) >= pd.Timestamp(config.FIRST_ISSUE)) &
                      (pd.to_datetime(fires['discovery_date']) <= pd.Timestamp(config.LAST_ISSUE) + pd.Timedelta(days=6))]
    out = dict(cells=int(lab['cell_id'].nunique()), weeks=int(lab['forecast_date'].nunique()),
               cell_weeks=int(len(lab)), fires_in_labelled_windows=int(in_window.shape[0]),
               events_counted=int(lab['event_count'].sum()), positives=int(lab['label'].sum()),
               positive_rate=round(float(lab['label'].mean()), 4),
               cells_never_positive=int((lab.groupby('cell_id')['label'].sum() == 0).sum()),
               by_split={})
    for s, g in lab.groupby('split'):
        out['by_split'][s] = dict(first=str(g['forecast_date'].min()), last=str(g['forecast_date'].max()),
                                  weeks=int(g['forecast_date'].nunique()), cell_weeks=int(len(g)),
                                  positives=int(g['label'].sum()), events=int(g['event_count'].sum()),
                                  positive_rate=round(float(g['label'].mean()), 4))
    assert out['events_counted'] == out['fires_in_labelled_windows'], 'every in-window fire must be labelled once'
    return out


def main() -> None:
    fires = load_fires()
    lab = build(fires)
    a = audit(lab, fires)
    lab.to_csv(config.PROCESSED_DIR / 'labels.csv', index=False)
    (config.PROCESSED_DIR / 'labels_audit.json').write_text(json.dumps(a, indent=2))
    print(json.dumps(a, indent=2))


if __name__ == '__main__':
    main()
