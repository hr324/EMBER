"""One-family-at-a-time feature experiments, selected on 2021-2022 validation only.

Protocol (EMBER_OVERNIGHT_FORECAST_MISSION_v2.md):
* Train 2015-2020, compare on 2021-2022. The used 2023-2024 holdout is not scored here.
* Every gradient-boosting variant uses ONE fixed configuration (the frozen headline
  model's), so differences come from features, not from re-tuning.
* Primary metric: precision of the weekly top-8 alert budget (share of flagged
  cell-weeks with >= 1 reported fire), compared with matched models at the same
  budget; month-block bootstrap for the paired difference.
* Each run appends to ``outputs/experiments.json`` and rewrites ``outputs/experiments.md``.

Usage: python3 -m forecasting.experiments <family>   (see FAMILIES)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from . import config, features, metrics, models
from .features import HISTORY_COLS, LOCATION_COLS, SEASON_COLS

GBM = dict(learning_rate=0.03, max_iter=500, max_leaf_nodes=15, min_samples_leaf=300, l2_regularization=3.0)
BUDGET = 8
N_BOOT = 2000
LOG_JSON = config.OUTPUT_DIR / 'experiments.json'
BASE_COLS = SEASON_COLS + LOCATION_COLS + ['clim']


def base_frame() -> pd.DataFrame:
    df = pd.read_csv(config.PROCESSED_DIR / 'features.csv', parse_dates=['forecast_date', 'weather_cutoff'])
    df = df[df['split'].isin(['train', 'validation'])].reset_index(drop=True)
    return models.add_climatology_feature(df)


def weather_cols() -> list[str]:
    return json.loads((config.PROCESSED_DIR / 'features_info.json').read_text())['weather_cols']


def fit_score(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    tr = df['split'] == 'train'
    m = HistGradientBoostingClassifier(random_state=models.SEED, early_stopping=False, **GBM)
    m.fit(df.loc[tr, cols].to_numpy(float), df.loc[tr, 'label'].to_numpy())
    return m.predict_proba(df[cols].to_numpy(float))[:, 1]


# ---------------------------------------------------------------- budget metrics

def weekly_top(df: pd.DataFrame, score: str, k: int = BUDGET) -> pd.DataFrame:
    r = df.groupby('forecast_date')[score].rank(ascending=False, method='first')
    return df[r <= k]


def budget_stats(df: pd.DataFrame, score: str) -> dict:
    top = weekly_top(df, score)
    return dict(alerts=int(len(top)), hits=int(top['label'].sum()),
                precision=round(float(top['label'].mean()), 4),
                event_capture=round(float(top['event_count'].sum() / df['event_count'].sum()), 4),
                cellweek_recall=round(float(top['label'].sum() / df['label'].sum()), 4),
                pr_auc=metrics.summary(df, score)['pr_auc'])


def paired_precision(df: pd.DataFrame, a: str, b: str) -> dict:
    """Precision(b) - precision(a) at the weekly top-8 budget, month-block bootstrap."""
    ta, tb = weekly_top(df, a), weekly_top(df, b)
    month = lambda t: pd.to_datetime(t['forecast_date']).dt.to_period('M').astype(str)
    ha = ta.groupby(month(ta))['label'].agg(['sum', 'count'])
    hb = tb.groupby(month(tb))['label'].agg(['sum', 'count'])
    blocks = ha.join(hb, lsuffix='_a', rsuffix='_b').to_numpy(float)
    point = blocks[:, 2].sum() / blocks[:, 3].sum() - blocks[:, 0].sum() / blocks[:, 1].sum()
    rng = np.random.default_rng(0)
    d = np.empty(N_BOOT)
    for i in range(N_BOOT):
        s = blocks[rng.integers(0, len(blocks), len(blocks))]
        d[i] = s[:, 2].sum() / s[:, 3].sum() - s[:, 0].sum() / s[:, 1].sum()
    lo, hi = np.percentile(d, [2.5, 97.5])
    return dict(baseline=a, candidate=b, diff=round(float(point), 4), ci95=[round(float(lo), 4), round(float(hi), 4)],
                p_le_zero=round(float((d <= 0).mean()), 4))


# ---------------------------------------------------------------- logging

def log(entry: dict) -> None:
    log_ = json.loads(LOG_JSON.read_text()) if LOG_JSON.exists() else []
    log_ = [e for e in log_ if e['family'] != entry['family']] + [entry]
    LOG_JSON.write_text(json.dumps(log_, indent=2, default=str))
    L = ['# Feature experiments (validation 2021-2022 only)', '',
         'Train 2015-2020, compare on 2021-2022. Fixed gradient-boosting configuration for every variant. '
         'Primary metric: share of the weekly top-8 alerts followed by >= 1 reported fire. '
         'CIs: calendar-month block bootstrap. The used 2023-2024 holdout is not scored here.', '']
    for e in log_:
        L += [f"## {e['family']}", '', f"- **Hypothesis:** {e['hypothesis']}", f"- **Source:** {e['source']}",
              f"- **Available at issue time:** {e['timing']}", f"- **Coverage:** {e['coverage']}", '',
              '| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |',
              '|---|---|---|---|---|---|']
        for v, s in e['variants'].items():
            L.append(f"| {v} | {s['alerts']} | {100 * s['precision']:.1f}% | {100 * s['event_capture']:.1f}% | "
                     f"{100 * s['cellweek_recall']:.1f}% | {s['pr_auc']:.3f} |")
        L += ['', '| Comparison | Precision difference | 95% CI | P(<= 0) |', '|---|---|---|---|']
        for c in e['comparisons']:
            L.append(f"| {c['candidate']} vs {c['baseline']} | {100 * c['diff']:+.1f} pt | "
                     f"[{100 * c['ci95'][0]:+.1f}, {100 * c['ci95'][1]:+.1f}] | {c['p_le_zero']} |")
        L += ['', f"**Decision:** {e['decision']}", '']
    (config.OUTPUT_DIR / 'experiments.md').write_text('\n'.join(L))


def run_family(name: str, df: pd.DataFrame, variants: dict[str, list[str] | None], comparisons: list[tuple[str, str]],
               meta: dict) -> dict:
    val = None
    for v, cols in variants.items():
        df[v] = df['clim_full_train'] if cols is None else fit_score(df, cols)
    val = df[df['split'] == 'validation']
    entry = dict(family=name, run_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'), **meta,
                 variants={v: budget_stats(val, v) for v in variants},
                 comparisons=[paired_precision(val, a, b) for a, b in comparisons])
    for v, s in entry['variants'].items():
        print(f"  {v:34s} precision {s['precision']:.4f}  capture {s['event_capture']:.4f}  PR-AUC {s['pr_auc']:.4f}")
    for c in entry['comparisons']:
        print(f"  {c['candidate']} - {c['baseline']}: {c['diff']:+.4f} {c['ci95']} P<=0 {c['p_le_zero']}")
    return entry


# ---------------------------------------------------------------- families

def exp_weather_timing() -> dict:
    """Diagnostic: does better-timed weather carry signal at all?"""
    df = base_frame()
    wcols = weather_cols()
    table = features.weather_table()
    lab = df[['cell_id', 'forecast_date']].copy()
    for tag, offset in (('lag1', -1), ('oracle', +6)):
        lab['weather_cutoff'] = df['forecast_date'] + pd.Timedelta(days=offset)
        w = features.weather(lab, table)
        for c in wcols:
            df[f'{c}__{tag}'] = w[c].to_numpy()
    seven = [c for c in wcols if c.endswith('_7')]
    base = BASE_COLS + HISTORY_COLS
    variants = {
        'A_climatology': None,
        'E0_history_no_weather': base,
        'E_weather_lag7 (current)': base + wcols,
        'E_weather_lag1 (upper bound)': base + [f'{c}__lag1' for c in wcols],
        'DIAG_oracle_target_week (leaks)': base + [f'{c}__oracle' for c in seven],
    }
    comps = [('E0_history_no_weather', 'E_weather_lag7 (current)'),
             ('E0_history_no_weather', 'E_weather_lag1 (upper bound)'),
             ('E_weather_lag7 (current)', 'E_weather_lag1 (upper bound)'),
             ('E0_history_no_weather', 'DIAG_oracle_target_week (leaks)'),
             ('A_climatology', 'E_weather_lag1 (upper bound)')]
    meta = dict(hypothesis='The 7-day weather lag hides near-term dry/windy conditions; weather ending the day before issue, '
                           'or (diagnostic only) the actual target-week weather, should add skill if weather matters at all.',
                source='Open-Meteo historical reanalysis, same 20 points and variables as the current model.',
                timing=('lag1 = reanalysis ending issue-1 day: an UPPER BOUND, not operational (reanalysis is a later '
                        'reconstruction). oracle = the actual weather of the forecast week: a LEAKING ceiling used only '
                        'to decide whether issued forecasts are worth pursuing; never a candidate.'),
                coverage='All 80 cells, 2015-2022, no missing values.')
    entry = run_family('1. Weather timing (diagnostic)', df, variants, comps, meta)
    return entry


def activity_features(df: pd.DataFrame, fires: pd.DataFrame) -> pd.DataFrame:
    """Recent-activity counts strictly before the issue date (no same-day fires)."""
    from .grid import Grid
    g = Grid()
    cells = [c.cell_id for c in g.cells]
    idx = {c: i for i, c in enumerate(cells)}
    day0 = pd.Timestamp('2014-01-01')
    n_days = (pd.to_datetime(df['forecast_date']).max() - day0).days + 8
    counts = np.zeros((len(cells), n_days + 1))
    for c, d in zip(fires['cell_id'], pd.to_datetime(fires['discovery_date'])):
        k = (d - day0).days
        if 0 <= k < n_days and c in idx:
            counts[idx[c], k + 1] += 1
    cum = counts.cumsum(axis=1)
    reg = cum.sum(axis=0)
    k = (pd.to_datetime(df['forecast_date']) - day0).dt.days.to_numpy()
    ci = df['cell_id'].map(idx).to_numpy()
    nb = {c: [idx[n] for n in g.neighbours(c)] for c in cells}
    out = pd.DataFrame(index=df.index)
    for n in (7, 30):
        out[f'act_region_{n}'] = reg[k] - reg[np.maximum(k - n, 0)]
    out['act_cell_7'] = cum[ci, k] - cum[ci, np.maximum(k - 7, 0)]
    nbr7 = np.zeros(len(df))
    for j, c in enumerate(cells):
        m = ci == j
        for b in nb[c]:
            nbr7[m] += cum[b, k[m]] - cum[b, np.maximum(k[m] - 7, 0)]
    out['act_nbr_7'] = nbr7
    return out


ACTIVITY_COLS = ['act_region_7', 'act_region_30', 'act_cell_7', 'act_nbr_7']


def exp_activity() -> dict:
    df = base_frame()
    fires = pd.read_csv(config.PROCESSED_DIR / 'fires.csv', parse_dates=['discovery_date'])
    df = pd.concat([df, activity_features(df, fires)], axis=1)
    base = BASE_COLS + HISTORY_COLS
    variants = {'A_climatology': None, 'E0_history_no_weather': base,
                'E0+activity': base + ACTIVITY_COLS, 'E0+weather(lag7)': base + weather_cols(),
                'E0+weather(lag7)+activity': base + weather_cols() + ACTIVITY_COLS}
    comps = [('E0_history_no_weather', 'E0+activity'), ('E0+weather(lag7)', 'E0+weather(lag7)+activity'),
             ('A_climatology', 'E0+activity')]
    meta = dict(hypothesis='Busy or quiet periods across the whole region (and in the last 7 days locally) shift '
                           'next-week ignition risk beyond season and location.',
                source='FPA-FOD discoveries (live equivalent: WFIGS feed, reliable from 2020).',
                timing='Counts of discoveries in [issue - N days, issue - 1 day]; known at issue in live use only if '
                       'reporting is prompt (WFIGS discovery records are near-real-time).',
                coverage='All 80 cells, 2015-2022.')
    return run_family('2. Recent activity anomalies', df, variants, comps, meta)


def _last_monday(y, m):
    from calendar import monthrange
    from datetime import date as D
    d = D(y, m, monthrange(y, m)[1])
    return d - pd.Timedelta(days=d.weekday())


def holiday_features(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic US holiday dates falling inside [issue, issue + 6] (known years ahead)."""
    from datetime import date as D, timedelta as TD
    out = pd.DataFrame(index=df.index)
    issue = pd.to_datetime(df['forecast_date']).dt.date

    def in_window(f):
        return issue.map(lambda d: int(d <= f(d.year) <= d + TD(days=6) or d <= f(d.year + 1) <= d + TD(days=6))).to_numpy()

    def first_monday(y, m):
        d = D(y, m, 1)
        return d + TD(days=(7 - d.weekday()) % 7)

    def thanksgiving(y):
        d = D(y, 11, 1)
        return d + TD(days=(3 - d.weekday()) % 7 + 21)

    out['hol_july4'] = in_window(lambda y: D(y, 7, 4))
    out['hol_memorial'] = in_window(lambda y: _last_monday(y, 5))
    out['hol_labor'] = in_window(lambda y: first_monday(y, 9))
    out['hol_thanksgiving'] = in_window(thanksgiving)
    mid = pd.to_datetime(df['forecast_date']) + pd.Timedelta(days=3)
    j4 = pd.to_datetime(mid.dt.year.astype(str) + '-07-04')
    out['hol_days_to_july4'] = (j4 - mid).dt.days.clip(-21, 21)
    return out


