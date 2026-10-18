"""Score any Monday issue date from live sources: the re-runnable prediction interface.

    python3 -m forecasting.predict --date 2026-10-19 [--refresh-fires]

Builds features exactly as in training, with each source's lag:
  * fire history: WFIGS discoveries strictly before the issue date
    (``--refresh-fires`` re-downloads the live feed first);
  * weather (model E): Open-Meteo archive, windows ending issue - 7 days;
    missing recent days are fetched for the 20 weather points;
  * Red Flag / Fire Weather Watch (candidate): IEM archive, products published by
    Monday 06:00 America/Los_Angeles; the issue year is re-downloaded.

Scores A (climatology), E (original frozen model) and the overnight candidate
(E0+redflag, ``candidate_v2.pkl``). Alerts are VARIABLE: a cell is alerted when
its risk clears that model's threshold, chosen on 2021-2022 validation
(``outputs/alert_thresholds.json``; default rule ``precision70``, also
``precision50`` and ``best_f1``). So a quiet week can have no alerts and a
dangerous week many. Writes ``outputs/live/forecast_<date>.csv`` and ``.geojson``.
Outcomes are NOT included; score them later with ``--score-outcomes``.
``--reflag`` recomputes alert flags on a saved forecast from its saved scores.

Python API: ``score_frame(df)`` scores a frame that already holds the feature
columns (see ``features_info.json`` and ``candidate.SPECS``).
"""
from __future__ import annotations

import argparse
import json
import pickle
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import config, external_test, features
from .candidate import BUNDLE, CAND, SPECS
from .evaluate import BASELINE, HEADLINE
from .experiments import REDFLAG_COLS
from .grid import Grid

LIVE = config.OUTPUT_DIR / 'live'
THRESHOLDS = config.OUTPUT_DIR / 'alert_thresholds.json'
TAGS = ((BASELINE, 'baseline'), (HEADLINE, 'ember'), (CAND, 'candidate'))


def load_thresholds() -> dict:
    return json.loads(THRESHOLDS.read_text())


def add_alerts(out: pd.DataFrame) -> dict:
    """Variable alert flags per model and rule from saved risk scores (validation thresholds)."""
    t = load_thresholds()
    for model, tag in TAGS:
        for rule, thr in t['thresholds'][model].items():
            if thr is not None:
                out[f'{tag}_alert_{rule}'] = out[f'{tag}_risk_score'] >= thr
        out[f'{tag}_alert'] = out[f'{tag}_alert_{t["default_rule"]}']
    return t


def ensure_weather(issue: date) -> None:
    """Fetch any days missing before the weather cutoff into weather_daily_live.csv."""
    from . import fetch_weather as FW
    need_end = issue - timedelta(days=config.WEATHER_LAG_DAYS)
    have = pd.concat([pd.read_csv(config.PROCESSED_DIR / n, usecols=['point_id', 'date'])
                      for n in ('weather_daily.csv', 'weather_daily_ext.csv', 'weather_daily_live.csv')
                      if (config.PROCESSED_DIR / n).exists()])
    last = pd.to_datetime(have['date']).max().date()
    if last >= need_end:
        return
    start = last + timedelta(days=1)
    rows = []
    for bid, p in sorted(FW.weather_points().items()):
        raw = FW._fetch(dict(latitude=f"{p['lat']:.5f}", longitude=f"{p['lon']:.5f}", start_date=start.isoformat(),
                             end_date=need_end.isoformat(), daily=','.join(FW.DAILY_VARS), timezone=FW.TZ))
        daily = json.loads(raw)['daily']
        for i, t in enumerate(daily['time']):
            vals = {v: daily[v][i] for v in FW.DAILY_VARS}
            if all(x is not None for x in vals.values()):
                rows.append(dict(point_id=bid, date=t, **vals))
    live = config.PROCESSED_DIR / 'weather_daily_live.csv'
    old = pd.read_csv(live) if live.exists() else pd.DataFrame()
    pd.concat([old, pd.DataFrame(rows)]).drop_duplicates(['point_id', 'date']).to_csv(live, index=False)


