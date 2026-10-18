"""Population-based relative prioritisation of model-ranked forecast cells.

Not emergency risk, not calibrated probabilities, not counts of exposed people.
The underlying GNN is unmodified. No outcome labels are used in this module.
"""
from __future__ import annotations
from math import log1p, isfinite
from .geo import haversine_km


def annotate_priority(forecast: list[list[float]], population: list[float],
                      places: list[dict] | None = None, limit: int = 8) -> list[dict]:
    """Rank forecast cells by GNN score * log(1+estimated residents in cell).

    This is a transparent, deliberately *uncalibrated* relative index; do not
    interpret it as the chance of fire reaching residents or a casualty count.
    A place name, when available, is a nearest-centroid label rather than
    evidence a municipal boundary lies inside the forecast cell.
    """
    if len(forecast) != len(population):
        raise ValueError('Each forecast cell must have one gridded population estimate')
    output=[]
    for index,(cell,pop) in enumerate(zip(forecast,population),1):
        lat,lon,score=map(float,cell[:3])
        count=max(0.,float(pop))
        if not (isfinite(score) and isfinite(count)):
            continue
        if count < 1:continue
        name=''
        if places:
            nearest=min(places,key=lambda p:haversine_km(lat,lon,p['latitude'],p['longitude']))
            if haversine_km(lat,lon,nearest['latitude'],nearest['longitude'])<=12:
                name=nearest['name']
        output.append({'forecast_rank':index,'latitude':round(lat,5),
                       'longitude':round(lon,5),'forecast_score':round(score,5),
                       'population_estimate':round(count),
                       'priority_index':round(max(0.,score)*log1p(count),5),
                       'nearest_place':name})
    return sorted(output,key=lambda r:(-r['priority_index'],r['forecast_rank']))[:limit]
