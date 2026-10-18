"""Ranking and probability metrics for weekly cell risk scores."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def week_capture(scores: np.ndarray, events: np.ndarray, k: int) -> float:
    """Events captured by the top-k cells of one week, sharing ties fractionally.

    Cells tied at the cut-off score contribute (slots left / tied cells) of their
    events, i.e. the expectation under uniformly random tie-breaking.
    """
    order = np.argsort(-scores, kind='stable')
    s, e = scores[order], events[order]
    thr = s[k - 1]
    above = s > thr
    tied = s == thr
    n_above = int(above.sum())
    return float(e[above].sum() + e[tied].sum() * (k - n_above) / tied.sum())


def topk_capture(df: pd.DataFrame, score: str, frac: float, events: str = 'event_count') -> dict:
    """Fraction of all reported fires falling in each week's top ``frac`` cells."""
    cap = tot = 0.0
    weekly = []
    for _, g in df.groupby('forecast_date', sort=True):
        k = max(1, int(round(frac * len(g))))
        c = week_capture(g[score].to_numpy(float), g[events].to_numpy(float), k)
        t = float(g[events].sum())
        cap += c
        tot += t
        weekly.append((c, t))
    return dict(capture=cap / tot if tot else float('nan'), captured_events=round(cap, 2),
                total_events=int(tot), lift=(cap / tot) / frac if tot else float('nan'))


def weekly_capture_table(df: pd.DataFrame, score: str, frac: float, events: str = 'event_count') -> pd.DataFrame:
    rows = []
    for d, g in df.groupby('forecast_date', sort=True):
        k = max(1, int(round(frac * len(g))))
        rows.append(dict(forecast_date=d, captured=week_capture(g[score].to_numpy(float), g[events].to_numpy(float), k),
                         events=float(g[events].sum())))
    return pd.DataFrame(rows)


def summary(df: pd.DataFrame, score: str) -> dict:
    y, p = df['label'].to_numpy(), df[score].to_numpy(float)
    out = dict(n=int(len(df)), weeks=int(df['forecast_date'].nunique()), positives=int(y.sum()),
               events=int(df['event_count'].sum()), prevalence=round(float(y.mean()), 4),
               pr_auc=round(float(average_precision_score(y, p)), 4),
               roc_auc=round(float(roc_auc_score(y, p)), 4))
    if np.all((p >= 0) & (p <= 1)):
        out['brier'] = round(float(brier_score_loss(y, p)), 5)
        out['brier_climatological_constant'] = round(float(brier_score_loss(y, np.full_like(p, y.mean()))), 5)
    for frac in (0.05, 0.10, 0.20):
        t = topk_capture(df, score, frac)
        out[f'top{int(frac * 100)}_capture'] = round(t['capture'], 4)
        out[f'top{int(frac * 100)}_lift'] = round(t['lift'], 3)
        out[f'top{int(frac * 100)}_captured_events'] = t['captured_events']
    return out


def block_bootstrap_diff(df: pd.DataFrame, score_a: str, score_b: str, frac: float = 0.10,
                         n_boot: int = 2000, seed: int = 0) -> dict:
    """Capture(b) - capture(a) with a calendar-month block bootstrap over weeks.

    Weeks are resampled in whole calendar-month blocks to respect temporal
    autocorrelation; both models are evaluated on the same resampled weeks.
    """
    ta = weekly_capture_table(df, score_a, frac)
    tb = weekly_capture_table(df, score_b, frac)
    m = ta[['forecast_date', 'events']].copy()
    m['ca'], m['cb'] = ta['captured'].to_numpy(), tb['captured'].to_numpy()
    m['block'] = pd.to_datetime(m['forecast_date']).dt.to_period('M').astype(str)
    blocks = m.groupby('block')[['ca', 'cb', 'events']].sum()
    arr = blocks.to_numpy()
    point = (arr[:, 1].sum() - arr[:, 0].sum()) / arr[:, 2].sum()
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        s = arr[rng.integers(0, len(arr), len(arr))]
        diffs[i] = (s[:, 1].sum() - s[:, 0].sum()) / s[:, 2].sum()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return dict(metric=f'top{int(frac * 100)}_capture', baseline=score_a, candidate=score_b,
                diff=round(float(point), 4), ci95=[round(float(lo), 4), round(float(hi), 4)],
                p_le_zero=round(float((diffs <= 0).mean()), 4), blocks=int(len(arr)), n_boot=n_boot)


def reliability(df: pd.DataFrame, score: str, bins: int = 10) -> list[dict]:
    q = pd.qcut(df[score].rank(method='first'), bins, labels=False)
    out = []
    for b, g in df.groupby(q):
        out.append(dict(bin=int(b), mean_score=round(float(g[score].mean()), 4),
                        observed_rate=round(float(g['label'].mean()), 4), n=int(len(g))))
    return out
