"""Audit the saved forecasts without retraining or changing any model.

1. Reproduce every reported holdout metric from ``holdout_predictions.csv`` alone.
2. Re-score all splits from ``models.pkl`` and confirm the holdout scores match.
3. Equal-budget comparison: same number of most-confident calls per model.
4. Season split, and confident calls versus what climatology already expected.
5. Confusion matrices at fixed, pre-stated decision rules.
6. Feature timestamp audit over every row of ``features.csv``.

Writes ``outputs/audit.json`` and the readable ``outputs/AUDIT.md``.
Usage: python3 -m forecasting.evaluate
"""
from __future__ import annotations

import gzip
import json
import pickle
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config, metrics, models

HEADLINE, BASELINE = 'E_gbm_history_weather', 'A_climatology'
SEASONS = {12: 'Winter (Dec-Feb)', 1: 'Winter (Dec-Feb)', 2: 'Winter (Dec-Feb)',
           3: 'Spring (Mar-May)', 4: 'Spring (Mar-May)', 5: 'Spring (Mar-May)',
           6: 'Summer (Jun-Aug)', 7: 'Summer (Jun-Aug)', 8: 'Summer (Jun-Aug)',
           9: 'Autumn (Sep-Nov)', 10: 'Autumn (Sep-Nov)', 11: 'Autumn (Sep-Nov)'}
N_BOOT = 2000


def wide(pred: pd.DataFrame) -> pd.DataFrame:
    """One row per cell-week with a score column per model."""
    w = pred.pivot_table(index=['forecast_date', 'cell_id', 'observed_fire', 'event_count'],
                         columns='model_name', values='risk_score').reset_index()
    w.columns.name = None
    w = w.rename(columns={'observed_fire': 'label'})
    w['month'] = pd.to_datetime(w['forecast_date']).dt.to_period('M').astype(str)
    w['season'] = pd.to_datetime(w['forecast_date']).dt.month.map(SEASONS)
    return w


# ------------------------------------------------------------ 1. reproduction

def reproduce(pred: pd.DataFrame) -> dict:
    saved = json.loads((config.OUTPUT_DIR / 'metrics.json').read_text())['results']['holdout']
    out = {}
    for name, g in pred.groupby('model_name'):
        r = metrics.summary(g.rename(columns={'observed_fire': 'label'}), 'risk_score')
        diffs = {k: round(abs(r[k] - saved[name][k]), 6) for k in r if k in saved[name] and isinstance(r[k], (int, float))}
        out[name] = dict(max_abs_diff=max(diffs.values()), recomputed_top10=r['top10_capture'])
    return out


# ------------------------------------------------------------ 2. rescore all splits

def rescore_all() -> tuple[pd.DataFrame, float]:
    fitted = pickle.loads((config.OUTPUT_DIR / 'models.pkl').read_bytes())
    df = pd.read_csv(config.PROCESSED_DIR / 'features.csv', parse_dates=['forecast_date'])
    df = models.add_climatology_feature(df)
    rows = [df.assign(model_name=BASELINE, risk_score=df['clim_full_train'])]
    for name, f in fitted.items():
        rows.append(df.assign(model_name=name,
                              risk_score=f['model'].predict_proba(models.design(df, f['spec'], f['cells']))[:, 1]))
    allp = pd.concat(rows, ignore_index=True)
    allp = allp[['forecast_date', 'split', 'cell_id', 'centroid_lat', 'centroid_lon', 'model_name', 'risk_score',
                 'label', 'event_count']]
    allp['forecast_date'] = allp['forecast_date'].dt.date.astype(str)
    hold = pd.read_csv(config.OUTPUT_DIR / 'holdout_predictions.csv', dtype={'forecast_date': str})
    m = hold.merge(allp, on=['forecast_date', 'cell_id', 'model_name'], suffixes=('_saved', '_rescored'))
    assert len(m) == len(hold), 'rescored predictions do not cover the saved holdout'
    return allp, float((m['risk_score_saved'] - m['risk_score_rescored']).abs().max())


# ------------------------------------------------------------ 3. equal budget

def topn_hits(scores: np.ndarray, labels: np.ndarray, n: int) -> float:
    """Expected positives among the n highest scores, ties at the cut shared fractionally."""
    return metrics.week_capture(scores, labels.astype(float), n)


