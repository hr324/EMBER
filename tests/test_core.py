"""Unit and integration tests (standard-library unittest; runs on LinuxONE)."""
from __future__ import annotations
import json
import math
import tempfile
import unittest
from pathlib import Path
from wildfire.geo import LocalProjection,haversine_km,segment_distance_m
from wildfire.ingest import load_firms,load_weather,observation_gate,datetime_utc
from wildfire.graph import build_grid,build_adjacency,SpreadParameters,reverse_shortest_paths
from wildfire.inference import infer_origin,InferenceOptions,public_result
from wildfire.evidence import build_evidence_graph
from wildfire.evaluation import evaluate_result
from wildfire.service import ApplicationService,ServerSettings

ROOT=Path(__file__).resolve().parents[1]
TOY=ROOT/'data/synthetic'

class TestGeo(unittest.TestCase):
    """Verify geodesic and planar methods used in spatial candidate construction."""
    def test_local_projection_inverse(self):
        p=LocalProjection(39.9,-121.4)
        a,b=p.latlon(*p.xy(39.834,-121.587))
        self.assertAlmostEqual(a,39.834,places=8)
        self.assertAlmostEqual(b,-121.587,places=8)
    def test_distance(self):
        self.assertAlmostEqual(haversine_km(0,0,0,1),111.195,delta=.01)
        self.assertAlmostEqual(segment_distance_m(2,3,0,0,4,0),3.)
    def test_strict_utc(self):
        self.assertEqual(datetime_utc('2018-11-08','633'),'2018-11-08T06:33:00Z')
        with self.assertRaises(ValueError): datetime_utc('2018-11-08','9999')

class TestIngest(unittest.TestCase):
    """Ensure canonical schema, UTC, wind conventions, and independent-pass gate."""
    def test_firms(self):
        det=load_firms(TOY/'toy_firms.csv')
        self.assertEqual(len(det),20)
        self.assertTrue(all(row['observed_utc'].endswith('Z') for row in det))
        self.assertEqual(observation_gate(det)['passes'],4)
    def test_weather(self):
        w=load_weather(TOY/'toy_weather.json')
        self.assertAlmostEqual(w[0]['wind_speed_mps'],7.2)
        self.assertEqual(w[0]['wind_from_deg'],270.)
    def test_invalid_observations(self):
        self.assertFalse(observation_gate([])['usable'])

    def test_canonical_weather_csv(self):
        # Canonical feed already in m/s must NOT be divided by 3.6 again.
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'wind.csv'
            file.write_text('timestamp_utc,wind_speed_mps,wind_from_deg,relative_humidity\n'
                            '2018-11-08T13:00:00Z,7.2,270,22\n')
            wx=load_weather(file)
            self.assertAlmostEqual(wx[0]['wind_speed_mps'],7.2)
            self.assertEqual(wx[0]['wind_from_deg'],270.)

    def test_time_pass_merges_interleaved_instruments(self):
        from wildfire.features import cluster_detections
        t='2018-11-08T13:01:00Z'
        base={'latitude':39.86,'longitude':-121.52,'observed_utc':t,
              'confidence':.75,'frp':10.,'scan_m':375}
        a=dict(base,instrument='VIIRS')
        b=dict(base,instrument='MODIS',longitude=-121.51)
        clusters=cluster_detections([a,b])
        self.assertEqual(len(clusters),2)
        self.assertEqual({c['pass_id'] for c in clusters},{0})

