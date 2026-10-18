"""Overnight candidate (E0+redflag): fit, save, and the single pre-registered 2025 test.

  python3 -m forecasting.candidate fit     # train 2015-2020, save outputs/candidate_v2.pkl
  python3 -m forecasting.candidate test    # PREREG_2025_v2.md, run once

The fitted bundle is also what ``forecasting.predict`` uses for new issue dates.
"""
from __future__ import annotations

import argparse
import json
import pickle
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from . import config, external_test, models
from .evaluate import BASELINE, HEADLINE
from .experiments import (BASE_COLS, GBM, REDFLAG_COLS, base_frame, budget_stats, paired_precision,
                          weekly_top)
from .features import HISTORY_COLS

BUNDLE = config.OUTPUT_DIR / 'candidate_v2.pkl'
CAND, CTRL = 'E0+redflag', 'E0_control'
SPECS = {CAND: BASE_COLS + HISTORY_COLS + REDFLAG_COLS, CTRL: BASE_COLS + HISTORY_COLS}


def redflag_table() -> pd.DataFrame:
    return pd.read_csv(config.PROCESSED_DIR / 'redflag_features.csv', parse_dates=['forecast_date'])


def fit() -> dict:
    df = base_frame().merge(redflag_table()[['cell_id', 'forecast_date'] + REDFLAG_COLS],
                            on=['cell_id', 'forecast_date'], how='left')
    tr = df['split'] == 'train'
    bundle = dict(version='v2-overnight', trained_on='FPA-FOD labels, issue dates 2015-2020',
                  gbm_params=GBM, seed=models.SEED, specs=SPECS, models={},
                  climatology=external_test.frozen_climatology(),
                  built_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    for name, cols in SPECS.items():
        m = HistGradientBoostingClassifier(random_state=models.SEED, early_stopping=False, **GBM)
        bundle['models'][name] = m.fit(df.loc[tr, cols].to_numpy(float), df.loc[tr, 'label'].to_numpy())
    # Reproduce the logged validation numbers as a check.
    va = df[df['split'] == 'validation'].copy()
    for name, cols in SPECS.items():
        va[name] = bundle['models'][name].predict_proba(va[cols].to_numpy(float))[:, 1]
    bundle['validation'] = {n: budget_stats(va, n) for n in SPECS}
    BUNDLE.write_bytes(pickle.dumps(bundle))
    print(json.dumps(bundle['validation'], indent=1))
    return bundle


def confusion(df: pd.DataFrame, score: str) -> dict:
    flag = df.index.isin(weekly_top(df, score).index)
    y = df['label'].to_numpy().astype(bool)
    return dict(TP=int((flag & y).sum()), FP=int((flag & ~y).sum()), FN=int((~flag & y).sum()),
                TN=int((~flag & ~y).sum()))


def test() -> dict:
    bundle = pickle.loads(BUNDLE.read_bytes())
    wf = external_test.load_wfigs()
    wx = external_test.weather_table_extended()
    issues = external_test.mondays(date(2025, 1, 6), date(2025, 12, 22))
    df = external_test.score(external_test.build_frame(issues, wf, wf, wx))  # adds clim, A, E (frozen)
    df = df.merge(redflag_table()[['cell_id', 'forecast_date'] + REDFLAG_COLS], on=['cell_id', 'forecast_date'],
                  how='left')
    assert df[REDFLAG_COLS].notna().all().all(), 'Red Flag features missing for 2025'
    for name, cols in SPECS.items():
        df[name] = bundle['models'][name].predict_proba(df[cols].to_numpy(float))[:, 1]
    names = [BASELINE, CTRL, HEADLINE, CAND]
    out = dict(prereg='PREREG_2025_v2.md', weeks=int(df['forecast_date'].nunique()), cell_weeks=int(len(df)),
               fire_cell_weeks=int(df['label'].sum()), fires=int(df['event_count'].sum()),
               base_rate=round(float(df['label'].mean()), 4),
               models={n: dict(**budget_stats(df, n), **confusion(df, n)) for n in names},
               comparisons=[paired_precision(df, BASELINE, CAND), paired_precision(df, CTRL, CAND),
                            paired_precision(df, HEADLINE, CAND), paired_precision(df, BASELINE, HEADLINE)],
               run_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    keep = ['forecast_date', 'cell_id', 'centroid_lat', 'centroid_lon', 'label', 'event_count'] + names + REDFLAG_COLS
    df[keep].to_csv(config.OUTPUT_DIR / 'candidate_2025_predictions.csv', index=False, float_format='%.6f')
    (config.OUTPUT_DIR / 'candidate_2025.json').write_text(json.dumps(out, indent=2))
    for n, s in out['models'].items():
        print(f"  {n:24s} alerts {s['alerts']} hits {s['hits']} precision {s['precision']:.4f} "
              f"capture {s['event_capture']:.4f} recall {s['cellweek_recall']:.4f} PR-AUC {s['pr_auc']:.4f}")
    for c in out['comparisons']:
        print(f"  {c['candidate']} - {c['baseline']}: {c['diff']:+.4f} {c['ci95']} P<=0 {c['p_le_zero']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('step', choices=['fit', 'test'])
    {'fit': fit, 'test': test}[ap.parse_args().step]()


if __name__ == '__main__':
    main()
