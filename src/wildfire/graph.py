"""Directed spatial spread graph with interpretable wind/terrain/fuel resistance."""
from __future__ import annotations
import csv
import heapq
import math
from dataclasses import dataclass
from pathlib import Path
from .geo import LocalProjection

@dataclass(frozen=True)
class Node:
    """Spatial cell with optional PRE-FIRE covariates."""
    index:int
    x:float
    y:float
    lat:float
    lon:float
    elevation_m:float|None=None
    fuel_factor:float|None=None

@dataclass
class SpatialGrid:
    """A regular lattice whose search extent comes only from hotspot positions."""
    nodes:list[Node]
    projection:LocalProjection
    cell_m:float
    nx:int
    ny:int
    minx:float
    miny:float

    def nearest(self,lat:float,lon:float)->int:
        """Snap latitude/longitude onto grid; clamp only within grid bbox."""
        x,y=self.projection.xy(lat,lon)
        i=max(0,min(self.nx-1,round((x-self.minx)/self.cell_m)))
        j=max(0,min(self.ny-1,round((y-self.miny)/self.cell_m)))
        return j*self.nx+i


def build_grid(clusters:list[dict],cell_m:float=800,margin_km:float=10,
               max_cells:int=12000)->SpatialGrid:
    """Derive candidates ONLY from early observed hotspots (never truth labels)."""
    if not clusters:raise ValueError('Cannot create candidate region without detections')
    if cell_m<100 or margin_km<0: raise ValueError('Bad grid resolution or margin')
    p=LocalProjection(sum(c['latitude'] for c in clusters)/len(clusters),
                      sum(c['longitude'] for c in clusters)/len(clusters))
    xy=[p.xy(c['latitude'],c['longitude']) for c in clusters]
    minx=min(x for x,_ in xy)-margin_km*1000
    maxx=max(x for x,_ in xy)+margin_km*1000
    miny=min(y for _,y in xy)-margin_km*1000
    maxy=max(y for _,y in xy)+margin_km*1000
    nx=math.ceil((maxx-minx)/cell_m)+1;ny=math.ceil((maxy-miny)/cell_m)+1
    if nx*ny>max_cells:
        raise ValueError(f'Grid of {nx*ny} cells exceeds {max_cells}. Increase cell_m or narrow input evidence.')
    nodes=[]
    for j in range(ny):
        for i in range(nx):
            x=minx+i*cell_m;y=miny+j*cell_m
            lat,lon=p.latlon(x,y)
            nodes.append(Node(j*nx+i,x,y,lat,lon))
    return SpatialGrid(nodes,p,cell_m,nx,ny,minx,miny)