HOLIDAY_COLS = ['hol_july4', 'hol_memorial', 'hol_labor', 'hol_thanksgiving', 'hol_days_to_july4']


def exp_holidays() -> dict:
    df = base_frame()
    df = pd.concat([df, holiday_features(df)], axis=1)
    base = BASE_COLS + HISTORY_COLS
    variants = {'A_climatology': None, 'E0_history_no_weather': base, 'E0+holidays': base + HOLIDAY_COLS}
    comps = [('E0_history_no_weather', 'E0+holidays'), ('A_climatology', 'E0+holidays')]
    july = df[(df['hol_july4'] == 1)]
    meta = dict(hypothesis='Fireworks and holiday travel raise ignitions in holiday weeks beyond the smooth seasonal curve '
                           '(cf. doi:10.1371/journal.pone.0291026).',
                source='Deterministic US federal holiday rules (no external data).',
                timing='Known years ahead.',
                coverage=f'All rows; July-4 weeks in train+validation: {july["forecast_date"].nunique()} '
                         f'(base rate {july["label"].mean():.3f} vs overall {df["label"].mean():.3f}). '
                         'No historically valid exposure layer (roads/campgrounds) was available, so no interaction term.')
    return run_family('3. Holiday weeks', df, variants, comps, meta)


GRIDMET_COLS = ['gm_erc_0', 'gm_erc_mean_7', 'gm_erc_max_7', 'gm_bi_max_7', 'gm_fm100_0', 'gm_fm1000_0',
                'gm_fm1000_chg_14']


