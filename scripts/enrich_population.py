#!/usr/bin/env python3
"""Add WorldPop population estimates to an existing GNN forecast replay.

Uses ONLY pretrained GNN forecast rankings and a historical population raster.
NEVER adds population to GNN features, never retrains, and does not touch labels.
Run where rasterio is available (Windows or a preprocessing computer); the
resulting JSON requires no native geospatial packages on LinuxONE.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
from urllib.request import urlopen, Request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wildfire.population import annotate_priority

WORLDPOP='https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/{year}/USA/usa_ppp_{year}_1km_Aggregated.tif'
CENSUS='https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_gaz_place_06.txt'


def download(url: str, out: Path) -> Path:
    """Fetch a public reference file without introducing API keys."""
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.is_file() and out.stat().st_size>100: return out
    partial=out.with_suffix(out.suffix+'.part')
    try:
        with urlopen(Request(url,headers={'User-Agent':'EMBER-Research/1.0'}), timeout=120) as src, open(partial,'wb') as dst:
            while True:
                buf=src.read(2**20)
                if not buf:break
                dst.write(buf)
        if partial.stat().st_size<100:raise ValueError('Downloaded file unexpectedly small')
        partial.replace(out)
    finally:
        if partial.exists():partial.unlink()
    return out


def load_ca_places(path: Path) -> list[dict]:
    """Load Census reference coordinates for nearest-place names only.

    The Gazetteer contains representative place coordinates, not town outlines.
    """
    result=[]
    with open(path,encoding='utf-8-sig',newline='') as handle:
        for row in csv.DictReader(handle,delimiter='\t'):
            try:
                row={k.strip():v.strip() for k,v in row.items() if k}
                result.append({'name':row['NAME'],'latitude':float(row['INTPTLAT']),
                               'longitude':float(row['INTPTLONG'])})
            except (KeyError,TypeError,ValueError):continue
    return result


def cell_population(raster, lat: float, lon: float, cell_m: float) -> float:
    """Area-weighted sum of WorldPop people-per-pixel inside a forecast cell.

    A small WGS84 rectangle approximates the 2 km local projection grid.
    Fractional pixel intersection avoids assigning entire raster pixels to
    adjacent cells. The estimate is NOT a direct count of affected people.
    """
    from rasterio.windows import Window
    dlat=cell_m/2/111320
    dlon=cell_m/2/(111320*max(.2,math.cos(math.radians(lat))))
    w,e=lon-dlon,lon+dlon
    s,n=lat-dlat,lat+dlat
    col0,row0=~raster.transform*(w,n)
    col1,row1=~raster.transform*(e,s)
    x0=max(0,math.floor(min(col0,col1)));x1=min(raster.width,math.ceil(max(col0,col1)))
    y0=max(0,math.floor(min(row0,row1)));y1=min(raster.height,math.ceil(max(row0,row1)))
    if x0>=x1 or y0>=y1:return 0.
    values=raster.read(1,window=Window(x0,y0,x1-x0,y1-y0),masked=True)
    total=0.
    for r in range(y0,y1):
        for c in range(x0,x1):
            raw=values[r-y0,c-x0]
            if bool(getattr(raw,'mask',False)) or not math.isfinite(float(raw)) or float(raw)<0:continue
            a,b=raster.transform*(c,r)
            d,f=raster.transform*(c+1,r+1)
            pixel_west,pixel_east=sorted((a,d));pixel_south,pixel_north=sorted((b,f))
            overlap=(max(0,min(e,pixel_east)-max(w,pixel_west)) *
                     max(0,min(n,pixel_north)-max(s,pixel_south)))
            pixel_area=(pixel_east-pixel_west)*(pixel_north-pixel_south)
            if pixel_area>0:total+=float(raw)*overlap/pixel_area
    return max(0.,total)


def enrich_replay(replay: dict, raster, places: list[dict], year: int) -> dict:
    """Write transparent population and ranking metadata for each forecast pass."""
    if raster.crs is None or raster.crs.to_epsg()!=4326:
        raise ValueError('Expected WorldPop EPSG:4326 raster; reproject other population rasters first')
    for frame in replay.get('frames',[]):
        # Prefer cells not detected in the latest pass for decision-focused exposure.
        # Fall back to overall ranking for legacy replays.
        cells=frame.get('forecast_new') or frame.get('forecast',[])
        counts=[cell_population(raster,cell[0],cell[1],frame['cell_m']) for cell in cells]
        frame['population_priorities']=annotate_priority(cells,counts,places,limit=10)
        frame['population_forecast_top25']=round(sum(counts[:min(25,len(counts))]))
    replay['population_metadata']={
        'raster':f'WorldPop USA people-per-pixel 1km {year}',
        'source':WORLDPOP.format(year=year),'year':year,
        'town_names_source':CENSUS if places else None,
        'population_type':'Estimated residents within model-ranked cells (census model raster), NOT threatened/exposed individuals',
        'priority_formula':'uncalibrated GNN ranking score * log(1 + estimated residents in cell)',
        'uncertainty':'Model scores uncalibrated; population year not necessarily incident year; no operational evacuation use',
        'coverage_note':'Candidate priorities restricted to top-ranked expansion cells (if available), not full geographic risk'}
    return replay


def main():
    """Download WorldPop/Census references optionally and enrich existing replay JSON."""
    parser=argparse.ArgumentParser(description='Enrich GNN replay with real WorldPop raster')
    parser.add_argument('--replay',default='frontend/gnn_replay.json')
    parser.add_argument('--output',default='frontend/gnn_replay.json')
    parser.add_argument('--tif',help='Use an already downloaded WorldPop 1km GeoTIFF')
    parser.add_argument('--year',type=int,choices=range(2000,2021),default=2017,
                        help='For Camp 2018 use 2017, avoiding future/post-fire population leakage')
    parser.add_argument('--download',action='store_true',help='Download the public ~50 MB WorldPop raster')
    parser.add_argument('--places',action='store_true',help='Add nearest California Census place names')
    args=parser.parse_args()
    try:import rasterio
    except ImportError:raise SystemExit('Install rasterio on your preprocessing machine: py -m pip install rasterio (NOT needed for LinuxONE inference)')
    path=Path(args.tif) if args.tif else Path('data/external')/f'worldpop_usa_{args.year}_1km.tif'
    if args.download:
        download(WORLDPOP.format(year=args.year),path)
    if not path.exists():parser.error('Population raster missing: provide --tif or --download')
    places=[]
    if args.places:
        try:
            places=load_ca_places(download(CENSUS,Path('data/external/2024_gaz_place_06.txt')))
        except Exception as exc:
            print(f'Place-name download unavailable: {exc}. Continuing with coordinates.',file=sys.stderr)
    replay=json.loads(Path(args.replay).read_text())
    with rasterio.open(path) as raster:enrich_replay(replay,raster,places,args.year)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(replay))
    print(json.dumps({'saved':str(output),'frames':len(replay.get('frames',[])),
                      'raster':str(path),'named_places':len(places),'year':args.year},indent=2))


if __name__=='__main__':main()
