"""Threshold-based alerts: alert every cell-week whose risk clears a threshold.

The number of alerts varies week to week with the models' risk, instead of a
fixed 8 per week. Thresholds are chosen on 2021-2022 validation only, per model,
by three rules fixed before any test number was computed:

  best_f1      threshold maximising F1 (alert precision vs recall of fire cell-weeks)
  precision70  lowest threshold whose validation precision is >= 70%
  precision50  lowest threshold whose validation precision is >= 50%

Also reported: comparisons at an EQUAL TOTAL number of alerts (pooled over the
whole period, free to concentrate in risky weeks), and threshold-free measures
(PR-AUC, ROC-AUC, Brier). Test periods: 2025 (WFIGS labels) and 2023-2024
(FPA-FOD labels); both were used before, so these are additional readings of
frozen models, not new blind tests.

Usage: python3 -m forecasting.flexible_alerts
"""
from __future__ import annotations

import gzip
import json
import pickle

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from . import config
from .candidate import BUNDLE, CAND, CTRL, SPECS
from .evaluate import BASELINE, HEADLINE
from .experiments import REDFLAG_COLS, base_frame

MODELS = [BASELINE, HEADLINE, CAND]
NAMES = {BASELINE: 'Seasonal baseline (A)', HEADLINE: 'EMBER (E)', CAND: 'Overnight candidate (E0+redflag)'}
RULES = ['best_f1', 'precision70', 'precision50']
N_BOOT = 2000


# ------------------------------------------------------------------ data

def frames() -> dict[str, pd.DataFrame]:
    allp = pd.read_csv(gzip.open(config.OUTPUT_DIR / 'all_predictions.csv.gz'))
    wide = allp[allp['model_name'].isin([BASELINE, HEADLINE])].pivot_table(
        index=['forecast_date', 'cell_id', 'split', 'label', 'event_count'], columns='model_name',
        values='risk_score').reset_index()
    wide.columns.name = None
    # Candidate scores for validation and 2023-2024 from the saved bundle (no refit).
    bundle = pickle.loads(BUNDLE.read_bytes())
    f = pd.read_csv(config.PROCESSED_DIR / 'features.csv', parse_dates=['forecast_date'])
    from .models import add_climatology_feature
    f = add_climatology_feature(f)
    rf = pd.read_csv(config.PROCESSED_DIR / 'redflag_features.csv', parse_dates=['forecast_date'])
    f = f.merge(rf[['cell_id', 'forecast_date'] + REDFLAG_COLS], on=['cell_id', 'forecast_date'], how='left')
    f[CAND] = bundle['models'][CAND].predict_proba(f[SPECS[CAND]].to_numpy(float))[:, 1]
    f['forecast_date'] = f['forecast_date'].dt.date.astype(str)
    wide = wide.merge(f[['forecast_date', 'cell_id', CAND]], on=['forecast_date', 'cell_id'], how='left')
    assert wide[CAND].notna().all()
    t25 = pd.read_csv(config.OUTPUT_DIR / 'candidate_2025_predictions.csv')
    return {'validation 2021-2022': wide[wide['split'] == 'validation'].reset_index(drop=True),
            'test 2023-2024 (FPA-FOD)': wide[wide['split'] == 'holdout'].reset_index(drop=True),
            'test 2025 (WFIGS)': t25}


# ------------------------------------------------------------------ thresholds (validation only)

def choose_thresholds(val: pd.DataFrame, model: str) -> dict:
    s, y = val[model].to_numpy(), val['label'].to_numpy()
    order = np.argsort(-s)
    s_sorted, y_sorted = s[order], y[order]
    tp = np.cumsum(y_sorted)
    n = np.arange(1, len(s) + 1)
    # evaluate only at distinct score values (alert set = all scores >= threshold)
    last = np.r_[s_sorted[1:] != s_sorted[:-1], True]
    thr, prec, rec = s_sorted[last], (tp / n)[last], (tp / y.sum())[last]
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    out = {'best_f1': float(thr[np.argmax(f1)])}
    for target, name in ((0.70, 'precision70'), (0.50, 'precision50')):
        ok = np.where(prec >= target)[0]
        out[name] = float(thr[ok.max()]) if len(ok) else None   # lowest threshold still meeting target
    return out


# ------------------------------------------------------------------ evaluation

def alert_stats(df: pd.DataFrame, model: str, thr: float) -> dict:
    flag = df[model] >= thr
    y = df['label'] == 1
    per_week = flag.groupby(df['forecast_date']).sum()
    tp = int((flag & y).sum())
    a = int(flag.sum())
    prec = tp / a if a else float('nan')
    rec = tp / int(y.sum())
    return dict(threshold=round(thr, 4), alerts=a, hits=tp, precision=round(prec, 4), recall=round(rec, 4),
                f1=round(2 * prec * rec / (prec + rec), 4) if a and tp else 0.0,
                fire_capture=round(float(df.loc[flag, 'event_count'].sum() / df['event_count'].sum()), 4),
                alerts_per_week=dict(min=int(per_week.min()), median=float(per_week.median()), max=int(per_week.max())),
                weeks_with_no_alert=int((per_week == 0).sum()), weeks=int(len(per_week)))


