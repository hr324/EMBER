"""EPSG:3310 (NAD83 / California Albers) projection and the square cell lattice.

Pure-Python Albers equal-area conic on the GRS80 ellipsoid (Snyder 1987,
eqs. 3-12 to 3-16, 14-1 to 14-21) so the grid runs without native wheels on
s390x. EPSG:3310 parameters: lat_1=34, lat_2=40.5, lat_0=0, lon_0=-120,
x_0=0, y_0=-4,000,000. NAD83 vs WGS84 datum difference (~1 m) is ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import config

A = 6_378_137.0
F = 1 / 298.257222101
E2 = 2 * F - F * F
E = math.sqrt(E2)
LAT1, LAT2, LAT0, LON0 = map(math.radians, (34.0, 40.5, 0.0, -120.0))
X0, Y0 = 0.0, -4_000_000.0


def _q(phi: float) -> float:
    s = math.sin(phi)
    return (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * math.log((1 - E * s) / (1 + E * s)))


def _m(phi: float) -> float:
    s = math.sin(phi)
    return math.cos(phi) / math.sqrt(1 - E2 * s * s)


_M1, _M2 = _m(LAT1), _m(LAT2)
_Q0, _Q1, _Q2 = _q(LAT0), _q(LAT1), _q(LAT2)
N = (_M1 ** 2 - _M2 ** 2) / (_Q2 - _Q1)
C = _M1 ** 2 + N * _Q1
RHO0 = A * math.sqrt(C - N * _Q0) / N


def to_albers(lat: float, lon: float) -> tuple[float, float]:
    """Project geographic degrees to EPSG:3310 metres (x, y)."""
    rho = A * math.sqrt(C - N * _q(math.radians(lat))) / N
    theta = N * (math.radians(lon) - LON0)
    return X0 + rho * math.sin(theta), Y0 + RHO0 - rho * math.cos(theta)


def from_albers(x: float, y: float) -> tuple[float, float]:
    """Inverse projection: EPSG:3310 metres to (lat, lon) degrees."""
    dx, dy = x - X0, RHO0 - (y - Y0)
    rho = math.hypot(dx, dy)
    theta = math.atan2(dx, dy)
    q = (C - (rho * N / A) ** 2) / N
    phi = math.asin(q / 2)
    for _ in range(15):
        s = math.sin(phi)
        step = ((1 - E2 * s * s) ** 2 / (2 * math.cos(phi))) * (
            q / (1 - E2) - s / (1 - E2 * s * s) + (1 / (2 * E)) * math.log((1 - E * s) / (1 + E * s)))
        phi += step
        if abs(step) < 1e-12:
            break
    return math.degrees(phi), math.degrees(LON0 + theta / N)


@dataclass(frozen=True)
class Cell:
    cell_id: str
    col: int
    row: int
    x_min: float
    y_min: float
    size: float

    @property
    def centroid_xy(self) -> tuple[float, float]:
        return self.x_min + self.size / 2, self.y_min + self.size / 2

    @property
    def centroid_latlon(self) -> tuple[float, float]:
        return from_albers(*self.centroid_xy)

    def polygon_lonlat(self, densify: int = 4) -> list[list[float]]:
        """Closed exterior ring in GeoJSON [lon, lat] order, edges densified."""
        s, x, y = self.size, self.x_min, self.y_min
        corners = [(x, y), (x + s, y), (x + s, y + s), (x, y + s), (x, y)]
        ring = []
        for (ax, ay), (bx, by) in zip(corners, corners[1:]):
            for k in range(densify):
                t = k / densify
                lat, lon = from_albers(ax + t * (bx - ax), ay + t * (by - ay))
                ring.append([round(lon, 6), round(lat, 6)])
        ring.append(ring[0])
        return ring


class Grid:
    """Square cells aligned to multiples of ``size`` in EPSG:3310 covering ``bbox``."""

    def __init__(self, bbox: dict | None = None, size: float = config.CELL_SIZE_M):
        bbox = bbox or config.BBOX
        self.size = size
        # Project a densified bbox boundary; Albers edges of a lat/lon box are curved.
        pts = []
        for i in range(21):
            t = i / 20
            lat = bbox['lat_min'] + t * (bbox['lat_max'] - bbox['lat_min'])
            lon = bbox['lon_min'] + t * (bbox['lon_max'] - bbox['lon_min'])
            pts += [to_albers(lat, bbox['lon_min']), to_albers(lat, bbox['lon_max']),
                    to_albers(bbox['lat_min'], lon), to_albers(bbox['lat_max'], lon)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.x0 = math.floor(min(xs) / size) * size
        self.y0 = math.floor(min(ys) / size) * size
        self.ncols = math.ceil((max(xs) - self.x0) / size)
        self.nrows = math.ceil((max(ys) - self.y0) / size)
        self.cells = [Cell(f'c{r:02d}_{c:02d}', c, r, self.x0 + c * size, self.y0 + r * size, size)
                      for r in range(self.nrows) for c in range(self.ncols)]
        self.by_id = {c.cell_id: c for c in self.cells}

    def cell_of(self, lat: float, lon: float) -> str | None:
        """Return the id of the cell containing a point, or None outside the lattice."""
        x, y = to_albers(lat, lon)
        c = math.floor((x - self.x0) / self.size)
        r = math.floor((y - self.y0) / self.size)
        if 0 <= c < self.ncols and 0 <= r < self.nrows:
            return f'c{r:02d}_{c:02d}'
        return None

    def latlon_bounds(self, pad_deg: float = 0.05) -> dict:
        """Geographic envelope of the whole lattice, for server-side source queries."""
        corners = [from_albers(self.x0 + i * self.ncols * self.size, self.y0 + j * self.nrows * self.size)
                   for i in (0, 1) for j in (0, 1)]
        edges = [from_albers(self.x0 + self.ncols * self.size / 2, self.y0 + j * self.nrows * self.size)
                 for j in (0, 1)]
        lats = [p[0] for p in corners + edges]
        lons = [p[1] for p in corners + edges]
        return dict(lat_min=min(lats) - pad_deg, lat_max=max(lats) + pad_deg,
                    lon_min=min(lons) - pad_deg, lon_max=max(lons) + pad_deg)

    def neighbours(self, cell_id: str) -> list[str]:
        """Up to eight adjacent cells (queen contiguity)."""
        cell = self.by_id[cell_id]
        out = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr or dc) and 0 <= cell.row + dr < self.nrows and 0 <= cell.col + dc < self.ncols:
                    out.append(f'c{cell.row + dr:02d}_{cell.col + dc:02d}')
        return out
