"""Train, select on validation, then evaluate once on the frozen 2023-2024 holdout.

Ablation (all fit on 2015-2020 issue dates only):
  A  climatology        smoothed cell x week-of-year ignition rate (training years)
  B  logit_season_loc   logistic: season harmonics + cell one-hot
  C  logit_weather      B + lagged weather
  D0 gbm_season_loc     gradient boosting: season + location + climatology (no weather)
  D  gbm_weather        D0 + lagged weather
  E0 gbm_history        D0 + prior fire counts (no weather)
  E  gbm_history_weather E0 + lagged weather

Usage: python3 -m forecasting.models
"""
from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config, metrics
from .features import HISTORY_COLS, LOCATION_COLS, SEASON_COLS

MODEL_VERSION = '0.1.0'
SEED = 20261018
CLIM_HALF_WIDTH = 2      # +/- weeks pooled around each week-of-year
CLIM_PRIOR_STRENGTH = 10.0


def weather_cols(df: pd.DataFrame) -> list[str]:
    info = json.loads((config.PROCESSED_DIR / 'features_info.json').read_text())
    return [c for c in info['weather_cols'] if c in df.columns]


# ---------------------------------------------------------------- climatology

def fit_climatology(train: pd.DataFrame) -> pd.DataFrame:
    """Smoothed P(label | cell, week-of-year) from the given rows only."""
    weeks = np.arange(1, 53)
    g = train.groupby(['cell_id', 'week_of_year'])['label'].agg(['sum', 'count'])
    cells = sorted(train['cell_id'].unique())
    s = g['sum'].unstack(fill_value=0).reindex(index=cells, columns=weeks, fill_value=0).to_numpy(float)
    n = g['count'].unstack(fill_value=0).reindex(index=cells, columns=weeks, fill_value=0).to_numpy(float)
    # circular +/- CLIM_HALF_WIDTH pooling over week-of-year
    S = sum(np.roll(s, k, axis=1) for k in range(-CLIM_HALF_WIDTH, CLIM_HALF_WIDTH + 1))
    N = sum(np.roll(n, k, axis=1) for k in range(-CLIM_HALF_WIDTH, CLIM_HALF_WIDTH + 1))
    season = S.sum(0) / np.maximum(N.sum(0), 1)                    # regional seasonal profile
    cell_rel = (s.sum(1) / np.maximum(n.sum(1), 1)) / max(train['label'].mean(), 1e-9)
    prior = np.clip(season[None, :] * cell_rel[:, None], 1e-4, 0.999)
    rate = (S + CLIM_PRIOR_STRENGTH * prior) / (N + CLIM_PRIOR_STRENGTH)
    return pd.DataFrame(rate, index=pd.Index(cells, name='cell_id'), columns=weeks)


def apply_climatology(table: pd.DataFrame, df: pd.DataFrame) -> np.ndarray:
    return table.stack().reindex(pd.MultiIndex.from_arrays([df['cell_id'], df['week_of_year']])).to_numpy()


def add_climatology_feature(df: pd.DataFrame) -> pd.DataFrame:
    """``clim`` for every row, from training years only.

    Training rows get a leave-one-year-out estimate so the feature never
    contains the row's own label; validation/holdout rows use all training years.
    """
    df = df.copy()
    train = df[df['split'] == 'train']
    df['clim'] = np.nan
    years = pd.to_datetime(df['forecast_date']).dt.year
    for y in sorted(years[df['split'] == 'train'].unique()):
        tab = fit_climatology(train[pd.to_datetime(train['forecast_date']).dt.year != y])
        m = (df['split'] == 'train') & (years == y)
        df.loc[m, 'clim'] = apply_climatology(tab, df[m])
    full = fit_climatology(train)
    m = df['split'] != 'train'
    df.loc[m, 'clim'] = apply_climatology(full, df[m])
    df['clim_full_train'] = apply_climatology(full, df)   # model A's score (in-sample on train rows)
    return df


# ---------------------------------------------------------------- model specs

def specs(wcols: list[str]) -> dict:
    base_gbm = SEASON_COLS + LOCATION_COLS + ['clim']
    return {
        'B_logit_season_loc': dict(kind='logit', num=SEASON_COLS, cell_onehot=True),
        'C_logit_weather': dict(kind='logit', num=SEASON_COLS + wcols, cell_onehot=True),
        'D0_gbm_season_loc': dict(kind='gbm', num=base_gbm),
        'D_gbm_weather': dict(kind='gbm', num=base_gbm + wcols),
        'E0_gbm_history': dict(kind='gbm', num=base_gbm + HISTORY_COLS),
        'E_gbm_history_weather': dict(kind='gbm', num=base_gbm + HISTORY_COLS + wcols),
    }