def equal_budget(w: pd.DataFrame, a: str, b: str, budgets: list[int]) -> list[dict]:
    rng = np.random.default_rng(0)
    months = w['month'].unique()
    by_month = {m: g for m, g in w.groupby('month')}
    total_pos = int(w['label'].sum())
    out = []
    for n in budgets:
        frac = n / len(w)
        ha = topn_hits(w[a].to_numpy(), w['label'].to_numpy(), n)
        hb = topn_hits(w[b].to_numpy(), w['label'].to_numpy(), n)
        diffs = np.empty(N_BOOT)
        for i in range(N_BOOT):
            s = pd.concat([by_month[m] for m in rng.choice(months, len(months))])
            k = max(1, round(frac * len(s)))
            diffs[i] = (topn_hits(s[b].to_numpy(), s['label'].to_numpy(), k) -
                        topn_hits(s[a].to_numpy(), s['label'].to_numpy(), k)) / k
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        out.append(dict(budget=n, budget_share=round(frac, 4),
                        **{f'{a}_hit_rate': round(ha / n, 4), f'{b}_hit_rate': round(hb / n, 4),
                           f'{a}_share_of_fire_cell_weeks': round(ha / total_pos, 4),
                           f'{b}_share_of_fire_cell_weeks': round(hb / total_pos, 4)},
                        diff_hit_rate=round((hb - ha) / n, 4), ci95=[round(lo, 4), round(hi, 4)],
                        p_le_zero=round(float((diffs <= 0).mean()), 4)))
    return out


# ------------------------------------------------------------ 4. seasons and excess over climatology

def season_table(w: pd.DataFrame) -> list[dict]:
    out = []
    for season, g in w.groupby('season'):
        row = dict(season=season, weeks=int(g['forecast_date'].nunique()), cell_weeks=int(len(g)),
                   fires=int(g['event_count'].sum()), fire_cell_weeks=int(g['label'].sum()),
                   base_rate=round(float(g['label'].mean()), 4))
        for name, tag in ((HEADLINE, 'E'), (BASELINE, 'A')):
            row[f'{tag}_top10_capture'] = round(metrics.topk_capture(g, name, 0.10)['capture'], 4)
            top = top8(g, name)
            row[f'{tag}_top8_hit_rate'] = round(float(top['label'].mean()), 4)
        # What climatology expected in E's top-8 picks, versus what happened.
        topE = top8(g, HEADLINE)
        row['E_top8_expected_by_climatology'] = round(float(topE[BASELINE].mean()), 4)
        row['E_top8_excess_hit_rate'] = round(float(topE['label'].mean() - topE[BASELINE].mean()), 4)
        boot = metrics.block_bootstrap_diff(g, BASELINE, HEADLINE, 0.10, n_boot=N_BOOT)
        row['E_minus_A_top10'] = boot['diff']
        row['E_minus_A_top10_ci95'] = boot['ci95']
        out.append(row)
    order = ['Winter (Dec-Feb)', 'Spring (Mar-May)', 'Summer (Jun-Aug)', 'Autumn (Sep-Nov)']
    return sorted(out, key=lambda r: order.index(r['season']))


def top8(g: pd.DataFrame, score: str) -> pd.DataFrame:
    k = max(1, round(0.10 * g.groupby('forecast_date').size().iloc[0]))
    r = g.groupby('forecast_date')[score].rank(ascending=False, method='first')
    return g[r <= k]


def confident_calls(w: pd.DataFrame, threshold: float = 0.7) -> dict:
    out = {}
    for name in (HEADLINE, BASELINE):
        c = w[w[name] >= threshold]
        out[name] = dict(threshold=threshold, calls=int(len(c)), hit_rate=round(float(c['label'].mean()), 4),
                         climatology_expected_rate=round(float(c[BASELINE].mean()), 4),
                         excess_over_climatology=round(float(c['label'].mean() - c[BASELINE].mean()), 4),
                         share_in_jun_sep=round(float(pd.to_datetime(c['forecast_date']).dt.month.between(6, 9).mean()), 4),
                         distinct_cells=int(c['cell_id'].nunique()),
                         share_from_top10_busiest_cells=None)
        busiest = w.groupby('cell_id')[BASELINE].mean().nlargest(10).index
        out[name]['share_from_top10_busiest_cells'] = round(float(c['cell_id'].isin(busiest).mean()), 4)
    return out


# ------------------------------------------------------------ 5. confusion matrices