def gridmet_features(df: pd.DataFrame) -> pd.DataFrame:
    """gridMET indices at each cell centroid, windows ending issue - LAG_DAYS (inclusive)."""
    from .fetch_gridmet import LAG_DAYS
    g = pd.read_csv(config.PROCESSED_DIR / 'gridmet_daily.csv', parse_dates=['date'])
    frames = []
    for cid, x in g.groupby('cell_id'):
        x = x.set_index('date').sort_index().asfreq('D')
        f = pd.DataFrame(index=x.index)
        f['gm_erc_0'] = x['erc']
        f['gm_erc_mean_7'] = x['erc'].rolling(7, min_periods=7).mean()
        f['gm_erc_max_7'] = x['erc'].rolling(7, min_periods=7).max()
        f['gm_bi_max_7'] = x['bi'].rolling(7, min_periods=7).max()
        f['gm_fm100_0'] = x['fm100']
        f['gm_fm1000_0'] = x['fm1000']
        f['gm_fm1000_chg_14'] = x['fm1000'] - x['fm1000'].shift(14)
        f['cell_id'] = cid
        frames.append(f.reset_index().rename(columns={'date': 'gridmet_latest_date'}))
    t = pd.concat(frames, ignore_index=True)
    key = pd.DataFrame({'cell_id': df['cell_id'].to_numpy(),
                        'gridmet_latest_date': (pd.to_datetime(df['forecast_date']) - pd.Timedelta(days=LAG_DAYS)).to_numpy()})
    out = key.merge(t, on=['cell_id', 'gridmet_latest_date'], how='left')
    out.index = df.index
    assert ((pd.to_datetime(df['forecast_date']) - out['gridmet_latest_date']).dt.days >= LAG_DAYS).all()
    return out[['gridmet_latest_date'] + GRIDMET_COLS]


