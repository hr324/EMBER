"""Regression tests for the data, stronger baseline, and population upgrade."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from wildfire.population import annotate_priority
import expand_fire_dataset as expand


class TestFireExpansion(unittest.TestCase):
    """Check event metadata parsing, AOIs, and geographic deduplication."""
    def test_eonet_record_parsing(self):
        """NASA GeoJSON points select archival downloads but not model inputs."""
        event={'id':'EONET-0033','title':'Example Fire','geometry':[
            {'date':'2023-06-12T00:00:00Z','type':'Point','coordinates':[-120.2,39.5]},
            {'date':'2023-06-13T00:00:00Z','type':'Point','coordinates':[-120.1,39.6]}]}
        case=expand.event_candidate(event,-125,32,-114,42)
        self.assertEqual(case['date'],'2023-06-12')
        self.assertAlmostEqual(case['lat'],39.5)
        self.assertEqual(len(expand.archive_bbox(case,25).split(',')),4)

    def test_reject_outside_and_nearby_duplicate(self):
        """Non-California events are discarded and neighbouring events deduplicated."""
        event={'title':'Other','geometry':[{'date':'2021-05-02','type':'Point','coordinates':[-72,40]}]}
        self.assertIsNone(expand.event_candidate(event,-125,32,-114,42))
        first={'date':'2021-05-01','lat':39.7,'lon':-121.3}
        second={'date':'2021-05-02','lat':39.75,'lon':-121.32}
        self.assertTrue(expand.nearby_duplicate(second,[first],25))


class TestPopulation(unittest.TestCase):
    """Ensure the exposure score is deterministic and never invents residents."""
    def test_population_ranking(self):
        """A lower forecast score may outrank a remote cell with few residents."""
        forecast=[[39.8,-121.4,.9],[39.81,-121.41,.7],[39.9,-121.5,.3]]
        result=annotate_priority(forecast,[2,1500,0],limit=10)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['forecast_rank'],2)
        self.assertEqual(result[0]['population_estimate'],1500)
        self.assertFalse('probability' in result[0])

    def test_wrong_lengths_rejected(self):
        """Never silently misalign forecast cells and population raster values."""
        with self.assertRaises(ValueError):annotate_priority([[0,0,.5]],[])

    @unittest.skipUnless(importlib.util.find_spec('rasterio'),'rasterio optional on preprocessing host')
    def test_raster_population_overlay(self):
        """Area-weighted GIS integration uses GeoTIFF people-per-pixel values."""
        import numpy as np
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin
        from enrich_population import cell_population,enrich_replay
        array=np.ones((7,7),dtype='float32')*100
        profile={'driver':'GTiff','height':7,'width':7,'count':1,'dtype':'float32',
                 'crs':'EPSG:4326','transform':from_origin(-121.54,39.84,.01,.01)}
        with MemoryFile() as mem:
            with mem.open(**profile) as out:out.write(array,1)
            with mem.open() as raster:
                residents=cell_population(raster,39.8,-121.5,2000)
                self.assertGreater(residents,200)
                self.assertLess(residents,1300)
                example={'frames':[{'cell_m':2000,'forecast':[[39.8,-121.5,.9]]}]}
                updated=enrich_replay(example,raster,[],2017)
                self.assertTrue(updated['frames'][0]['population_priorities'])
                self.assertEqual(updated['population_metadata']['year'],2017)


@unittest.skipUnless(importlib.util.find_spec('torch'),'PyTorch optional')
class TestStrongerBaseline(unittest.TestCase):
    """Verify the stronger comparison uses only current observations."""
    def test_baseline_label_independence(self):
        """Later detections must not change the distance-baseline score vector."""
        import gnn_forecast as g
        passes=g.get_passes(g.load_firms(ROOT/'data/synthetic/toy_firms.csv'))
        x=g.build_example('toy',passes[:1],None,[],cell_m=1500,margin_km=7,max_cells=1000)
        y=g.build_example('toy',passes[:1],passes[1],[],cell_m=1500,margin_km=7,max_cells=1000)
        self.assertTrue(g.torch.equal(g.proximity_baseline(x),g.proximity_baseline(y)))
        self.assertGreater(g.average_precision(g.proximity_baseline(y),y.label),0)


if __name__=='__main__':unittest.main()