def redflag_for(issue: date) -> pd.DataFrame:
    from . import fetch_redflag as RF
    years = sorted({issue.year - 1, issue.year})
    ev = RF.events(years=years, refresh_years=(issue.year,) if issue.year >= datetime.now().year else ())
    cov = RF.coverage(RF.zone_geometries(ev))
    return RF.build_features([issue], ev, cov)


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Add A, E and candidate scores to a frame holding the feature columns."""
    df = external_test.score(df)          # clim + A + all original frozen models
    bundle = pickle.loads(BUNDLE.read_bytes())
    for name in (CAND,):
        df[name] = bundle['models'][name].predict_proba(df[SPECS[name]].to_numpy(float))[:, 1]
    return df


def build(issue: date, refresh_fires: bool = False) -> pd.DataFrame:
    if issue.weekday() != 0:
        raise SystemExit(f'{issue} is not a Monday; forecasts are issued on Mondays')
    if refresh_fires:
        from . import fetch_wfigs
        rows = fetch_wfigs.download(refresh=True)
        fires, audit = fetch_wfigs.clean(rows)
        pd.DataFrame(fires).to_csv(config.PROCESSED_DIR / 'wfigs_fires.csv', index=False)
    wf = external_test.load_wfigs()
    ensure_weather(issue)
    wx = external_test.weather_table_extended()
    lab = external_test.lattice(wf[wf['discovery_date'] < pd.Timestamp(issue)], [issue])
    lab = lab.drop(columns=['label', 'event_count'])
    df = pd.concat([lab, features.season(lab), features.location(lab),
                    features.history(lab, wf[wf['discovery_date'] < pd.Timestamp(issue)]),
                    features.weather(lab, wx)], axis=1)
    features.assert_no_leakage(df)
    rf = redflag_for(issue)
    df = df.merge(rf[['cell_id', 'forecast_date'] + REDFLAG_COLS], on=['cell_id', 'forecast_date'], how='left')
    df['label'] = 0           # placeholder required by shared helpers; outcomes unknown at issue
    df['event_count'] = 0
    return score_frame(df)


def write(df: pd.DataFrame, issue: date) -> dict:
    LIVE.mkdir(parents=True, exist_ok=True)
    out = df[['forecast_date', 'cell_id', 'centroid_lat', 'centroid_lon', 'weather_latest_date',
              'history_latest_date'] + REDFLAG_COLS].copy()
    for name, tag in TAGS:
        out[f'{tag}_risk_score'] = df[name].round(5)
        out[f'{tag}_rank'] = df[name].rank(ascending=False, method='first').astype(int)
    t = add_alerts(out)
    return save(out, issue, t, issued_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))


def save(out: pd.DataFrame, issue: date, t: dict, issued_utc: str, note: str | None = None) -> dict:
    stem = LIVE / f'forecast_{issue.isoformat()}'
    out.to_csv(stem.with_suffix('.csv'), index=False)
    cells = {c.cell_id: c for c in Grid().cells}
    feats = [dict(type='Feature', geometry=dict(type='Polygon', coordinates=[cells[r['cell_id']].polygon_lonlat()]),
                  properties={k: (v.isoformat() if hasattr(v, 'isoformat') else (bool(v) if isinstance(v, (bool, np.bool_)) else v))
                              for k, v in r.items() if k not in ('centroid_lat', 'centroid_lon')})
             for r in out.to_dict('records')]
    meta = dict(issue_date=issue.isoformat(), window=f'{issue} to {issue + timedelta(days=6)}', issued_utc=issued_utc,
                meaning='Risk of at least one newly reported wildfire in each ~25 km cell during the 7-day window. '
                        'A cell is alerted when its risk clears the model threshold chosen on 2021-2022 validation, '
                        f'so the number of alerts varies week to week (default rule {t["default_rule"]}).',
                alert_rules=t['rules'], default_rule=t['default_rule'], thresholds=t['thresholds'],
                models={'baseline': BASELINE, 'ember': HEADLINE, 'candidate': CAND})
    if note:
        meta['note'] = note
    stem.with_suffix('.geojson').write_text(json.dumps(dict(type='FeatureCollection', **meta, features=feats), default=str))
    alerts = {tag: out.loc[out[f'{tag}_alert'], 'cell_id'].tolist() for _, tag in TAGS}
    return dict(**{k: v for k, v in meta.items() if k != 'thresholds'}, alerts=alerts,
                alert_counts_by_rule={tag: {r: int(out[f'{tag}_alert_{r}'].sum()) for r in t['rules']
                                            if f'{tag}_alert_{r}' in out} for _, tag in TAGS},
                files=[str(stem.with_suffix('.csv')), str(stem.with_suffix('.geojson'))])


def reflag(issue: date) -> dict:
    """Re-derive variable alerts on a saved forecast from its saved scores (no re-scoring, no new data)."""
    out = pd.read_csv(LIVE / f'forecast_{issue.isoformat()}.csv')
    out = out[[c for c in out.columns if '_alert' not in c]]
    gj = json.loads((LIVE / f'forecast_{issue.isoformat()}.geojson').read_text())
    t = add_alerts(out)
    return save(out, issue, t, issued_utc=gj['issued_utc'],
                note=f'Scores issued {gj["issued_utc"]}; alert flags re-derived from those saved scores on '
                     f'{datetime.now(timezone.utc).isoformat(timespec="seconds")} with validation thresholds '
                     '(originally flagged as a fixed top 8; see git history).')


def score_outcomes(issue: date) -> dict:
    """After the week has passed: compare a saved forecast with WFIGS reports (refresh the feed first)."""
    f = pd.read_csv(LIVE / f'forecast_{issue.isoformat()}.csv')
    wf = external_test.load_wfigs()
    end = pd.Timestamp(issue) + pd.Timedelta(days=6)
    week = wf[(wf['discovery_date'] >= pd.Timestamp(issue)) & (wf['discovery_date'] <= end)]
    hit = set(week['cell_id'])
    res = {}
    for _, tag in TAGS:
        for col in [c for c in f.columns if c.startswith(f'{tag}_alert_')]:
            a = f[col].astype(bool)
            res[col] = dict(alerts=int(a.sum()), hits=int(f.loc[a, 'cell_id'].isin(hit).sum()),
                            fire_cells_missed=int(len(hit - set(f.loc[a, 'cell_id']))))
    return dict(issue_date=issue.isoformat(), reported_fires=int(len(week)), cells_with_fire=len(hit), results=res,
                feed_downloaded_note='WFIGS is live; rerun after late reports settle (about two weeks).')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--date', required=True, help='Monday issue date YYYY-MM-DD')
    ap.add_argument('--refresh-fires', action='store_true', help='re-download the live WFIGS feed first')
    ap.add_argument('--score-outcomes', action='store_true', help='score a saved forecast against WFIGS reports')
    ap.add_argument('--reflag', action='store_true', help='recompute alert flags of a saved forecast from its scores')
    a = ap.parse_args()
    issue = date.fromisoformat(a.date)
    if a.reflag:
        print(json.dumps(reflag(issue), indent=2, default=str))
        return
    if a.score_outcomes:
        print(json.dumps(score_outcomes(issue), indent=2))
        return
    print(json.dumps(write(build(issue, a.refresh_fires), issue), indent=2, default=str))


if __name__ == '__main__':
    main()