LOGIT_GRID = [dict(C=c) for c in (0.01, 0.1, 1.0)]
GBM_GRID = [dict(learning_rate=0.05, max_iter=300, max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=1.0),
            dict(learning_rate=0.05, max_iter=300, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0),
            dict(learning_rate=0.03, max_iter=500, max_leaf_nodes=15, min_samples_leaf=300, l2_regularization=3.0)]


def design(df: pd.DataFrame, spec: dict, cells: list[str]) -> np.ndarray:
    X = df[spec['num']].to_numpy(float)
    if spec.get('cell_onehot'):
        oh = (df['cell_id'].to_numpy()[:, None] == np.array(cells)[None, :]).astype(float)
        X = np.hstack([X, oh])
    return X


def make_model(spec: dict, params: dict):
    if spec['kind'] == 'logit':
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, **params))
    return HistGradientBoostingClassifier(random_state=SEED, early_stopping=False, **params)


def fit_select(df: pd.DataFrame, name: str, spec: dict, cells: list[str]) -> tuple:
    """Fit each config on train, choose by validation top-10% capture (PR-AUC tie-break)."""
    tr, va = df[df['split'] == 'train'], df[df['split'] == 'validation']
    Xtr, Xva = design(tr, spec, cells), design(va, spec, cells)
    trials = []
    for params in (LOGIT_GRID if spec['kind'] == 'logit' else GBM_GRID):
        m = make_model(spec, params).fit(Xtr, tr['label'].to_numpy())
        p = m.predict_proba(Xva)[:, 1]
        v = va.assign(_s=p)
        cap = metrics.topk_capture(v, '_s', 0.10)['capture']
        pr = metrics.summary(v, '_s')['pr_auc']
        trials.append(dict(params=params, val_top10_capture=round(cap, 4), val_pr_auc=pr, model=m))
        print(f'  {name} {params}: val top10 {cap:.4f}  PR-AUC {pr:.4f}', flush=True)
    best = max(trials, key=lambda t: (t['val_top10_capture'], t['val_pr_auc']))
    return best['model'], best['params'], [{k: v for k, v in t.items() if k != 'model'} for t in trials]


# ---------------------------------------------------------------- pipeline

def run(df: pd.DataFrame, use_weather: bool = True) -> dict:
    df = add_climatology_feature(df)
    cells = sorted(df['cell_id'].unique())
    wcols = weather_cols(df) if use_weather else []
    if use_weather:
        missing = df[wcols].isna().any(axis=1)
        assert not missing.any(), f'{int(missing.sum())} rows lack weather; rerun fetch_weather'
    all_specs = specs(wcols)
    if not use_weather:
        all_specs = {k: v for k, v in all_specs.items() if 'weather' not in k}

    scores = {'A_climatology': df['clim_full_train'].to_numpy()}
    selection, fitted = {}, {}
    for name, spec in all_specs.items():
        model, params, trials = fit_select(df, name, spec, cells)
        scores[name] = model.predict_proba(design(df, spec, cells))[:, 1]
        selection[name] = dict(chosen=params, trials=trials, features=spec['num'],
                               cell_onehot=bool(spec.get('cell_onehot')))
        fitted[name] = dict(model=model, spec=spec, cells=cells)
    for k, v in scores.items():
        df[f'score_{k}'] = v

    results = {}
    for split in ('train', 'validation', 'holdout'):
        part = df[df['split'] == split]
        results[split] = {k: metrics.summary(part, f'score_{k}') for k in scores}
    hold = df[df['split'] == 'holdout']
    tests = []
    pairs = [('A_climatology', 'B_logit_season_loc'), ('B_logit_season_loc', 'C_logit_weather'),
             ('D0_gbm_season_loc', 'D_gbm_weather'), ('E0_gbm_history', 'E_gbm_history_weather'),
             ('A_climatology', 'E_gbm_history_weather'), ('A_climatology', 'E0_gbm_history'),
             ('A_climatology', 'D_gbm_weather')]
    for a, b in pairs:
        if a in scores and b in scores:
            t = metrics.block_bootstrap_diff(hold, f'score_{a}', f'score_{b}', 0.10)
            t.update(baseline=a, candidate=b)
            tests.append(t)
    reliab = {k: metrics.reliability(hold, f'score_{k}') for k in scores}
    return dict(df=df, results=results, tests=tests, selection=selection, fitted=fitted, reliability=reliab,
                weather_cols=wcols)