def exp_gridmet() -> dict:
    df = base_frame()
    df = pd.concat([df, gridmet_features(df)], axis=1)
    miss = int(df[GRIDMET_COLS].isna().any(axis=1).sum())
    base = BASE_COLS + HISTORY_COLS
    variants = {'A_climatology': None, 'E0_history_no_weather': base, 'E0+gridmet': base + GRIDMET_COLS,
                'E0+weather(lag7)': base + weather_cols(), 'E0+weather(lag7)+gridmet': base + weather_cols() + GRIDMET_COLS}
    comps = [('E0_history_no_weather', 'E0+gridmet'), ('E0+weather(lag7)', 'E0+weather(lag7)+gridmet'),
             ('A_climatology', 'E0+gridmet')]
    meta = dict(hypothesis='Fuel dryness and fire danger at 4 km (ERC, burning index, 100/1000-hour fuel moisture) '
                           'distinguish dangerous weeks and cells better than 50 km raw weather.',
                source='gridMET via Northwest Knowledge Network THREDDS (free), sampled at the 80 cell centroids.',
                timing='Latest gridMET day = issue - 3 (observed archive latency ~2 days on 18 Oct 2026). '
                       'Archive values are final versions; provisional real-time values may have differed.',
                coverage=f'All 80 cells, 2015-2022; rows with any missing gridMET value: {miss}.')
    return run_family('5. gridMET fuel dryness and fire danger', df, variants, comps, meta)


