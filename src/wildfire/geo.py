"""Small-area local metric projection and geographic geometry in stdlib only.

An equirectangular tangent approximation is used within ~100 km of a reference
latitude. It is NOT suitable for continental-scale distances; no reliance on
native geospatial wheels is needed on s390x.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_008.8

@dataclass(frozen=True)
class LocalProjection:
    """Project lon/lat to a local metric plane, with no external dependencies."""
    lat0: float
    lon0: float

    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        """Return easting/northing offsets in metres relative to reference point."""
        return (EARTH_RADIUS_M * math.radians(lon - self.lon0) * math.cos(math.radians(self.lat0)),
                EARTH_RADIUS_M * math.radians(lat - self.lat0))

    def latlon(self, x: float, y: float) -> tuple[float, float]:
        """Return latitude/longitude from relative metre coordinates."""
        return (self.lat0 + math.degrees(y / EARTH_RADIUS_M),
                self.lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(self.lat0)))))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in kilometres for evaluation and display."""
    a = math.sin(math.radians(lat2-lat1)/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*EARTH_RADIUS_M/1000 * math.asin(min(1, math.sqrt(a)))


def segment_distance_m(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Point-to-line-segment distance, used only for explanatory evidence links."""
    dx, dy = bx-ax, by-ay
    z = dx*dx + dy*dy
    t = max(0., min(1., ((px-ax)*dx+(py-ay)*dy)/z)) if z > 0 else 0.
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))
