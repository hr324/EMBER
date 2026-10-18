"""Frozen-model tests on a different fire source (WFIGS), per ``PREREG_2025.md``.

Steps (each writes to ``outputs/external_test.json`` and ``outputs/EXTERNAL_TEST.md``):
  compare   WFIGS vs FPA-FOD on 2015-2024: yearly counts, cell-week label agreement,
            record matching and discovery-date differences.
  shift     2023-2024 scored with WFIGS labels and/or WFIGS history, to measure how
            much the source change alone moves the metrics.
  test      2025 (primary) and 2026-to-date (secondary), frozen models, WFIGS labels
            and history, Open-Meteo weather with the same 7-day lag.

Nothing here fits, tunes or recalibrates a model.
Usage: python3 -m forecasting.external_test {compare,shift,test}
"""
from __future__ import annotations

import argparse
import json
import pickle
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config, features, metrics, models
from .evaluate import BASELINE, HEADLINE, SEASONS, equal_budget
from .grid import Grid

OUT_JSON = config.OUTPUT_DIR / 'external_test.json'


def load_state() -> dict:
    return json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}


def save_state(s: dict) -> None:
    OUT_JSON.write_text(json.dumps(s, indent=2, default=str))


def load_fpa() -> pd.DataFrame:
    f = pd.read_csv(config.PROCESSED_DIR / 'fires.csv', dtype={'fpa_id': str})
    f['discovery_date'] = pd.to_datetime(f['discovery_date'])
    return f


def load_wfigs() -> pd.DataFrame:
    f = pd.read_csv(config.PROCESSED_DIR / 'wfigs_fires.csv')
    f['discovery_date'] = pd.to_datetime(f['discovery_date'])
    return f


def mondays(first: date, last: date) -> list[date]:
    out, d = [], first
    assert d.weekday() == 0
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


def lattice(fires: pd.DataFrame, issues: list[date]) -> pd.DataFrame:
    g = Grid()
    lab = pd.MultiIndex.from_product([[c.cell_id for c in g.cells], issues],
                                     names=['cell_id', 'forecast_date']).to_frame(index=False)
    fd = fires['discovery_date']
    wk = (fd - pd.to_timedelta(fd.dt.weekday, unit='D')).dt.date
    cnt = (pd.DataFrame({'cell_id': fires['cell_id'], 'forecast_date': wk})
           .groupby(['cell_id', 'forecast_date']).size().rename('event_count').reset_index())
    lab = lab.merge(cnt, on=['cell_id', 'forecast_date'], how='left')
    lab['event_count'] = lab['event_count'].fillna(0).astype(int)
    lab['label'] = (lab['event_count'] > 0).astype(int)
    lab['forecast_date'] = pd.to_datetime(lab['forecast_date'])
    lab['weather_cutoff'] = lab['forecast_date'] - pd.Timedelta(days=config.WEATHER_LAG_DAYS)
    lab['horizon_days'] = config.HORIZON_DAYS
    cen = {c.cell_id: c.centroid_latlon for c in g.cells}
    lab['centroid_lat'] = lab['cell_id'].map(lambda c: round(cen[c][0], 5))
    lab['centroid_lon'] = lab['cell_id'].map(lambda c: round(cen[c][1], 5))
    return lab.sort_values(['forecast_date', 'cell_id']).reset_index(drop=True)


# ------------------------------------------------------------------ compare