def month_blocks(df: pd.DataFrame) -> np.ndarray:
    return pd.to_datetime(df['forecast_date']).dt.to_period('M').astype(str).to_numpy()


def boot_ci(stat, df: pd.DataFrame) -> list[float]:
    """Calendar-month block bootstrap of a statistic computed on a resampled frame."""
    rng = np.random.default_rng(0)
    m = month_blocks(df)
    groups = {k: np.where(m == k)[0] for k in np.unique(m)}
    keys = list(groups)
    vals = []
    for _ in range(N_BOOT):
        idx = np.concatenate([groups[k] for k in rng.choice(keys, len(keys))])
        v = stat(df.iloc[idx])
        if v == v:
            vals.append(v)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def threshold_diff(df: pd.DataFrame, a: str, ta: float, b: str, tb: float, metric: str) -> dict:
    def stat(d):
        sa, sb = alert_stats(d, a, ta), alert_stats(d, b, tb)
        return sb[metric] - sa[metric]
    return dict(metric=metric, diff=round(stat(df), 4), ci95=boot_ci(stat, df))


def equal_count(df: pd.DataFrame, a: str, b: str, n: int) -> dict:
    """Both models get the same n alerts, placed on their n highest-risk cell-weeks anywhere in the period."""
    def prec(d, model, k):
        return float(d.nlargest(k, model)['label'].mean())
    frac = n / len(df)

    def stat(d):
        k = max(1, round(frac * len(d)))
        return prec(d, b, k) - prec(d, a, k)
    pa, pb = prec(df, a, n), prec(df, b, n)
    return dict(alerts=n, share_of_cellweeks=round(frac, 4), precision_a=round(pa, 4), precision_b=round(pb, 4),
                diff=round(pb - pa, 4), ci95=boot_ci(stat, df))


def threshold_free(df: pd.DataFrame, model: str) -> dict:
    y, p = df['label'].to_numpy(), df[model].to_numpy()
    return dict(pr_auc=round(float(average_precision_score(y, p)), 4), roc_auc=round(float(roc_auc_score(y, p)), 4),
                brier=round(float(brier_score_loss(y, p)), 5), mean_risk=round(float(p.mean()), 4),
                observed_rate=round(float(y.mean()), 4))


def tf_diff(df: pd.DataFrame, a: str, b: str) -> dict:
    out = {}
    for name, fn in (('pr_auc', lambda d, m: average_precision_score(d['label'], d[m])),
                     ('roc_auc', lambda d, m: roc_auc_score(d['label'], d[m])),
                     ('brier', lambda d, m: brier_score_loss(d['label'], d[m]))):
        stat = lambda d: float(fn(d, b) - fn(d, a))
        out[name] = dict(diff=round(stat(df), 4), ci95=boot_ci(stat, df))
    return out


def main() -> None:
    F = frames()
    val = F['validation 2021-2022']
    thresholds = {m: choose_thresholds(val, m) for m in MODELS}
    res = dict(thresholds_chosen_on='validation 2021-2022', thresholds=thresholds, periods={})
    for period, df in F.items():
        r = dict(cell_weeks=int(len(df)), fire_cell_weeks=int(df['label'].sum()), base_rate=round(float(df['label'].mean()), 4),
                 threshold_free={m: threshold_free(df, m) for m in MODELS}, rules={}, equal_count={})
        for rule in RULES:
            r['rules'][rule] = {m: alert_stats(df, m, thresholds[m][rule]) for m in MODELS if thresholds[m][rule] is not None}
            if period != 'validation 2021-2022':
                r['rules'][rule]['comparisons'] = [
                    threshold_diff(df, BASELINE, thresholds[BASELINE][rule], m, thresholds[m][rule], met)
                    for m in (HEADLINE, CAND) for met in ('precision', 'recall', 'f1')
                    if thresholds[m][rule] is not None and thresholds[BASELINE][rule] is not None]
        if period != 'validation 2021-2022':
            r['threshold_free_diff'] = {m: tf_diff(df, BASELINE, m) for m in (HEADLINE, CAND)}
            for rule in RULES:   # equal total alerts = what EMBER issued under that rule
                n = r['rules'][rule][HEADLINE]['alerts']
                r['equal_count'][rule] = {m: equal_count(df, BASELINE, m, n) for m in (HEADLINE, CAND)}
        res['periods'][period] = r
    (config.OUTPUT_DIR / 'flexible_alerts.json').write_text(json.dumps(res, indent=2))
    write_report(res)
    print((config.OUTPUT_DIR / 'FLEXIBLE_ALERTS.md').read_text())