def confusion(w: pd.DataFrame) -> list[dict]:
    rules = {'top 8 cells per week (10%)': lambda g, s: g.groupby('forecast_date')[s].rank(ascending=False, method='first') <= 8,
             'score >= 0.5': lambda g, s: g[s] >= 0.5,
             'score >= 0.7': lambda g, s: g[s] >= 0.7}
    out = []
    for rule, f in rules.items():
        for name in (HEADLINE, BASELINE):
            flag = f(w, name).to_numpy()
            y = w['label'].to_numpy().astype(bool)
            tp, fp = int((flag & y).sum()), int((flag & ~y).sum())
            fn, tn = int((~flag & y).sum()), int((~flag & ~y).sum())
            out.append(dict(rule=rule, model=name, TP=tp, FP=fp, FN=fn, TN=tn,
                            precision=round(tp / max(tp + fp, 1), 4), recall=round(tp / max(tp + fn, 1), 4),
                            specificity=round(tn / max(tn + fp, 1), 4), flagged=tp + fp))
    return out


# ------------------------------------------------------------ 6. feature timestamps

def timestamp_audit() -> dict:
    f = pd.read_csv(config.PROCESSED_DIR / 'features.csv',
                    usecols=['forecast_date', 'weather_cutoff', 'weather_latest_date', 'history_latest_date', 'split'],
                    parse_dates=['forecast_date', 'weather_cutoff', 'weather_latest_date', 'history_latest_date'])
    wgap = (f['forecast_date'] - f['weather_latest_date']).dt.days
    hgap = (f['forecast_date'] - f['history_latest_date']).dt.days
    info = json.loads((config.PROCESSED_DIR / 'features_info.json').read_text())
    return dict(rows=int(len(f)),
                weather_gap_days=dict(min=int(wgap.min()), max=int(wgap.max()), required_min=config.WEATHER_LAG_DAYS,
                                      violations=int((wgap < config.WEATHER_LAG_DAYS).sum())),
                history_gap_days=dict(min=int(hgap.min()), max=int(hgap.max()), required_min=1,
                                      violations=int((hgap < 1).sum())),
                weather_cutoff_equals_latest=bool((f['weather_cutoff'] == f['weather_latest_date']).all()),
                windows=dict(weather='trailing 7/14/30/90 days ending at issue_date - 7 (inclusive)',
                             history='discoveries in [issue_date - N, issue_date - 1], N in 30/90/365',
                             season='day-of-year of window midpoint (known in advance)',
                             location='static cell centroid; climatology from training years only'),
                weather_features=info['weather_cols'], history_features=info['history_cols'],
                excluded_inputs=['fire_size', 'fire_size_class', 'cause', 'containment date', 'any forecast-window data'])


# ------------------------------------------------------------ report

def pct(x):
    return f'{100 * x:.1f}%'