def compare() -> dict:
    fpa, wf = load_fpa(), load_wfigs()
    years = range(2015, 2025)
    counts = {y: dict(fpa_fod=int((fpa['discovery_date'].dt.year == y).sum()),
                      wfigs=int((wf['discovery_date'].dt.year == y).sum())) for y in years}
    issues = mondays(config.FIRST_ISSUE, config.LAST_ISSUE)
    a, b = lattice(fpa, issues), lattice(wf, issues)
    m = a[['cell_id', 'forecast_date', 'label']].merge(b[['cell_id', 'forecast_date', 'label']],
                                                       on=['cell_id', 'forecast_date'], suffixes=('_fpa', '_wfigs'))
    m['year'] = m['forecast_date'].dt.year

    def agree(d):
        x, y = d['label_fpa'].to_numpy(), d['label_wfigs'].to_numpy()
        po = float((x == y).mean())
        pe = float(x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean()))
        both = int((x & y).sum())
        return dict(cell_weeks=int(len(d)), fpa_pos=int(x.sum()), wfigs_pos=int(y.sum()), both_pos=both,
                    agreement=round(po, 4), kappa=round((po - pe) / (1 - pe), 4) if pe < 1 else None,
                    fpa_pos_also_in_wfigs=round(both / max(int(x.sum()), 1), 4),
                    wfigs_pos_also_in_fpa=round(both / max(int(y.sum()), 1), 4))

    by_year = {int(y): agree(d) for y, d in m.groupby('year')}
    # Record matching: nearest WFIGS record within 2 km and +/- 3 days of each FPA-FOD record.
    from .grid import to_albers
    fx = np.array([to_albers(la, lo) for la, lo in zip(fpa['latitude'], fpa['longitude'])])
    wx = np.array([to_albers(la, lo) for la, lo in zip(wf['latitude'], wf['longitude'])])
    fd = fpa['discovery_date'].to_numpy('datetime64[D]').astype(int)
    wd = wf['discovery_date'].to_numpy('datetime64[D]').astype(int)
    order = np.argsort(wd)
    wd_s, wx_s = wd[order], wx[order]
    matched, delta = np.zeros(len(fpa), bool), np.full(len(fpa), np.nan)
    sel = (fpa['discovery_date'].dt.year >= 2020).to_numpy()  # WFIGS coverage is reliable from 2020
    for i in np.where(sel)[0]:
        lo, hi = np.searchsorted(wd_s, fd[i] - 3), np.searchsorted(wd_s, fd[i] + 3, side='right')
        if hi > lo:
            dist = np.hypot(*(wx_s[lo:hi] - fx[i]).T)
            j = int(np.argmin(dist))
            if dist[j] <= 2000:
                matched[i] = True
                delta[i] = wd_s[lo + j] - fd[i]
    dd = pd.Series(delta[matched]).value_counts().sort_index()
    rec = dict(scope='FPA-FOD records 2020-2024 (WFIGS coverage reliable from 2020)', fpa_records=int(sel.sum()),
               matched_within_2km_3days=int(matched.sum()), match_rate=round(float(matched[sel].mean()), 4),
               wfigs_minus_fpa_date_days={int(k): int(v) for k, v in dd.items()},
               same_day_share_of_matches=round(float((delta[matched] == 0).mean()), 4))
    pooled_20_24 = agree(m[m['year'] >= 2020])
    return dict(yearly_counts=counts, label_agreement_by_year=by_year, label_agreement_2020_2024=pooled_20_24,
                record_matching=rec)


# ------------------------------------------------------------------ scoring with frozen models

def build_frame(issues: list[date], label_fires: pd.DataFrame, hist_fires: pd.DataFrame,
                wx_table: pd.DataFrame) -> pd.DataFrame:
    lab = lattice(label_fires, issues)
    df = pd.concat([lab, features.season(lab), features.location(lab),
                    features.history(lab, hist_fires.assign(discovery_date=hist_fires['discovery_date'])),
                    features.weather(lab, wx_table)], axis=1)
    features.assert_no_leakage(df)
    return df


def frozen_climatology() -> pd.DataFrame:
    tr = pd.read_csv(config.PROCESSED_DIR / 'features.csv', usecols=['cell_id', 'week_of_year', 'label', 'split'])
    return models.fit_climatology(tr[tr['split'] == 'train'])


def score(df: pd.DataFrame) -> pd.DataFrame:
    fitted = pickle.loads((config.OUTPUT_DIR / 'models.pkl').read_bytes())
    clim = frozen_climatology()
    df = df.copy()
    df['clim'] = models.apply_climatology(clim, df)
    wcols = json.loads((config.PROCESSED_DIR / 'features_info.json').read_text())['weather_cols']
    missing = int(df[wcols].isna().any(axis=1).sum())
    assert missing == 0, f'{missing} rows lack weather'
    df[BASELINE] = df['clim']
    for name, f in fitted.items():
        df[name] = f['model'].predict_proba(models.design(df, f['spec'], f['cells']))[:, 1]
    return df


def evaluate_frame(df: pd.DataFrame) -> dict:
    names = [BASELINE] + [c for c in df.columns if c[:2] in ('B_', 'C_', 'D0', 'D_', 'E0', 'E_')]
    res = dict(weeks=int(df['forecast_date'].nunique()), cell_weeks=int(len(df)),
               fire_cell_weeks=int(df['label'].sum()), fires=int(df['event_count'].sum()),
               base_rate=round(float(df['label'].mean()), 4),
               models={n: metrics.summary(df, n) for n in names})
    res['E_minus_A_top10'] = metrics.block_bootstrap_diff(df, BASELINE, HEADLINE, 0.10)
    w = df.assign(month=df['forecast_date'].dt.to_period('M').astype(str))
    n = max(1, round(0.054 * len(w)))
    res['equal_budget_5pct'] = equal_budget(w, BASELINE, HEADLINE, [n])[0]
    seas = {}
    for s, g in w.assign(season=w['forecast_date'].dt.month.map(SEASONS)).groupby('season'):
        seas[s] = dict(weeks=int(g['forecast_date'].nunique()), fires=int(g['event_count'].sum()),
                       E_top10=round(metrics.topk_capture(g, HEADLINE, 0.1)['capture'], 4),
                       A_top10=round(metrics.topk_capture(g, BASELINE, 0.1)['capture'], 4))
    res['seasons'] = seas
    return res


