"""Evaluation that rewards forecasting fires climatology did NOT expect.

Definitions (fixed before any number below was computed; committed first):

* Expectedness of a cell-week = c, the frozen 2015-2020 climatology rate for that
  cell and week of year (model A's score). Recognising summer hotspots is worth
  nothing here; only departures from c that turn out right earn credit.
* M1 information gain over climatology, bits per cell-week:
      mean[ y*log2(p/c) + (1-y)*log2((1-p)/(1-c)) ]      (p, c clipped to [1e-4, 1-1e-4])
  > 0 only if the model's deviations from climatology are right on balance. A = 0.
  Also the Brier skill score vs climatology: 1 - Brier(p)/Brier(c).
* M2 within-stratum ranking: ROC-AUC computed inside each climatology decile
  (decile edges = quantiles of c on 2021-2022 validation), averaged with weights =
  positives per decile (deciles lacking both classes skipped). Measures who can
  tell, among cell-weeks with the SAME historical risk, which will burn.
* M3 unexpected fires: fire cell-weeks with c < 0.10 (that cell and week burned in
  under 1 week in 10 historically). Sensitivity: c < 0.05 and c < 0.20. Under each
  validation-chosen alert rule (``alert_thresholds.json``): unexpected fire
  cell-weeks alerted (recall), alerts in the stratum and their hit rate, and
  surprise-weighted recall = sum over alerted fire cell-weeks of -log2(c) / same
  over all fire cell-weeks.
* M4 excess hits: for each alert rule, sum over alerts of (y - c): fires found
  beyond what climatology already expected in the alerted cells; also per alert.

Periods: validation 2021-2022 (where thresholds were chosen), test 2023-2024
(FPA-FOD) and test 2025 (WFIGS); both tests were used before. CIs: calendar-month
block bootstrap of EMBER (E) minus baseline (A), or of E alone for M1.

Usage: python3 -m forecasting.surprise_eval
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import config
from .evaluate import BASELINE, HEADLINE
from .flexible_alerts import CAND, NAMES, RULES, boot_ci, frames

MODELS = [BASELINE, HEADLINE, CAND]
CUTS = (0.05, 0.10, 0.20)
PRIMARY_CUT = 0.10
EPS = 1e-4


def info_gain(df: pd.DataFrame, m: str) -> float:
    p = df[m].clip(EPS, 1 - EPS).to_numpy()
    c = df[BASELINE].clip(EPS, 1 - EPS).to_numpy()
    y = df['label'].to_numpy()
    return float(np.mean(y * np.log2(p / c) + (1 - y) * np.log2((1 - p) / (1 - c))))


def brier_skill(df: pd.DataFrame, m: str) -> float:
    y = df['label'].to_numpy()
    return float(1 - np.mean((df[m] - y) ** 2) / np.mean((df[BASELINE] - y) ** 2))


def strat_auc(df: pd.DataFrame, m: str, edges: np.ndarray) -> float:
    dec = np.digitize(df[BASELINE].to_numpy(), edges[1:-1])
    num = den = 0.0
    for d in np.unique(dec):
        g = df[dec == d]
        pos = int(g['label'].sum())
        if 0 < pos < len(g):
            num += pos * roc_auc_score(g['label'], g[m])
            den += pos
    return num / den if den else float('nan')


def unexpected(df: pd.DataFrame, m: str, thr: float, cut: float) -> dict:
    s = df[df[BASELINE] < cut]
    flag = s[m] >= thr
    y = s['label'] == 1
    surprise = -np.log2(s[BASELINE].clip(EPS, 1).to_numpy())
    tp = int((flag & y).sum())
    return dict(fire_cellweeks=int(y.sum()), alerted_fires=tp, recall=round(tp / max(int(y.sum()), 1), 4),
                alerts=int(flag.sum()), hit_rate=round(tp / int(flag.sum()), 4) if flag.sum() else None,
                surprise_weighted_recall=round(float(surprise[(flag & y).to_numpy()].sum() / surprise[y.to_numpy()].sum()), 4)
                if y.any() else None)


def excess(df: pd.DataFrame, m: str, thr: float) -> dict:
    a = df[df[m] >= thr]
    ex = float((a['label'] - a[BASELINE]).sum())
    return dict(alerts=int(len(a)), hits=int(a['label'].sum()), expected_by_climatology=round(float(a[BASELINE].sum()), 1),
                excess_hits=round(ex, 1), excess_per_alert=round(ex / len(a), 4) if len(a) else None)


def main() -> None:
    F = frames()
    thr = json.loads((config.OUTPUT_DIR / 'alert_thresholds.json').read_text())['thresholds']
    edges = np.quantile(F['validation 2021-2022'][BASELINE], np.linspace(0, 1, 11))
    res = dict(definitions=__doc__.split('Periods:')[0].strip(), decile_edges=[round(float(e), 4) for e in edges],
               thresholds=thr, periods={})
    for period, df in F.items():
        r = dict(cell_weeks=int(len(df)), fire_cell_weeks=int(df['label'].sum()),
                 unexpected_share_of_fire_cellweeks={str(c): round(float(((df[BASELINE] < c) & (df['label'] == 1)).sum()
                                                                        / df['label'].sum()), 4) for c in CUTS},
                 M1={m: dict(info_gain_bits=round(info_gain(df, m), 5), brier_skill=round(brier_skill(df, m), 4))
                     for m in MODELS},
                 M2={m: round(strat_auc(df, m, edges), 4) for m in MODELS},
                 M3={rule: {str(c): {m: unexpected(df, m, thr[m][rule], c) for m in MODELS} for c in CUTS}
                     for rule in RULES if all(thr[m][rule] is not None for m in MODELS)},
                 M4={rule: {m: excess(df, m, thr[m][rule]) for m in MODELS}
                     for rule in RULES if all(thr[m][rule] is not None for m in MODELS)})
        if not period.startswith('validation'):
            ci = {}
            for m in (HEADLINE, CAND):
                ci[m] = dict(
                    info_gain=boot_ci(lambda d: info_gain(d, m), df),
                    strat_auc_diff=dict(diff=round(r['M2'][m] - r['M2'][BASELINE], 4),
                                        ci95=boot_ci(lambda d: strat_auc(d, m, edges) - strat_auc(d, BASELINE, edges), df)),
                    unexpected_recall_diff={rule: dict(
                        diff=round(r['M3'][rule][str(PRIMARY_CUT)][m]['recall'] - r['M3'][rule][str(PRIMARY_CUT)][BASELINE]['recall'], 4),
                        ci95=boot_ci(lambda d: unexpected(d, m, thr[m][rule], PRIMARY_CUT)['recall']
                                     - unexpected(d, BASELINE, thr[BASELINE][rule], PRIMARY_CUT)['recall'], df))
                        for rule in r['M3']},
                    excess_per_alert_diff={rule: dict(
                        diff=round(r['M4'][rule][m]['excess_per_alert'] - r['M4'][rule][BASELINE]['excess_per_alert'], 4),
                        ci95=boot_ci(lambda d: (excess(d, m, thr[m][rule])['excess_per_alert'] or 0)
                                     - (excess(d, BASELINE, thr[BASELINE][rule])['excess_per_alert'] or 0), df))
                        for rule in r['M4']})
            r['ci'] = ci
        res['periods'][period] = r
        print(f'  {period} done', flush=True)
    (config.OUTPUT_DIR / 'surprise_eval.json').write_text(json.dumps(res, indent=2))
    write_report(res)
    print((config.OUTPUT_DIR / 'SURPRISE_EVAL.md').read_text())


def write_report(res: dict) -> None:
    pct = lambda x: '-' if x is None else f'{100 * x:.1f}%'
    ci = lambda c, k=100, u='pt': f'[{k * c[0]:+.1f}, {k * c[1]:+.1f}]'
    L = ['# Rewarding unexpected fires', '',
         'Expectedness of a cell-week = its frozen 2015-2020 climatology rate c (how often that cell burned in that week '
         'of the year). These measures give **no credit for recognising usual hotspots**; only correct departures from '
         'climatology count. Definitions were committed before computing (`surprise_eval.py`). Alert thresholds come from '
         '2021-2022 validation (`alert_thresholds.json`). Both test periods were used before. CIs: calendar-month block bootstrap.', '']
    for period in ('test 2025 (WFIGS)', 'test 2023-2024 (FPA-FOD)', 'validation 2021-2022'):
        r = res['periods'][period]
        u = r['unexpected_share_of_fire_cellweeks']
        L += [f'## {period}', '',
              f"{r['cell_weeks']:,} cell-weeks; {r['fire_cell_weeks']:,} with a reported fire. Share of fire cell-weeks that were "
              f"unexpected (c < 5% / 10% / 20%): {pct(u['0.05'])} / {pct(u['0.1'])} / {pct(u['0.2'])}.", '',
              '### Skill beyond climatology (all cell-weeks)', '',
              '| Model | Information gain (millibits/cell-week) | Brier skill vs climatology | Ranking within same-risk deciles (ROC-AUC) |',
              '|---|---|---|---|']
        for m in MODELS:
            L.append(f"| {NAMES[m]} | {1000 * r['M1'][m]['info_gain_bits']:+.1f} | {r['M1'][m]['brier_skill']:+.4f} | {r['M2'][m]:.3f} |")
        if 'ci' in r:
            L += ['', '| Versus baseline | Information gain 95% CI (millibits) | Within-decile ROC-AUC difference |', '|---|---|---|']
            for m, c in r['ci'].items():
                L.append(f"| {NAMES[m]} | [{1000 * c['info_gain'][0]:+.1f}, {1000 * c['info_gain'][1]:+.1f}] | "
                         f"{c['strat_auc_diff']['diff']:+.3f} [{c['strat_auc_diff']['ci95'][0]:+.3f}, {c['strat_auc_diff']['ci95'][1]:+.3f}] |")
        L += ['', f'### Unexpected fires (climatology < {int(100 * PRIMARY_CUT)}%) caught by validation-threshold alerts', '',
              '| Rule | Model | Unexpected fire cell-weeks | Caught | Recall | Alerts in that stratum | Their hit rate | Surprise-weighted recall |',
              '|---|---|---|---|---|---|---|---|']
        for rule, byc in r['M3'].items():
            for m in MODELS:
                x = byc[str(PRIMARY_CUT)][m]
                L.append(f"| {rule} | {NAMES[m]} | {x['fire_cellweeks']} | {x['alerted_fires']} | {pct(x['recall'])} | {x['alerts']} | "
                         f"{pct(x['hit_rate'])} | {pct(x['surprise_weighted_recall'])} |")
        if 'ci' in r:
            L += ['', '| Versus baseline: unexpected-fire recall | Rule | Difference | 95% CI |', '|---|---|---|---|']
            for m, c in r['ci'].items():
                for rule, d in c['unexpected_recall_diff'].items():
                    L.append(f"| {NAMES[m]} | {rule} | {100 * d['diff']:+.1f} pt | {ci(d['ci95'])} |")
        L += ['', '### Excess hits: fires found beyond what climatology expected in the alerted cells', '',
              '| Rule | Model | Alerts | Hits | Expected by climatology | Excess hits | Excess per alert |', '|---|---|---|---|---|---|---|']
        for rule, bym in r['M4'].items():
            for m in MODELS:
                x = bym[m]
                L.append(f"| {rule} | {NAMES[m]} | {x['alerts']} | {x['hits']} | {x['expected_by_climatology']} | "
                         f"{x['excess_hits']:+.1f} | {x['excess_per_alert']:+.3f} |")
        if 'ci' in r:
            L += ['', '| Versus baseline: excess per alert | Rule | Difference | 95% CI |', '|---|---|---|---|']
            for m, c in r['ci'].items():
                for rule, d in c['excess_per_alert_diff'].items():
                    L.append(f"| {NAMES[m]} | {rule} | {d['diff']:+.3f} | [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}] |")
        L.append('')
    sens = ['## Sensitivity: unexpected-fire recall at other cut-offs (2025, confident rule)', '',
            '| Cut-off | Model | Unexpected fire cell-weeks | Recall |', '|---|---|---|---|']
    r25 = res['periods']['test 2025 (WFIGS)']['M3'].get('precision70', {})
    for c, bym in r25.items():
        for m in MODELS:
            sens.append(f"| c < {float(c):.2f} | {NAMES[m]} | {bym[m]['fire_cellweeks']} | {pct(bym[m]['recall'])} |")
    (config.OUTPUT_DIR / 'SURPRISE_EVAL.md').write_text('\n'.join(L + sens) + '\n')


if __name__ == '__main__':
    main()
