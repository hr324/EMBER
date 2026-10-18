#!/usr/bin/env python3
"""OPTIONAL geospatial preprocessing OUTSIDE LinuxONE native critical path.

Sample rasterio-readable pre-fire DEM and/or vegetation-derived fuel-factor
GeoTIFF to CSV matching inference lattice. The fuel raster must already be a
valid, documented conversion to relative speed multiplier, not unprocessed
LANDFIRE categorical fuel codes. This script intentionally refuses raw classes.
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wildfire.cli import read_detections
from wildfire.features import cluster_detections
from wildfire.graph import build_grid


def sample_raster(dataset,points):
    """Reproject EPSG:4326 lat/lon sampling coordinates to source raster CRS."""
    from rasterio.warp import transform
    lon=[n.lon for n in points];lat=[n.lat for n in points]
    rx,ry=transform('EPSG:4326',dataset.crs,lon,lat)
    for value in dataset.sample(zip(rx,ry),masked=True):
        v=value[0]
        yield None if getattr(v,'mask',False) or not float(v)==float(v) else float(v)


def main()->None:
    """Generate portable grid covariates that match fixed cell width/margin."""
    parser=argparse.ArgumentParser()
    parser.add_argument('--detections',required=True);parser.add_argument('--dem')
    parser.add_argument('--fuel-factor-raster',help='Already converted relative-spread multiplier (NOT raw categorical LANDFIRE)')
    parser.add_argument('--output',required=True);parser.add_argument('--cell-m',type=float,default=850.)
    parser.add_argument('--margin-km',type=float,default=9.)
    args=parser.parse_args()
    if not (args.dem or args.fuel_factor_raster):parser.error('Provide at least one raster')
    try:import rasterio
    except ImportError:parser.error('Install the geo extra on preprocessing host: pip install -e .[geo]')
    detections=read_detections(args.detections)
    grid=build_grid(cluster_detections(detections),args.cell_m,args.margin_km)
    def get_samples(path):
        if not path:return [None]*len(grid.nodes)
        with rasterio.open(path) as dataset:
            return list(sample_raster(dataset,grid.nodes))
    elevations=get_samples(args.dem);fuels=get_samples(args.fuel_factor_raster)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with open(out,'w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['latitude','longitude','elevation_m','fuel_factor'])
        for n,e,f in zip(grid.nodes,elevations,fuels):
            writer.writerow([n.lat,n.lon,'' if e is None else e,'' if f is None else f])
    metadata={'input_dem':args.dem,'input_fuel_factor':args.fuel_factor_raster,'cell_m':args.cell_m,
              'margin_km':args.margin_km,'fuel_factor_requires_independent_documented_conversion':True}
    out.with_suffix('.meta.json').write_text(json.dumps(metadata,indent=2))
    print('Saved',out,'with',len(grid.nodes),'grid samples')

if __name__=='__main__':main()