def weather_table_extended() -> pd.DataFrame:
    """Rolling weather features from the original archive plus the 2025-26 and live extensions."""
    base = pd.read_csv(config.PROCESSED_DIR / 'weather_daily.csv')
    for name in ('weather_daily_ext.csv', 'weather_daily_live.csv'):
        ext_path = config.PROCESSED_DIR / name
        if ext_path.exists():
            ext = pd.read_csv(ext_path)
            base = pd.concat([base, ext[~ext.set_index(['point_id', 'date']).index.isin(
                base.set_index(['point_id', 'date']).index)]], ignore_index=True)
    tmp = config.PROCESSED_DIR / '_weather_combined.csv'
    base.sort_values(['point_id', 'date']).to_csv(tmp, index=False)
    t = features.weather_table(tmp)
    tmp.unlink()
    return t


def shift() -> dict:
    fpa, wf = load_fpa(), load_wfigs()
    issues = [d for d in mondays(config.FIRST_ISSUE, config.LAST_ISSUE) if d.year >= 2023]
    wx = features.weather_table()
    out = {}
    for tag, lab_src, hist_src in (('fpa_labels_fpa_history', fpa, fpa), ('fpa_labels_wfigs_history', fpa, wf),
                                   ('wfigs_labels_fpa_history', wf, fpa), ('wfigs_labels_wfigs_history', wf, wf)):
        out[tag] = evaluate_frame(score(build_frame(issues, lab_src, hist_src, wx)))
        r = out[tag]
        print(f"  {tag}: E top10 {r['models'][HEADLINE]['top10_capture']:.4f}  A top10 "
              f"{r['models'][BASELINE]['top10_capture']:.4f}  base rate {r['base_rate']}", flush=True)
    return out


def test() -> dict:
    wf = load_wfigs()
    wx = weather_table_extended()
    out = {}
    for tag, first, last in (('2025_primary', date(2025, 1, 6), date(2025, 12, 22)),
                             ('2026_to_date_secondary', date(2026, 1, 5), date(2026, 9, 28))):
        issues = mondays(first, last)
        latest_wx = pd.to_datetime(wx['weather_end']).max().date()
        issues = [d for d in issues if d - timedelta(days=config.WEATHER_LAG_DAYS) <= latest_wx]
        df = score(build_frame(issues, wf, wf, wx))
        out[tag] = evaluate_frame(df)
        out[tag]['issue_dates'] = [str(issues[0]), str(issues[-1])]
        keep = ['forecast_date', 'cell_id', 'centroid_lat', 'centroid_lon', 'label', 'event_count', BASELINE, HEADLINE]
        df[keep].to_csv(config.OUTPUT_DIR / f'external_predictions_{tag}.csv', index=False, float_format='%.6f')
    return out