def write_report(res: dict) -> None:
    pct = lambda x: f'{100 * x:.1f}%'
    L = ['# Threshold-based alerts (no fixed number per week)', '',
         'Every cell-week whose risk score clears a threshold is an alert, so alert counts rise and fall with the season '
         'and conditions. Thresholds were chosen per model on **2021-2022 validation only**, by rules fixed before any '
         'test number was computed. 2023-2024 and 2025 were both used before; these are additional readings of frozen '
         'models. CIs: calendar-month block bootstrap. Regenerate: `python3 -m forecasting.flexible_alerts`.', '',
         '## Thresholds (from validation)', '', '| Model | best F1 | precision >= 70% | precision >= 50% |', '|---|---|---|---|']
    for m, t in res['thresholds'].items():
        f = lambda v: '-' if v is None else f'{v:.3f}'
        L.append(f"| {NAMES[m]} | {f(t['best_f1'])} | {f(t['precision70'])} | {f(t['precision50'])} |")
    rule_txt = {'best_f1': 'Best balance (max F1)', 'precision70': 'Confident (>= 70% on validation)',
                'precision50': 'Broad (>= 50% on validation)'}
    for period in ('test 2025 (WFIGS)', 'test 2023-2024 (FPA-FOD)', 'validation 2021-2022'):
        r = res['periods'][period]
        L += ['', f'## {period}', '',
              f"{r['cell_weeks']:,} cell-weeks, {r['fire_cell_weeks']:,} with a reported fire ({pct(r['base_rate'])}).", '']
        for rule in RULES:
            L += [f'### {rule_txt[rule]}', '',
                  '| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |',
                  '|---|---|---|---|---|---|---|---|']
            for m in MODELS:
                s = r['rules'][rule].get(m)
                if not s:
                    continue
                w = s['alerts_per_week']
                L.append(f"| {NAMES[m]} | {s['alerts']} | {w['min']}-{w['median']:.0f}-{w['max']} | {s['weeks_with_no_alert']} of {s['weeks']} | "
                         f"**{pct(s['precision'])}** | {pct(s['recall'])} | {pct(s['fire_capture'])} | {s['f1']:.3f} |")
            comps = r['rules'][rule].get('comparisons', [])
            if comps:
                L += ['', '| Versus baseline | Difference | 95% CI |', '|---|---|---|']
                for c, m in zip(comps, [x for x in (HEADLINE, CAND) for _ in range(3)]):
                    L.append(f"| {NAMES[m]}, {c['metric']} | {100 * c['diff']:+.1f} pt | [{100 * c['ci95'][0]:+.1f}, {100 * c['ci95'][1]:+.1f}] |")
            L.append('')
        if r['equal_count']:
            L += ['### Same total number of alerts, placed anywhere in the period', '',
                  '| Alerts (= EMBER under rule) | Share of cell-weeks | Model | Its hit rate | Baseline hit rate | Difference | 95% CI |',
                  '|---|---|---|---|---|---|---|']
            for rule, d in r['equal_count'].items():
                for m, e in d.items():
                    L.append(f"| {e['alerts']} ({rule}) | {pct(e['share_of_cellweeks'])} | {NAMES[m]} | {pct(e['precision_b'])} | "
                             f"{pct(e['precision_a'])} | {100 * e['diff']:+.1f} pt | [{100 * e['ci95'][0]:+.1f}, {100 * e['ci95'][1]:+.1f}] |")
            L.append('')
        L += ['### Threshold-free', '', '| Model | PR-AUC | ROC-AUC | Brier | Mean risk vs observed rate |', '|---|---|---|---|---|']
        for m, t in r['threshold_free'].items():
            L.append(f"| {NAMES[m]} | {t['pr_auc']:.3f} | {t['roc_auc']:.3f} | {t['brier']:.4f} | {pct(t['mean_risk'])} vs {pct(t['observed_rate'])} |")
        if r.get('threshold_free_diff'):
            L += ['', '| Versus baseline | PR-AUC (higher better) | ROC-AUC (higher better) | Brier (lower better) |', '|---|---|---|---|']
            for m, d in r['threshold_free_diff'].items():
                f = lambda x: f"{x['diff']:+.4f} [{x['ci95'][0]:+.4f}, {x['ci95'][1]:+.4f}]"
                L.append(f"| {NAMES[m]} | {f(d['pr_auc'])} | {f(d['roc_auc'])} | {f(d['brier'])} |")
    (config.OUTPUT_DIR / 'FLEXIBLE_ALERTS.md').write_text('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