def write_report(a: dict) -> None:
    L = ['# EMBER forecast audit', '',
         f"Generated {a['generated_utc']} by `python3 -m forecasting.evaluate`. Reads saved predictions and models only; nothing was retrained or tuned.",
         f'Holdout: 2023-2024, {a["holdout_weeks"]} weeks, {a["holdout_cell_weeks"]} cell-weeks, '
         f'{a["holdout_fire_cell_weeks"]} with a reported fire ({pct(a["holdout_base_rate"])}).', '',
         '## 1. Reproducibility', '']
    L += [f'- Holdout metrics recomputed from `holdout_predictions.csv`: largest difference from `metrics.json` = '
          f'{max(v["max_abs_diff"] for v in a["reproduce"].values()):.6f} (rounding only).',
          f'- All splits re-scored from `models.pkl`: largest difference from saved holdout scores = {a["rescore_max_abs_diff"]:.2e}.',
          f'- Prediction-level file for every split and model: `all_predictions.csv.gz` ({a["all_predictions_rows"]:,} rows).', '',
          '## 2. Equal-budget comparison', '',
          'Each model gets the same number of most-confident cell-week calls over the whole holdout. '
          'CIs: calendar-month block bootstrap.', '',
          '| Calls (share of cell-weeks) | Weather model E hit rate | Climatology A hit rate | E - A | 95% CI | E share of fire cell-weeks caught | A share |',
          '|---|---|---|---|---|---|---|']
    for r in a['equal_budget']:
        L.append(f"| {r['budget']} ({pct(r['budget_share'])}) | {pct(r[HEADLINE + '_hit_rate'])} | {pct(r[BASELINE + '_hit_rate'])} | "
                 f"{100 * r['diff_hit_rate']:+.1f} pt | [{100 * r['ci95'][0]:+.1f}, {100 * r['ci95'][1]:+.1f}] | "
                 f"{pct(r[HEADLINE + '_share_of_fire_cell_weeks'])} | {pct(r[BASELINE + '_share_of_fire_cell_weeks'])} |")
    L += ['', '## 3. By season', '',
          '| Season | Weeks | Fires | Base rate | E top-10% capture | A top-10% capture | E - A (95% CI) | E top-8 hit rate | Climatology expected for those picks | Excess |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for r in a['seasons']:
        L.append(f"| {r['season']} | {r['weeks']} | {r['fires']} | {pct(r['base_rate'])} | {pct(r['E_top10_capture'])} | "
                 f"{pct(r['A_top10_capture'])} | {100 * r['E_minus_A_top10']:+.1f} pt [{100 * r['E_minus_A_top10_ci95'][0]:+.1f}, "
                 f"{100 * r['E_minus_A_top10_ci95'][1]:+.1f}] | {pct(r['E_top8_hit_rate'])} | "
                 f"{pct(r['E_top8_expected_by_climatology'])} | {100 * r['E_top8_excess_hit_rate']:+.1f} pt |")
    L += ['', '## 4. High-confidence calls (score >= 0.7) versus climatology', '',
          '| Model | Calls | Hit rate | Climatology expected | Excess | Share in Jun-Sep | Distinct cells | Share from the 10 busiest cells |',
          '|---|---|---|---|---|---|---|---|']
    for name, r in a['confident_calls'].items():
        L.append(f"| {name} | {r['calls']} | {pct(r['hit_rate'])} | {pct(r['climatology_expected_rate'])} | "
                 f"{100 * r['excess_over_climatology']:+.1f} pt | {pct(r['share_in_jun_sep'])} | {r['distinct_cells']} | "
                 f"{pct(r['share_from_top10_busiest_cells'])} |")
    L += ['', '"Climatology expected" = mean training-period seasonal fire rate (model A score) for the same cell-weeks. '
          'Excess near zero means the confident calls mostly identify cells that burn every season.', '',
          '## 5. Confusion matrices (holdout cell-weeks)', '',
          '| Rule | Model | Flagged | TP | FP | FN | TN | Precision | Recall | Specificity |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for r in a['confusion']:
        L.append(f"| {r['rule']} | {r['model']} | {r['flagged']} | {r['TP']} | {r['FP']} | {r['FN']} | {r['TN']} | "
                 f"{pct(r['precision'])} | {pct(r['recall'])} | {pct(r['specificity'])} |")
    t = a['timestamp_audit']
    L += ['', '## 6. Feature timestamp audit', '',
          f"- Rows checked: {t['rows']:,} (all splits).",
          f"- Issue date minus latest weather day: min {t['weather_gap_days']['min']}, max {t['weather_gap_days']['max']} days "
          f"(required >= {t['weather_gap_days']['required_min']}); violations: {t['weather_gap_days']['violations']}.",
          f"- Issue date minus latest fire-history day: min {t['history_gap_days']['min']}, max {t['history_gap_days']['max']} "
          f"(required >= 1); violations: {t['history_gap_days']['violations']}.",
          f"- Weather windows: {t['windows']['weather']}. History windows: {t['windows']['history']}.",
          f"- Never used as inputs: {', '.join(t['excluded_inputs'])}.", '']
    (config.OUTPUT_DIR / 'AUDIT.md').write_text('\n'.join(L))


def main() -> None:
    pred = pd.read_csv(config.OUTPUT_DIR / 'holdout_predictions.csv', dtype={'forecast_date': str})
    w = wide(pred)
    allp, rescore_diff = rescore_all()
    with gzip.open(config.OUTPUT_DIR / 'all_predictions.csv.gz', 'wt', newline='') as fh:
        allp.to_csv(fh, index=False, float_format='%.6f')
    total_pos = int(w['label'].sum())
    a = dict(generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
             holdout_weeks=int(w['forecast_date'].nunique()), holdout_cell_weeks=int(len(w)),
             holdout_fire_cell_weeks=total_pos, holdout_base_rate=float(w['label'].mean()),
             reproduce=reproduce(pred), rescore_max_abs_diff=rescore_diff, all_predictions_rows=int(len(allp)),
             equal_budget=equal_budget(w, BASELINE, HEADLINE,
                                       [276, 449, 786, 832, round(0.2 * len(w))]),
             seasons=season_table(w), confident_calls=confident_calls(w),
             confusion=confusion(w), timestamp_audit=timestamp_audit())
    (config.OUTPUT_DIR / 'audit.json').write_text(json.dumps(a, indent=2))
    write_report(a)
    print((config.OUTPUT_DIR / 'AUDIT.md').read_text())


if __name__ == '__main__':
    main()
