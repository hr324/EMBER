"""NWS Red Flag Warnings (FW.W) and Fire Weather Watches (FW.A) as known at issue time.

Source: Iowa Environmental Mesonet (IEM) VTEC archive (free, no account).
* ``json/vtec_events_bywfo.py`` gives one row per (event, zone) with
  ``product_issued`` (when that zone was first put under the product),
  ``issue`` (valid start) and ``init_expired`` (expiry as first issued). Later
  extensions (``expire``) are NOT used, because they were unknown at issue time.
* ``geojson/vtec_event.py`` gives each zone's polygon as stored for that event.

Features for a Monday issue at 06:00 America/Los_Angeles (T):
  rfw_week_cov     max cell coverage of warnings published <= T whose valid period
                   overlaps [T, T+7d)
  fww_week_cov     the same for Fire Weather Watches
  rfw_past7_cov    sum over the 7 days before T of the max covered fraction under a warning

Usage: python3 -m forecasting.fetch_redflag
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import config
from .grid import Grid

WFOS = ['STO', 'EKA', 'REV', 'MFR', 'MTR']
PRODUCTS = {'W': 'red_flag_warning', 'A': 'fire_weather_watch'}
YEARS = range(2014, 2026)
IEM = 'https://mesonet.agron.iastate.edu'
UA = {'User-Agent': 'EMBER-datathon-research/0.1 (non-commercial; retrospective backtest)'}
PACIFIC = ZoneInfo('America/Los_Angeles')
CACHE = config.CACHE_DIR / 'redflag'


def _get(url: str, tries: int = 5) -> bytes:
    for k in range(tries):
        try:
            with urlopen(Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise
            time.sleep(5 * (k + 1))
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))
    raise RuntimeError(url)


def cached(name: str, url: str, refresh: bool = False) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if refresh or not p.exists():
        p.write_bytes(_get(url))
        time.sleep(0.7)
    return json.loads(p.read_bytes())


def events(years=YEARS, refresh_years=()) -> pd.DataFrame:
    """(event, zone) rows; ``refresh_years`` are re-downloaded (the current year is still changing)."""
    rows = []
    for wfo in WFOS:
        for y in years:
            for sig in PRODUCTS:
                d = cached(f'events_{wfo}_{y}_FW{sig}.json',
                           f'{IEM}/json/vtec_events_bywfo.py?wfo={wfo}&year={y}&phenomena=FW&significance={sig}',
                           refresh=y in refresh_years)
                for r in d.get('events', []):
                    rows.append(dict(wfo=wfo, year=y, sig=sig, eventid=r['eventid'], ugc=r['ugc'],
                                     product_issued=r['product_issued'], issue=r['issue'],
                                     init_expired=r['init_expired'], expire=r['expire']))
    df = pd.DataFrame(rows)
    for c in ('product_issued', 'issue', 'init_expired', 'expire'):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df.drop_duplicates(['wfo', 'year', 'sig', 'eventid', 'ugc'])


def zone_geometries(ev: pd.DataFrame) -> dict:
    """(ugc, year) -> list of polygons (rings), fetching the fewest event GeoJSONs per office-year."""
    geoms: dict = {}
    for (wfo, y, sig), g in ev.groupby(['wfo', 'year', 'sig']):
        need = set(g['ugc'])
        by_event = g.groupby('eventid')['ugc'].apply(set).sort_values(key=lambda s: -s.map(len))
        for eid, ugcs in by_event.items():
            missing = {u for u in ugcs if (u, y) not in geoms}
            if not missing & need:
                continue
            try:
                gj = cached(f'geom_{wfo}_{y}_FW{sig}_{eid}.json',
                            f'{IEM}/geojson/vtec_event.py?wfo={wfo}&year={y}&phenomena=FW&significance={sig}&etn={eid}')
            except HTTPError:
                continue
            for f in gj.get('features', []):
                geom = f.get('geometry') or {}
                polys = geom.get('coordinates', [])
                if geom.get('type') == 'Polygon':
                    polys = [polys]
                geoms.setdefault((f['id'], y), [p[0] for p in polys if p])
            need -= {u for u in need if (u, y) in geoms}
            if not need:
                break
    return geoms


def _inside(x: float, y: float, ring: list) -> bool:
    inside, n = False, len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def coverage(geoms: dict) -> dict:
    """(ugc, year) -> {cell_id: fraction of 6x6 sample points inside the zone}."""
    from .grid import from_albers
    g = Grid()
    samples = {c.cell_id: [from_albers(c.x_min + (i + .5) * c.size / 6, c.y_min + (j + .5) * c.size / 6)
                           for i in range(6) for j in range(6)] for c in g.cells}
    out = {}
    for key, rings in geoms.items():
        xs = [p[0] for r in rings for p in r]
        ys = [p[1] for r in rings for p in r]
        bb = (min(xs), max(xs), min(ys), max(ys))
        cov = {}
        for cid, pts in samples.items():
            k = sum(1 for la, lo in pts if bb[0] <= lo <= bb[1] and bb[2] <= la <= bb[3]
                    and any(_inside(lo, la, r) for r in rings))
            if k:
                cov[cid] = k / len(pts)
        out[key] = cov
    return out


def issue_instant(d) -> pd.Timestamp:
    return pd.Timestamp(datetime(d.year, d.month, d.day, 6, 0, tzinfo=PACIFIC)).tz_convert('UTC')


def build_features(issue_dates: list, ev: pd.DataFrame, cov: dict) -> pd.DataFrame:
    cells = [c.cell_id for c in Grid().cells]
    ev = ev.copy()
    ev['start'] = ev['issue'].fillna(ev['product_issued'])
    ev['end'] = ev['init_expired'].fillna(ev['expire'])
    ev['cov'] = [cov.get((u, y), {}) for u, y in zip(ev['ugc'], ev['year'])]
    ev = ev[ev['cov'].map(len) > 0]
    rows = []
    for d in issue_dates:
        T = issue_instant(d)
        known = ev[ev['product_issued'] <= T]
        week = known[(known['start'] < T + pd.Timedelta(days=7)) & (known['end'] > T)]
        rec = {c: dict(rfw_week_cov=0.0, fww_week_cov=0.0, rfw_past7_cov=0.0) for c in cells}
        for r in week.itertuples():
            col = 'rfw_week_cov' if r.sig == 'W' else 'fww_week_cov'
            for c, f in r.cov.items():
                rec[c][col] = max(rec[c][col], f)
        past = known[(known['sig'] == 'W') & (known['start'] < T) & (known['end'] > T - pd.Timedelta(days=7))]
        for k in range(7):
            a, b = T - pd.Timedelta(days=7 - k), T - pd.Timedelta(days=6 - k)
            day = past[(past['start'] < b) & (past['end'] > a)]
            best = {}
            for r in day.itertuples():
                for c, f in r.cov.items():
                    best[c] = max(best.get(c, 0.0), f)
            for c, f in best.items():
                rec[c]['rfw_past7_cov'] += f
        for c in cells:
            rows.append(dict(cell_id=c, forecast_date=pd.Timestamp(d), redflag_known_at=T.isoformat(), **rec[c]))
    return pd.DataFrame(rows)


def main() -> None:
    ev = events()
    print(f'{len(ev)} (event, zone) rows; products: {ev.groupby("sig").size().to_dict()}', flush=True)
    geoms = zone_geometries(ev)
    print(f'{len(geoms)} zone-year geometries', flush=True)
    cov = coverage(geoms)
    touching = {k for k, v in cov.items() if v}
    ev['touches_lattice'] = [(u, y) in touching for u, y in zip(ev['ugc'], ev['year'])]
    d, issues = date_range()
    feats = build_features(issues, ev, cov)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    feats.to_csv(config.PROCESSED_DIR / 'redflag_features.csv', index=False)
    summary = dict(source=IEM, wfos=WFOS, years=[min(YEARS), max(YEARS)], rows=int(len(ev)),
                   rows_touching_lattice=int(ev['touches_lattice'].sum()),
                   by_wfo_touching={k: int(v) for k, v in ev[ev['touches_lattice']].groupby('wfo').size().items()},
                   zone_year_geometries=len(geoms), zones_touching=sorted({u for u, _ in touching}),
                   issue_rule='product_issued <= Monday 06:00 America/Los_Angeles; valid window issue..init_expired',
                   share_cellweeks_rfw_week=round(float((feats['rfw_week_cov'] > 0).mean()), 4),
                   share_cellweeks_fww_week=round(float((feats['fww_week_cov'] > 0).mean()), 4),
                   share_cellweeks_rfw_past7=round(float((feats['rfw_past7_cov'] > 0).mean()), 4),
                   built_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    (config.PROCESSED_DIR / 'redflag_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def date_range():
    first, last = config.FIRST_ISSUE, pd.Timestamp('2025-12-22').date()
    out, d = [], first
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return None, out


if __name__ == '__main__':
    main()