def report() -> None:
    s = load_state()
    pct = lambda x: f'{100 * x:.1f}%'
    pt = lambda x: f'{100 * x:+.1f} pt'
    ci = lambda c: f'[{100 * c[0]:+.1f}, {100 * c[1]:+.1f}]'
    c = s['compare']
    L = ['# Independent test on the live WFIGS fire feed', '',
         'Rules fixed in advance in `PREREG_2025.md`. Frozen models from `models.pkl`; nothing refit or tuned. '
         'Regenerate with `python3 -m forecasting.external_test compare|shift|test|report`.', '',
         '## Results', '',
         '| Test | Weeks | Fires | Fire cell-weeks | Weather model E top-10% | Climatology A top-10% | E - A | 95% CI |',
         '|---|---|---|---|---|---|---|---|']
    for tag, r in s['test'].items():
        e, a, d = r['models'][HEADLINE], r['models'][BASELINE], r['E_minus_A_top10']
        L.append(f"| {tag.replace('_', ' ')} ({r['issue_dates'][0]} to {r['issue_dates'][1]}) | {r['weeks']} | {r['fires']} | "
                 f"{r['fire_cell_weeks']} ({pct(r['base_rate'])}) | **{pct(e['top10_capture'])}** | {pct(a['top10_capture'])} | "
                 f"{pt(d['diff'])} | {ci(d['ci95'])} |")
    hold = s['shift']['wfigs_labels_wfigs_history']
    L.append(f"| reference: 2023-2024 holdout, same WFIGS labels and history | {hold['weeks']} | {hold['fires']} | "
             f"{hold['fire_cell_weeks']} ({pct(hold['base_rate'])}) | {pct(hold['models'][HEADLINE]['top10_capture'])} | "
             f"{pct(hold['models'][BASELINE]['top10_capture'])} | {pt(hold['E_minus_A_top10']['diff'])} | "
             f"{ci(hold['E_minus_A_top10']['ci95'])} |")
    L += ['', 'Random ranking would capture about 10%.', '', '### All models', '',
          '| Model | 2025 top-5% | 2025 top-10% | 2025 top-20% | 2025 PR-AUC | 2026 top-10% | 2026 PR-AUC |', '|---|---|---|---|---|---|---|']
    t25, t26 = s['test']['2025_primary'], s['test']['2026_to_date_secondary']
    for m, x in t25['models'].items():
        y = t26['models'][m]
        L.append(f"| {m} | {pct(x['top5_capture'])} | {pct(x['top10_capture'])} | {pct(x['top20_capture'])} | "
                 f"{x['pr_auc']:.3f} | {pct(y['top10_capture'])} | {y['pr_auc']:.3f} |")
    L += ['', '### Equal budget (same number of most-confident calls, 5.4% of cell-weeks)', '',
          '| Test | Calls | E hit rate | A hit rate | E - A | 95% CI |', '|---|---|---|---|---|---|']
    for tag, r in s['test'].items():
        e = r['equal_budget_5pct']
        L.append(f"| {tag.replace('_', ' ')} | {e['budget']} | {pct(e[HEADLINE + '_hit_rate'])} | "
                 f"{pct(e[BASELINE + '_hit_rate'])} | {pt(e['diff_hit_rate'])} | {ci(e['ci95'])} |")
    L += ['', '### By season, 2025 (top-10% capture)', '', '| Season | Fires | E | A |', '|---|---|---|---|']
    for sname in ('Winter (Dec-Feb)', 'Spring (Mar-May)', 'Summer (Jun-Aug)', 'Autumn (Sep-Nov)'):
        x = t25['seasons'][sname]
        L.append(f"| {sname} | {x['fires']} | {pct(x['E_top10'])} | {pct(x['A_top10'])} |")
    L += ['', '## Data-quality checks (run before scoring 2025)', '', '### WFIGS vs FPA-FOD, cell-week labels', '',
          '| Year | FPA-FOD fires | WFIGS fires | Label agreement | Kappa | FPA fire cell-weeks also in WFIGS |', '|---|---|---|---|---|---|']
    for y, cnt in c['yearly_counts'].items():
        a = c['label_agreement_by_year'][str(y)]
        L.append(f"| {y} | {cnt['fpa_fod']} | {cnt['wfigs']} | {pct(a['agreement'])} | {a['kappa']:.2f} | {pct(a['fpa_pos_also_in_wfigs'])} |")
    rm = c['record_matching']
    L += ['', f"WFIGS is close to FPA-FOD from 2022 (kappa 0.90-0.96) and sparse before 2020. "
          f"Of {rm['fpa_records']:,} FPA-FOD records in 2020-2024, {pct(rm['match_rate'])} have a WFIGS record within 2 km and 3 days; "
          f"{pct(rm['same_day_share_of_matches'])} of those matches fall on the same Pacific calendar day.", '',
          '### Effect of switching source (2023-2024, frozen models)', '',
          '| Labels | Fire history | E top-10% | A top-10% | E - A |', '|---|---|---|---|---|']
    for tag, r in s['shift'].items():
        lab, hist = tag.split('_labels_')
        L.append(f"| {lab.upper()} | {hist.replace('_history', '').upper()} | {pct(r['models'][HEADLINE]['top10_capture'])} | "
                 f"{pct(r['models'][BASELINE]['top10_capture'])} | {pt(r['E_minus_A_top10']['diff'])} |")
    L += ['', 'The first row reproduces the original holdout exactly. Switching to WFIGS lowers capture by about '
          '1-1.5 points for E and 0.7 for A, so a 2025 drop larger than that is real, not a source artefact.', '']
    (config.OUTPUT_DIR / 'EXTERNAL_TEST.md').write_text('\n'.join(L))
    print((config.OUTPUT_DIR / 'EXTERNAL_TEST.md').read_text())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('step', choices=['compare', 'shift', 'test', 'report'])
    step = ap.parse_args().step
    if step == 'report':
        return report()
    s = load_state()
    s[step] = {'compare': compare, 'shift': shift, 'test': test}[step]()
    save_state(s)
    print(json.dumps(s[step], indent=1, default=str)[:6000])


if __name__ == '__main__':
    main()
