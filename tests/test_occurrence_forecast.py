"""Tests for the weekly occurrence forecast (forecasting/).

Uses small verbatim extracts of real FPA-FOD and Open-Meteo responses in
forecasting/samples/; no simulated fires or weather.
"""
import importlib.util
import json
import pickle
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'forecasting' / 'samples'
HAS_STACK = all(importlib.util.find_spec(m) for m in ('numpy', 'pandas', 'sklearn'))

from forecasting import config, grid  # noqa: E402  (stdlib only)


class TestProjectionAndGrid(unittest.TestCase):
    # Reference values from pyproj 3.x, EPSG:4269 -> EPSG:3310.
    REF = [((39.0, -122.8), (-242236.298, 112916.688)),
           ((41.0, -120.8), (-67345.020, 331785.282)),
           ((39.81, -121.43), (-122369.242, 200273.472))]

    def test_albers_matches_reference(self):
        for (lat, lon), (x, y) in self.REF:
            gx, gy = grid.to_albers(lat, lon)
            self.assertAlmostEqual(gx, x, delta=0.01)
            self.assertAlmostEqual(gy, y, delta=0.01)

    def test_inverse_roundtrip(self):
        for (lat, lon), _ in self.REF:
            rlat, rlon = grid.from_albers(*grid.to_albers(lat, lon))
            self.assertAlmostEqual(rlat, lat, places=9)
            self.assertAlmostEqual(rlon, lon, places=9)

    def test_lattice_and_cell_assignment(self):
        g = grid.Grid()
        self.assertEqual(len(g.cells), 80)
        for c in g.cells:  # centroid falls in its own cell; cells are exactly 25 km
            self.assertEqual(g.cell_of(*c.centroid_latlon), c.cell_id)
            self.assertEqual(c.size, 25_000)
        # 2024 Park Fire discovery point (FPA-FOD) -> cell c04_03
        self.assertEqual(g.cell_of(39.818579, -121.802601), 'c04_03')
        self.assertIsNone(g.cell_of(34.05, -118.25))  # Los Angeles is outside

    def test_split_boundaries(self):
        self.assertEqual(config.split_of(date(2020, 12, 28)), 'train')
        self.assertEqual(config.split_of(date(2021, 1, 4)), 'validation')
        self.assertEqual(config.split_of(date(2022, 12, 26)), 'validation')
        self.assertEqual(config.split_of(date(2023, 1, 2)), 'holdout')


@unittest.skipUnless(HAS_STACK, 'numpy/pandas/scikit-learn not installed')
class TestLabelsFeaturesLeakage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        from forecasting import fetch_fires, labels
        raw = json.loads((SAMPLES / 'fpa_fod_2024_jul17_31.json').read_text())
        fires, cls.audit = fetch_fires.clean([f['attributes'] for f in raw['features']])
        cls.fires = pd.DataFrame(fires)
        cls.fires['discovery_date'] = pd.to_datetime(cls.fires['discovery_date']).dt.date
        cls.labels = labels.build(cls.fires)
        cls.pd = pd

    def test_dates_match_day_of_year(self):
        self.assertEqual(self.audit['doy_mismatch'], 0)

    def test_every_fire_labelled_in_its_week(self):
        lab, pd = self.labels, self.pd
        wk = lab[lab['forecast_date'] == date(2024, 7, 22)]
        f = self.fires
        inwin = f[(f['discovery_date'] >= date(2024, 7, 22)) & (f['discovery_date'] <= date(2024, 7, 28))]
        self.assertEqual(int(wk['event_count'].sum()), len(inwin))
        park = wk[wk['cell_id'] == 'c04_03'].iloc[0]
        self.assertEqual(park['label'], 1)
        # zero-labelled cells have no fires in the window
        zero_cells = set(wk.loc[wk['label'] == 0, 'cell_id'])
        self.assertFalse(zero_cells & set(inwin['cell_id']))

    def test_history_excludes_issue_day_and_future(self):
        from forecasting.features import history
        pd = self.pd
        lab = self.labels[self.labels['forecast_date'] == date(2024, 7, 22)].reset_index(drop=True)
        fires = self.fires.assign(discovery_date=pd.to_datetime(self.fires['discovery_date']))
        h = history(lab, fires)
        before = fires[(fires['discovery_date'] < '2024-07-22') & (fires['discovery_date'] >= '2024-06-22')]
        expect = before.groupby('cell_id').size()
        for i, r in lab.iterrows():
            self.assertEqual(h.loc[i, 'hist_cell_30'], expect.get(r['cell_id'], 0))
        # Adding fires on/after the issue date must not change any history feature.
        extra = fires.copy()
        extra['discovery_date'] = pd.Timestamp('2024-07-22')
        h2 = history(lab, pd.concat([fires, extra]))
        self.assertTrue((h2[['hist_cell_30', 'hist_nbr_30']].to_numpy() == h[['hist_cell_30', 'hist_nbr_30']].to_numpy()).all())

    def test_weather_window_ends_at_lag_cutoff(self):
        """Corrupting every day after the cutoff leaves the features unchanged."""
        import tempfile
        import numpy as np
        from forecasting import features
        from forecasting.fetch_weather import DAILY_VARS
        pd = self.pd
        d = json.loads((SAMPLES / 'openmeteo_w02_01_2024.json').read_text())['daily']
        wx = pd.DataFrame({'point_id': 'w02_01', 'date': d['time'], **{v: d[v] for v in DAILY_VARS}})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p1, p2 = Path(tmp.name) / 'wx1.csv', Path(tmp.name) / 'wx2.csv'
        wx.to_csv(p1, index=False)
        wx2 = wx.copy()
        late = pd.to_datetime(wx2['date']) > pd.Timestamp('2024-07-15')
        for v in DAILY_VARS:
            wx2.loc[late, v] = 9999.0
        wx2.to_csv(p2, index=False)
        lab = self.labels[(self.labels['forecast_date'] == date(2024, 7, 22)) & (self.labels['cell_id'] == 'c04_03')]
        lab = lab.assign(weather_cutoff=pd.to_datetime(lab['weather_cutoff']))
        a = features.weather(lab, features.weather_table(p1))
        b = features.weather(lab, features.weather_table(p2))
        cols = [c for c in a.columns if c not in ('weather_point', 'weather_latest_date')]
        self.assertTrue(np.allclose(a[cols].to_numpy(float), b[cols].to_numpy(float), equal_nan=True))
        self.assertEqual(str(a['weather_latest_date'].iloc[0].date()), '2024-07-15')
        # Real values: 7-day mean of daily max temperature ending 2024-07-15
        win = wx[(wx['date'] >= '2024-07-09') & (wx['date'] <= '2024-07-15')]['temperature_2m_max'].mean()
        self.assertAlmostEqual(a['tmax_mean_7'].iloc[0], win, places=6)


