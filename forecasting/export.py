"""Export the demo-week GeoJSON layers and a standalone before/after HTML map.

Demo week rule (fixed before inspecting any model score for it): the holdout
week containing the discovery of the 2024 Park Fire (FPA-FOD, 24 July 2024,
Butte County), i.e. issue date Monday 22 July 2024. The HTML also lets a viewer
step through every holdout week, so the demo is not a single hand-picked week.

Usage: python3 -m forecasting.export
"""
from __future__ import annotations

import json

import pandas as pd

from . import config
from .grid import Grid

DEMO_ISSUE = '2024-07-22'
BASELINE = 'A_climatology'


def headline_model(metrics_json: dict) -> str:
    """Weather-using model with the best *validation* top-10% capture."""
    val = metrics_json['results']['validation']
    cands = [k for k in val if 'weather' in k]
    return max(cands, key=lambda k: (val[k]['top10_capture'], val[k]['pr_auc']))


def weekly_rank(df: pd.DataFrame) -> pd.Series:
    return df.groupby(['forecast_date', 'model_name'])['risk_score'].rank(ascending=False, method='min')


def main() -> None:
    m = json.loads((config.OUTPUT_DIR / 'metrics.json').read_text())
    fusion = headline_model(m)
    preds = pd.read_csv(config.OUTPUT_DIR / 'holdout_predictions.csv')
    preds = preds[preds['model_name'].isin([BASELINE, fusion])].copy()
    preds['rank'] = weekly_rank(preds).astype(int)
    fires = pd.read_csv(config.PROCESSED_DIR / 'fires.csv')
    grid = Grid()
    ncell = len(grid.cells)
    top_n = max(1, round(0.10 * ncell))

    # ---- forecast_map.geojson: one held-out week, risk only (no outcomes) ----
    wk = preds[preds['forecast_date'] == DEMO_ISSUE]
    feats = []
    for cell in grid.cells:
        props = dict(cell_id=cell.cell_id, forecast_date=DEMO_ISSUE, horizon_days=config.HORIZON_DAYS,
                     window_end=str((pd.Timestamp(DEMO_ISSUE) + pd.Timedelta(days=6)).date()),
                     weather_cutoff=str((pd.Timestamp(DEMO_ISSUE) - pd.Timedelta(days=config.WEATHER_LAG_DAYS)).date()))
        for name, tag in ((fusion, 'fusion'), (BASELINE, 'baseline')):
            r = wk[(wk['cell_id'] == cell.cell_id) & (wk['model_name'] == name)].iloc[0]
            props[f'{tag}_risk_score'] = float(r['risk_score'])
            props[f'{tag}_rank'] = int(r['rank'])
            props[f'{tag}_top10pct'] = bool(r['rank'] <= top_n)
        props['fusion_model'], props['baseline_model'] = fusion, BASELINE
        feats.append(dict(type='Feature', properties=props,
                          geometry=dict(type='Polygon', coordinates=[cell.polygon_lonlat()])))
    fc = dict(type='FeatureCollection',
              name=f'ember_forecast_{DEMO_ISSUE}',
              crs_note='Coordinates WGS84/NAD83 lon,lat (EPSG:4326 order per RFC 7946); cells are 25 km squares in EPSG:3310',
              description=('Risk scores rank cells for >=1 newly reported wildfire in the 7 days from forecast_date. '
                           'Scores are relative risk, not calibrated probabilities. Inputs end at weather_cutoff.'),
              features=feats)
    (config.OUTPUT_DIR / 'forecast_map.geojson').write_text(json.dumps(fc))

    # ---- observed_events.geojson: the subsequent outcome, reveal layer only ----
    end = (pd.Timestamp(DEMO_ISSUE) + pd.Timedelta(days=6)).date().isoformat()
    obs = fires[(fires['discovery_date'] >= DEMO_ISSUE) & (fires['discovery_date'] <= end)]
    ev = [dict(type='Feature', geometry=dict(type='Point', coordinates=[round(r.longitude, 5), round(r.latitude, 5)]),
               properties=dict(fpa_id=r.fpa_id, fire_name=r.fire_name if isinstance(r.fire_name, str) else None,
                               discovery_date=r.discovery_date, cell_id=r.cell_id,
                               final_size_acres_audit_only=r.audit_fire_size_ac))
          for r in obs.itertuples()]
    (config.OUTPUT_DIR / 'observed_events.geojson').write_text(json.dumps(dict(
        type='FeatureCollection', name=f'ember_observed_{DEMO_ISSUE}_{end}',
        description='FPA-FOD fires discovered during the forecast window. Evaluation/reveal layer only; never a model input.',
        features=ev)))

    # ---- all holdout weeks for the interactive page ----
    weeks = {}
    hold_fires = fires[fires['discovery_date'] >= '2023-01-02']
    for d, g in preds.groupby('forecast_date'):
        end_d = (pd.Timestamp(d) + pd.Timedelta(days=6)).date().isoformat()
        fw = hold_fires[(hold_fires['discovery_date'] >= d) & (hold_fires['discovery_date'] <= end_d)]
        weeks[d] = dict(
            fusion={r.cell_id: [round(r.risk_score, 5), int(r.rank)] for r in g[g.model_name == fusion].itertuples()},
            baseline={r.cell_id: [round(r.risk_score, 5), int(r.rank)] for r in g[g.model_name == BASELINE].itertuples()},
            fires=[[round(r.latitude, 4), round(r.longitude, 4), r.cell_id,
                    r.fire_name if isinstance(r.fire_name, str) else '', r.discovery_date] for r in fw.itertuples()])
    cells = {c.cell_id: c.polygon_lonlat(2) for c in grid.cells}
    hold = m['results']['holdout']
    summary = dict(fusion=fusion, baseline=BASELINE, top_n=top_n, demo=DEMO_ISSUE,
                   fusion_top10=hold[fusion]['top10_capture'], baseline_top10=hold[BASELINE]['top10_capture'],
                   holdout_events=hold[BASELINE]['events'], weeks=hold[BASELINE]['weeks'])
    sig = [t for t in m['holdout_significance'] if t['candidate'] == fusion and t['baseline'] == BASELINE]
    summary['diff'] = sig[0] if sig else None
    html = (config.PKG / 'map_template.html').read_text()
    html = html.replace('/*__DATA__*/', 'const DATA=' + json.dumps(dict(cells=cells, weeks=weeks, summary=summary)) + ';')
    (config.OUTPUT_DIR / 'forecast_map.html').write_text(html)
    print(f'headline fusion model (by validation): {fusion}; demo week {DEMO_ISSUE}; '
          f'{len(ev)} observed fires in window; {len(weeks)} holdout weeks in HTML')


if __name__ == '__main__':
    main()