def exp_redflag() -> dict:
    df = base_frame()
    r = pd.read_csv(config.PROCESSED_DIR / 'redflag_features.csv', parse_dates=['forecast_date'])
    df = df.merge(r[['cell_id', 'forecast_date'] + REDFLAG_COLS], on=['cell_id', 'forecast_date'], how='left')
    assert df[REDFLAG_COLS].notna().all().all()
    base = BASE_COLS + HISTORY_COLS
    variants = {'A_climatology': None, 'E0_history_no_weather': base, 'E0+redflag': base + REDFLAG_COLS,
                'E0+weather(lag7)': base + weather_cols(), 'E0+weather(lag7)+redflag': base + weather_cols() + REDFLAG_COLS}
    comps = [('E0_history_no_weather', 'E0+redflag'), ('E0+weather(lag7)', 'E0+weather(lag7)+redflag'),
             ('A_climatology', 'E0+redflag')]
    s = json.loads((config.PROCESSED_DIR / 'redflag_summary.json').read_text())
    meta = dict(hypothesis='Red Flag Warnings and Fire Weather Watches already published by Monday 06:00 Pacific '
                           '(forecaster-identified critical fire weather) mark weeks and cells of elevated ignition risk.',
                source='IEM NWS VTEC archive (FW.W, FW.A) for offices STO, EKA, REV, MFR, MTR; zone polygons per event.',
                timing='Zone rows count only if product_issued <= Monday 06:00 America/Los_Angeles; valid window = '
                       'issue..init_expired (expiry as first issued; later extensions ignored).',
                coverage=f"{s['rows_touching_lattice']} (event, zone) rows touch the lattice; {len(s['zones_touching'])} zones; "
                         f"cell-weeks with a warning for the coming week {100 * s['share_cellweeks_rfw_week']:.1f}%, "
                         f"watch {100 * s['share_cellweeks_fww_week']:.1f}%, warning in past 7 days "
                         f"{100 * s['share_cellweeks_rfw_past7']:.1f}%.")
    return run_family('6. Red Flag Warnings / Fire Weather Watches', df, variants, comps, meta)


# ---------------------------------------------------------------- climatology-offset model

OFFSET_L2 = (1.0, 10.0, 100.0)