class TestWfigsCleaning(unittest.TestCase):
    """Live-feed rules from PREREG_2025.md, on verbatim WFIGS records."""

    @classmethod
    def setUpClass(cls):
        from forecasting import fetch_wfigs
        raw = json.loads((SAMPLES / 'wfigs_2024_jul23_25.json').read_text())['features']
        cls.rows = [dict(f['attributes'], _gx=(f.get('geometry') or {}).get('x'), _gy=(f.get('geometry') or {}).get('y'))
                    for f in raw]
        cls.clean = staticmethod(fetch_wfigs.clean)

    def test_discovery_date_is_pacific_calendar_day(self):
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        out, audit = self.clean(self.rows)
        self.assertGreater(audit['utc_date_differs_from_pacific_date'], 0)
        for r in out:
            utc = datetime.fromisoformat(r['discovery_utc'])
            self.assertEqual(r['discovery_date'], utc.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat())
        # BAXTER: 2024-07-24 00:42 UTC is 23 July in California.
        baxter = [r for r in out if r['fire_name'] == 'BAXTER']
        self.assertEqual(baxter[0]['discovery_date'], '2024-07-23')

    def test_duplicates_removed(self):
        out, audit = self.clean(self.rows + self.rows[:3])
        self.assertEqual(audit['duplicate_unique_id'], 3)
        self.assertEqual(len(out), len(self.clean(self.rows)[0]))


@unittest.skipUnless(HAS_STACK, 'numpy/pandas/scikit-learn not installed')
class TestMetricsAndModels(unittest.TestCase):
    def test_capture_shares_ties(self):
        import numpy as np
        from forecasting.metrics import week_capture
        self.assertEqual(week_capture(np.array([3, 2, 2, 2, 1.]), np.array([1, 3, 0, 0, 5.]), 2), 2.0)
        self.assertEqual(week_capture(np.zeros(5), np.ones(5), 1), 1.0)
        self.assertEqual(week_capture(np.arange(10.), np.arange(10.), 10), 45.0)

    def test_model_serialisation_roundtrip(self):
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingClassifier
        rng = np.random.default_rng(0)
        X = rng.normal(size=(200, 3))
        y = (X[:, 0] > 0).astype(int)  # structural check only: no observations are being invented
        m = HistGradientBoostingClassifier(max_iter=20).fit(X, y)
        m2 = pickle.loads(pickle.dumps(m))
        self.assertTrue(np.array_equal(m.predict_proba(X), m2.predict_proba(X)))

    @unittest.skipUnless((config.OUTPUT_DIR / 'metrics.json').exists(), 'run the pipeline first')
    def test_saved_metrics_reproduce_from_predictions(self):
        import pandas as pd
        from forecasting.metrics import topk_capture
        m = json.loads((config.OUTPUT_DIR / 'metrics.json').read_text())
        p = pd.read_csv(config.OUTPUT_DIR / 'holdout_predictions.csv')
        for name, res in m['results']['holdout'].items():
            sub = p[p['model_name'] == name]
            cap = topk_capture(sub, 'risk_score', 0.10)['capture']
            self.assertAlmostEqual(cap, res['top10_capture'], places=3, msg=name)
            self.assertTrue(pd.to_datetime(sub['forecast_date']).dt.year.between(2023, 2024).all())

    @unittest.skipUnless((config.PROCESSED_DIR / 'features.csv').exists(), 'run the pipeline first')
    def test_full_feature_table_respects_cutoffs(self):
        import pandas as pd
        from forecasting.features import assert_no_leakage
        df = pd.read_csv(config.PROCESSED_DIR / 'features.csv',
                         usecols=['forecast_date', 'weather_latest_date', 'history_latest_date'])
        assert_no_leakage(df)

    def test_climatology_training_rows_exclude_own_year(self):
        import numpy as np
        import pandas as pd
        from forecasting import models
        p = config.PROCESSED_DIR / 'features.csv'
        if not p.exists():
            self.skipTest('run the pipeline first')
        df = pd.read_csv(p, usecols=['cell_id', 'forecast_date', 'week_of_year', 'label', 'split'],
                         parse_dates=['forecast_date'])
        a = models.add_climatology_feature(df)
        flipped = df.copy()
        m15 = flipped['forecast_date'].dt.year == 2015
        flipped.loc[m15, 'label'] = 1 - flipped.loc[m15, 'label']
        b = models.add_climatology_feature(flipped)
        r = (a['forecast_date'].dt.year == 2015).to_numpy()
        self.assertTrue(np.allclose(a.loc[r, 'clim'], b.loc[r, 'clim']))


if __name__ == '__main__':
    unittest.main()
