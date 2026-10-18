"""Build minimally correlated satellite evidence clusters, not pixel-level pseudo-replicates."""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from .geo import LocalProjection
from .ingest import parse_utc

@dataclass
class ThermalCluster:
    """Spatially joined detections from a single approximate sensor overpass."""
    cluster_id: str
    latitude: float
    longitude: float
    timestamp_utc: str
    n_pixels: int
    confidence: float
    frp_sum: float
    uncertainty_m: float
    instrument: str
    pass_id: int


def cluster_detections(detections: list[dict], *, max_hours: float=10.0,
                       pass_gap_min: float=30, radius_m: float=1250,
                       max_clusters: int=12) -> list[dict]:
    """Cluster nearby hotspots by pass (connected components) and retain early evidence.

    The same pass is represented by independent SPATIAL clusters; closely
    neighbouring raw pixels cannot each overwhelm the likelihood. A bounding
    box alone does not assign detections to a particular fire; users must check
    the resulting map and discard unrelated hotspots.
    """
    if not detections: return []
    detections=sorted(detections,key=lambda r:r['observed_utc'])
    t0=parse_utc(detections[0]['observed_utc'])
    selected=[d for d in detections if (parse_utc(d['observed_utc'])-t0).total_seconds()<=max_hours*3600]
    p=LocalProjection(sum(r['latitude'] for r in selected)/len(selected),
                      sum(r['longitude'] for r in selected)/len(selected))
    # Define physical observation PASS groups by time alone, so interleaved
    # instruments at the same time do not falsely count as independent passes.
    time_groups=[]
    for det in selected:
        timestamp=parse_utc(det['observed_utc'])
        if not time_groups or (timestamp-time_groups[-1][-1][0]).total_seconds()>pass_gap_min*60:
            time_groups.append([])
        time_groups[-1].append((timestamp,det))
    clusters=[]
    for pass_id,time_group in enumerate(time_groups):
        by_instrument={}
        for _,det in time_group:
            key=str(det.get('instrument') or det.get('source') or 'unknown')
            by_instrument.setdefault(key,[]).append(det)
        for instrument,group in by_instrument.items():
            # Spatial hashing keeps neighbour unions near-linear on large FIRMS
            # archived passes; no scikit-learn wheel is required on LinuxONE.
            n=len(group);parent=list(range(n))
            def root(i):
                while i!=parent[i]:
                    parent[i]=parent[parent[i]];i=parent[i]
                return i
            coords=[p.xy(r['latitude'],r['longitude']) for r in group]
            buckets={}
            for i,(x,y) in enumerate(coords):
                cell=(math.floor(x/radius_m),math.floor(y/radius_m))
                for bx in range(cell[0]-1,cell[0]+2):
                    for by in range(cell[1]-1,cell[1]+2):
                        for j in buckets.get((bx,by),[]):
                            if math.dist(coords[i],coords[j])<=radius_m:
                                parent[root(i)]=root(j)
                buckets.setdefault(cell,[]).append(i)
            members={}
            for i in range(n):members.setdefault(root(i),[]).append(i)
            for k,ids in enumerate(members.values()):
                weights=[max(0.25, float(group[i].get('confidence',.6))) for i in ids]
                wsum=sum(weights)
                lat=sum(weights[j]*group[i]['latitude'] for j,i in enumerate(ids))/wsum
                lon=sum(weights[j]*group[i]['longitude'] for j,i in enumerate(ids))/wsum
                timestamp=min(group[i]['observed_utc'] for i in ids)
                # A cluster extent and pixel footprint cannot be a precise boundary.
                x,y=p.xy(lat,lon)
                uncertainty=max(400., max(math.dist(coords[i],(x,y)) for i in ids),
                                max(float(group[i].get('scan_m',375)) for i in ids)/2)
                clusters.append(asdict(ThermalCluster(f'pass{pass_id}-{instrument}-cluster{k}',lat,lon,
                       timestamp,len(ids),sum(weights)/len(weights),
                       sum(float(group[i].get('frp',0)) for i in ids),uncertainty,
                       instrument,pass_id)))
    return sorted(clusters,key=lambda c:(c['timestamp_utc'],-c['n_pixels']))[:max_clusters]


def weather_summary(weather: list[dict], start: str, end: str) -> dict:
    """Vector-average METEOROLOGICAL direction, weighting by wind speed.

    A direction angle of 0 is wind FROM north; resultant u/v point TO east/north.
    The average here is deliberately static; a dynamic weather graph is stretch.
    """
    values=[w for w in weather if start <= w['timestamp_utc'] <= end]
    if not values:
        raise ValueError('No weather observations overlap selected fire timeline')
    east=north=0.
    for w in values:
        a=math.radians(float(w['wind_from_deg']))
        s=float(w['wind_speed_mps'])
        east+=-s*math.sin(a); north+=-s*math.cos(a)
    east/=len(values); north/=len(values)
    speed=math.hypot(east,north)
    # Direction TO, clockwise from north
    to_deg=math.degrees(math.atan2(east,north))%360 if speed else 0.
    return {'wind_east_mps':east,'wind_north_mps':north,
            'wind_speed_mps':speed,'wind_to_deg':to_deg,'n_hours':len(values),
            'mean_relative_humidity':sum(w['relative_humidity'] for w in values)/len(values),
            'approximation':'vector-mean stationary wind across early observation window'}