def with_covariates(grid:SpatialGrid,path:str|Path,match_radius_m:float|None=None)->SpatialGrid:
    """Attach external pre-fire elevation/fuel samples by nearest valid coordinates.

    Expected CSV: latitude,longitude,elevation_m,fuel_factor. Fuel factor is
    a dimensionless expert-provided relative rate multiplier; no calibration is
    claimed. No covariate cells remain missing (neutral weights, flagged).
    """
    with open(path,newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    if not rows: return grid
    radius=match_radius_m or grid.cell_m*.8
    values={}
    for r in rows:
        try:
            i=grid.nearest(float(r['latitude']),float(r['longitude']))
            x,y=grid.projection.xy(float(r['latitude']),float(r['longitude']))
            if math.dist((x,y),(grid.nodes[i].x,grid.nodes[i].y))<=radius:
                ele=float(r['elevation_m']) if r.get('elevation_m') not in ('',None) else None
                fuel=float(r['fuel_factor']) if r.get('fuel_factor') not in ('',None) else None
                if fuel is not None and not (0.1<=fuel<=5.):raise ValueError('Fuel factor out of bounds')
                values[i]=(ele,fuel)
        except (ValueError,KeyError): continue
    grid.nodes=[Node(n.index,n.x,n.y,n.lat,n.lon,*(values.get(n.index,(None,None)))) for n in grid.nodes]
    return grid

@dataclass(frozen=True)
class SpreadParameters:
    """Explicit hypotheses controlling assumed speed and directional effects."""
    base_speed_mps:float=0.35
    wind_gain:float=0.85
    slope_gain:float=1.6
    use_fuel:bool=True
    wind_direction_offset_deg:float=0.
    min_speed_mps:float=0.04
    max_speed_mps:float=3.5


def build_adjacency(grid:SpatialGrid,wind:dict|None,
                    params:SpreadParameters=SpreadParameters())->tuple[list[list[tuple[int,float]]],dict]:
    """Encode possible neighbour-to-neighbour fire propagation (hours per edge).

    Simplified directional model: log(v/base)=wind_gain*speed/10*dot +
    slope_gain*gradient, multiplied by mean cell fuel. This is deliberately
    not Rothermel and must be treated as a sensitivity model, not physical truth.
    """
    if params.base_speed_mps<=0: raise ValueError('Positive base speed required')
    n=len(grid.nodes);adj=[[] for _ in range(n)]
    east=north=0.
    if wind:
        angle=math.radians(params.wind_direction_offset_deg)
        e0,n0=wind['wind_east_mps'],wind['wind_north_mps']
        east=e0*math.cos(angle)-n0*math.sin(angle)
        north=e0*math.sin(angle)+n0*math.cos(angle)
    speed=math.hypot(east,north)
    available_elevation=sum(v.elevation_m is not None for v in grid.nodes)
    available_fuel=sum(v.fuel_factor is not None for v in grid.nodes)
    for j in range(grid.ny):
        for i in range(grid.nx):
            a=j*grid.nx+i;v=grid.nodes[a]
            for dj in (-1,0,1):
                for di in (-1,0,1):
                    if di==dj==0 or not (0<=i+di<grid.nx and 0<=j+dj<grid.ny):continue
                    b=(j+dj)*grid.nx+i+di;w=grid.nodes[b]
                    distance=grid.cell_m*math.hypot(di,dj)
                    wind_dot=(east*di+north*dj)/(speed*math.hypot(di,dj)) if speed else 0.
                    wind_exp=params.wind_gain*(speed/10.)*wind_dot
                    terrain_slope=((w.elevation_m-v.elevation_m)/distance
                            if v.elevation_m is not None and w.elevation_m is not None else 0.)
                    slope_exp=params.slope_gain*max(-.5,min(.5,terrain_slope))
                    fuels=[q for q in (v.fuel_factor,w.fuel_factor) if q is not None]
                    fuel_factor=(sum(fuels)/len(fuels)) if (params.use_fuel and fuels) else 1.
                    velocity=params.base_speed_mps*math.exp(max(-6,min(6,wind_exp+slope_exp)))*fuel_factor
                    velocity=max(params.min_speed_mps,min(params.max_speed_mps,velocity))
                    adj[a].append((b,distance/velocity/3600.))
    return adj,{'nodes':n,'directed_edges':sum(len(row) for row in adj),
               'wind_used':wind is not None,'elevation_coverage':available_elevation/max(n,1),
               'fuel_coverage':available_fuel/max(n,1),'params':vars(params)}


def reverse_shortest_paths(adjacency:list[list[tuple[int,float]]],target_nodes:list[int])->list[list[float]]:
    """Run reverse Dijkstra from each observed cell, getting every candidate's
    shortest directed travel time TO each observation. Complexity O(K E log V).
    """
    reversed_edges=[[] for _ in adjacency]
    for i,neighbours in enumerate(adjacency):
        for j,cost in neighbours:reversed_edges[j].append((i,cost))
    results=[]
    for dest in target_nodes:
        dist=[math.inf]*len(adjacency);dist[dest]=0.;pq=[(0.,dest)]
        while pq:
            d,node=heapq.heappop(pq)
            if d>dist[node]:continue
            for previous,cost in reversed_edges[node]:
                proposal=d+cost
                if proposal<dist[previous]:dist[previous]=proposal;heapq.heappush(pq,(proposal,previous))
        results.append(dist)
    return results