def anomalies(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Each dynamic feature minus its training-years mean for the same cell and calendar month."""
    month = pd.to_datetime(df['forecast_date']).dt.month
    tr = df['split'] == 'train'
    out = pd.DataFrame(index=df.index)
    for c in cols:
        ref = df.loc[tr, c].groupby([df.loc[tr, 'cell_id'], month[tr]]).mean()
        key = pd.MultiIndex.from_arrays([df['cell_id'], month])
        out[f'{c}__anom'] = df[c].to_numpy(float) - ref.reindex(key).to_numpy()
    return out


class OffsetLogit:
    """logit p = logit(climatology) + b0 + X.beta, L2-penalised; climatology enters as a fixed offset.

    The only learned part is the departure from climatology, so a gain can come
    only from dynamic information that season and location do not carry.
    """

    def __init__(self, l2: float):
        self.l2 = l2

    @staticmethod
    def _offset(clim):
        c = np.clip(np.asarray(clim, float), 1e-4, 1 - 1e-4)
        return np.log(c / (1 - c))

    def fit(self, X, y, clim):
        from scipy.optimize import minimize
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        off = self._offset(clim)
        n, k = Z.shape

        def f(w):
            eta = off + w[0] + Z @ w[1:]
            p = 1 / (1 + np.exp(-eta))
            loss = np.sum(np.logaddexp(0, eta) - y * eta) + 0.5 * self.l2 * np.sum(w[1:] ** 2)
            g = np.concatenate([[np.sum(p - y)], Z.T @ (p - y) + self.l2 * w[1:]])
            return loss, g

        self.w = minimize(f, np.zeros(k + 1), jac=True, method='L-BFGS-B').x
        return self

    def predict(self, X, clim):
        Z = (X - self.mu) / self.sd
        return 1 / (1 + np.exp(-(self._offset(clim) + self.w[0] + Z @ self.w[1:])))


def fit_offset(df: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, float, dict]:
    tr, va = (df['split'] == 'train').to_numpy(), (df['split'] == 'validation').to_numpy()
    X = df[cols].to_numpy(float)
    best = None
    for l2 in OFFSET_L2:
        m = OffsetLogit(l2).fit(X[tr], df['label'].to_numpy()[tr], df['clim'].to_numpy()[tr])
        p = m.predict(X, np.where(tr, df['clim'], df['clim_full_train']))
        prec = budget_stats(df[va].assign(_s=p[va]), '_s')['precision']
        if best is None or prec > best[2]:
            best = (p, l2, prec, m)
    p, l2, _, m = best
    coefs = dict(zip(cols, np.round(m.w[1:], 4)))
    return p, l2, coefs


def offset_families(df: pd.DataFrame) -> dict[str, list[str]]:
    fam = {'weather': [f'{c}__anom' for c in weather_cols()],
           'activity': [f'{c}__anom' for c in ACTIVITY_COLS + HISTORY_COLS],
           'holidays': HOLIDAY_COLS}
    rf = config.PROCESSED_DIR / 'redflag_features.csv'
    if rf.exists():
        fam['redflag'] = [f'{c}__anom' for c in REDFLAG_COLS]
    if (config.PROCESSED_DIR / 'gridmet_daily.csv').exists():
        fam['gridmet'] = [f'{c}__anom' for c in GRIDMET_COLS]
    return fam


REDFLAG_COLS = ['rfw_week_cov', 'fww_week_cov', 'rfw_past7_cov']


def offset_frame() -> pd.DataFrame:
    df = base_frame()
    fires = pd.read_csv(config.PROCESSED_DIR / 'fires.csv', parse_dates=['discovery_date'])
    df = pd.concat([df, activity_features(df, fires), holiday_features(df)], axis=1)
    dyn = weather_cols() + ACTIVITY_COLS + HISTORY_COLS
    rf = config.PROCESSED_DIR / 'redflag_features.csv'
    if rf.exists():
        r = pd.read_csv(rf, parse_dates=['forecast_date'])
        df = df.merge(r[['cell_id', 'forecast_date'] + REDFLAG_COLS], on=['cell_id', 'forecast_date'], how='left')
        assert df[REDFLAG_COLS].notna().all().all(), 'red-flag features missing for some cell-weeks'
        dyn += REDFLAG_COLS
    if (config.PROCESSED_DIR / 'gridmet_daily.csv').exists():
        df = pd.concat([df, gridmet_features(df)], axis=1)
        assert df[GRIDMET_COLS].notna().all().all(), 'gridMET features missing for some cell-weeks'
        dyn += GRIDMET_COLS
    return pd.concat([df, anomalies(df, dyn)], axis=1)


def exp_offset() -> dict:
    df = offset_frame()
    fam = offset_families(df)
    df['A_climatology'] = np.where(df['split'] == 'train', df['clim'], df['clim_full_train'])
    variants, chosen = {'A_climatology': None}, {}
    for name, cols in fam.items():
        p, l2, coefs = fit_offset(df, cols)
        df[f'A+{name}'] = p
        chosen[f'A+{name}'] = dict(l2=l2, coefs=coefs)
    allc = [c for cols in fam.values() for c in cols]
    p, l2, coefs = fit_offset(df, allc)
    df['A+all_dynamic'] = p
    chosen['A+all_dynamic'] = dict(l2=l2, coefs=coefs)
    val = df[df['split'] == 'validation']
    names = ['A_climatology'] + [f'A+{n}' for n in fam] + ['A+all_dynamic']
    entry = dict(family='4. Climatology-offset model (dynamic departures only)',
                 run_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                 hypothesis='Holding climatology fixed as an offset, a small penalised adjustment from dynamic '
                            'departures (weather, activity, holidays, Red Flag) improves the weekly alerts.',
                 source='Same sources as families 1-3, plus IEM Red Flag Warnings / Fire Weather Watches if built.',
                 timing='Weather lag 7 days; activity and history before issue; Red Flag as published by Monday 06:00 PT.',
                 coverage=f'All 80 cells, 2015-2022. Families: {", ".join(fam)}. Anomalies = value minus training-years '
                          'mean for the same cell and month. L2 penalty chosen on validation from 1, 10, 100.',
                 variants={n: budget_stats(val, n) for n in names},
                 comparisons=[paired_precision(val, 'A_climatology', n) for n in names[1:]],
                 offset_models=chosen)
    for v, s in entry['variants'].items():
        print(f"  {v:22s} precision {s['precision']:.4f}  capture {s['event_capture']:.4f}  PR-AUC {s['pr_auc']:.4f}")
    for c in entry['comparisons']:
        print(f"  {c['candidate']} - {c['baseline']}: {c['diff']:+.4f} {c['ci95']} P<=0 {c['p_le_zero']}")
    return entry


FAMILIES = {'weather_timing': exp_weather_timing, 'activity': exp_activity, 'holidays': exp_holidays,
            'offset': exp_offset, 'gridmet': exp_gridmet, 'redflag': exp_redflag}


DECISIONS = {
    '1. Weather timing (diagnostic)': (
        'REJECT lag-1 weather (no gain even as an upper bound: -0.8 pt vs no weather). The leaking oracle ceiling is only +1.2 pt [-0.2, +2.7], so even perfect next-week weather at this scale adds little. Experiment 4 (issued forecasts, archive from ~2021 only) is therefore DEPRIORITISED: its maximum plausible gain is below what 2 validation years can detect.'),
    '2. Recent activity anomalies': (
        'REJECT for the alert budget: -0.1 pt [-1.0, +0.8] vs matched control. Small PR-AUC/capture gain (0.521 -> 0.529) noted; kept only inside the offset-model test.'),
    '3. Holiday weeks': (
        'REJECT: +0.1 pt [-0.6, +0.7]. Only ~8 July-4 weeks in train+validation; too rare to learn from at this scale.'),
    '4. Climatology-offset model (dynamic departures only)': (
        'REJECT: no family moves the weekly top-8 relative to climatology (all-dynamic +0.0 pt [-2.3, +2.6]). Coefficients have sensible signs (drier 1000-h fuel and recent activity raise risk), but the shifts rarely change which 8 cells rank highest.'),
    '5. gridMET fuel dryness and fire danger': (
        'REJECT: -0.5 pt alone; -1.7 pt [-3.0, -0.4] when added to lag-7 weather (significantly worse: redundant correlated inputs overfit).'),
    '6. Red Flag Warnings / Fire Weather Watches': (
        'CARRY FORWARD as the single candidate: best validation precision of any new variant (48.4%), +0.7 pt [-0.2, +1.6] vs matched control (P<=0 = 0.07). Not significant; tested once on 2025 per PREREG_2025_v2.md.'),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('family', choices=sorted(FAMILIES))
    a = ap.parse_args()
    entry = FAMILIES[a.family]()
    entry['decision'] = DECISIONS.get(entry['family'], 'PENDING - set after review')
    log(entry)


if __name__ == '__main__':
    main()