def save(out: dict) -> None:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = out['df']
    hold = df[df['split'] == 'holdout']
    rows = []
    for k in [c[len('score_'):] for c in df.columns if c.startswith('score_')]:
        rows.append(pd.DataFrame({
            'forecast_date': pd.to_datetime(hold['forecast_date']).dt.date, 'horizon_days': hold['horizon_days'],
            'cell_id': hold['cell_id'], 'centroid_lat': hold['centroid_lat'], 'centroid_lon': hold['centroid_lon'],
            'risk_score': hold[f'score_{k}'].round(6), 'observed_fire': hold['label'],
            'event_count': hold['event_count'], 'model_name': k, 'model_version': MODEL_VERSION}))
    pd.concat(rows).to_csv(config.OUTPUT_DIR / 'holdout_predictions.csv', index=False)
    with open(config.OUTPUT_DIR / 'models.pkl', 'wb') as fh:
        pickle.dump(out['fitted'], fh)

    split_dates = {s: dict(first=str(pd.to_datetime(g['forecast_date']).min().date()),
                           last=str(pd.to_datetime(g['forecast_date']).max().date()))
                   for s, g in df.groupby('split')}
    payload = dict(
        generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'), model_version=MODEL_VERSION,
        target=('1 if >=1 FPA-FOD fire discovered in the cell during [issue_date, issue_date+6]; '
                '0 = zero reported fires (not proof of no fire)'),
        unit='25 km EPSG:3310 cell x Monday issue date', weather_lag_days=config.WEATHER_LAG_DAYS,
        splits=split_dates, fitted_on='train only (2015-2020); configs chosen on validation (2021-2022); holdout evaluated once',
        primary_metric='weekly top-10%-of-cells capture of reported fires (ties shared fractionally)',
        results=out['results'], holdout_significance=out['tests'], selection=out['selection'],
        holdout_reliability=out['reliability'], weather_features=out['weather_cols'],
        limitations=[
            'Scores are ranking risk scores; calibration is checked in holdout_reliability, not assumed.',
            'Label 0 means no reported fire; FPA-FOD is incomplete and discovery dates are date-only.',
            'Weather is retrospective reanalysis (Open-Meteo / ERA5 family), not a forecast archived at issue time; a 7-day lag reduces but does not remove look-ahead from later reanalysis revisions.',
            'Weather sampled at one point per ~50 km block (free-tier quota); cells share block weather.',
            'Fire-history features assume discoveries before the issue date were known by then; real reporting latency may be longer.',
            'Single region (N. California 39-41N); temporal holdout only, neighbouring cells are spatially correlated.',
            'Equal-area cells differ in burnable land, population and reporting intensity; lift is not equal-opportunity.',
        ])
    (config.OUTPUT_DIR / 'metrics.json').write_text(json.dumps(payload, indent=2, default=str))


def print_table(out: dict) -> None:
    for split in ('validation', 'holdout'):
        print(f'\n{split}:')
        print(f"  {'model':26s} {'top5':>7s} {'top10':>7s} {'top20':>7s} {'PR-AUC':>7s} {'ROC':>6s} {'Brier':>8s}")
        for k, r in out['results'][split].items():
            print(f"  {k:26s} {r['top5_capture']:7.4f} {r['top10_capture']:7.4f} {r['top20_capture']:7.4f} "
                  f"{r['pr_auc']:7.4f} {r['roc_auc']:6.3f} {r.get('brier', float('nan')):8.5f}")
    print('\nholdout top-10% capture differences (month-block bootstrap):')
    for t in out['tests']:
        print(f"  {t['candidate']} - {t['baseline']}: {t['diff']:+.4f}  95% CI {t['ci95']}  P(<=0)={t['p_le_zero']}")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--no-weather', action='store_true', help='baseline/history models only')
    args = ap.parse_args()
    df = pd.read_csv(config.PROCESSED_DIR / 'features.csv', parse_dates=['forecast_date'])
    out = run(df, use_weather=not args.no_weather)
    print_table(out)
    save(out)


if __name__ == '__main__':
    main()