class TestDirectedGraph(unittest.TestCase):
    """Check wind-dependent asymmetry and reverse shortest path semantics."""
    def setUp(self):
        self.grid=build_grid([{'latitude':39.8,'longitude':-121.6}],cell_m=1000,margin_km=1)
    def test_directional_wind(self):
        wind={'wind_east_mps':8.,'wind_north_mps':0.}
        adj,_=build_adjacency(self.grid,wind,SpreadParameters(base_speed_mps=.4,wind_gain=1.))
        node=self.grid.nearest(39.8,-121.6)
        east=node+1
        forward=dict(adj[node])[east]
        backward=dict(adj[east])[node]
        self.assertLess(forward,backward)
    def test_reverse_paths(self):
        adj=[[(1,1.)],[(2,2.)],[]]
        d=reverse_shortest_paths(adj,[2])[0]
        self.assertEqual(d,[3.,2.,0.])

    def test_external_terrain_covariates(self):
        from wildfire.graph import with_covariates
        v=self.grid.nodes[0]
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'terrain.csv'
            file.write_text('latitude,longitude,elevation_m,fuel_factor\n'
                            f'{v.lat},{v.lon},221,1.4\n')
            with_covariates(self.grid,file)
            _,metadata=build_adjacency(self.grid,None)
            self.assertGreater(metadata['elevation_coverage'],0.)
            self.assertGreater(metadata['fuel_coverage'],0.)

class TestInference(unittest.TestCase):
    """Confirm a complete synthetic workflow and the causal hypothesis firewall."""
    @classmethod
    def setUpClass(cls):
        cls.detections=load_firms(TOY/'toy_firms.csv')
        cls.weather=load_weather(TOY/'toy_weather.json')
        cls.opt=InferenceOptions(cell_m=1000,margin_km=6,ensemble=False)
        cls.model=infer_origin(cls.detections,cls.weather,cls.opt)
    def test_synthetic_reconstruction(self):
        metrics=evaluate_result(self.model,str(TOY/'toy_reference.json'))
        self.assertLess(metrics['model_error_km'],5)
        self.assertTrue(metrics['truth_in_candidate_grid'])
    def test_regions_are_uncalibrated(self):
        self.assertTrue(self.model['regions']['top80']['warning'].startswith('Model-relative'))
        self.assertGreater(self.model['regions']['top80']['cell_count'],0)
    def test_no_ignition_label_in_api_result(self):
        self.assertNotIn('_internal',public_result(self.model))
        self.assertNotIn('cause',public_result(self.model)['best_origin'])
        self.assertNotIn('ground_truth',public_result(self.model))
    def test_causal_associations_do_not_reorder(self):
        ev=build_evidence_graph(self.model,str(TOY/'toy_powerlines.geojson'),str(TOY/'toy_lightning.csv'))
        self.assertTrue(ev['metadata']['candidate_ranking_is_independent_of_hypothesis_edges'])
        self.assertTrue(any(n['kind']=='powerline' for n in ev['nodes']))
        self.assertEqual(build_evidence_graph(self.model)['nodes'][0]['id'],ev['nodes'][0]['id'])
    def test_label_isolation(self):
        # Changing evaluation truth affects METRICS only, not inferred origin.
        with tempfile.TemporaryDirectory() as temp:
            altered=Path(temp)/'reference.json'
            altered.write_text(json.dumps({'fire_id':'TEST','latitude':41.,'longitude':-120.}))
            a=evaluate_result(self.model,str(TOY/'toy_reference.json'))
            b=evaluate_result(self.model,str(altered))
            self.assertNotEqual(a['model_error_km'],b['model_error_km'])
            self.assertTrue(self.model['best_origin']['cell_id']>=0)
    def test_bad_candidate_grid(self):
        with self.assertRaises(ValueError):
            infer_origin(self.detections,self.weather,InferenceOptions(cell_m=100,margin_km=25,max_grid_cells=5))

    def test_server_paths(self):
        service=ApplicationService(ServerSettings(str(TOY/'toy_firms.csv'),str(TOY/'toy_weather.json'),
                                                  powerlines=str(TOY/'toy_powerlines.geojson'),mode='synthetic'))
        self.assertEqual(service.health()['gate']['detections'],20)
        self.assertEqual(service.infer('satellite',1200,5,False)['inference']['variant'],'satellite')
        self.assertIsNotNone(service.context()['powerlines'])

if __name__=='__main__':unittest.main()
