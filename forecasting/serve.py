"""Read-only forecast API + map, standard library only (runs on s390x without wheels).

GET /api/forecast?date=YYYY-MM-DD[&model=NAME]   precomputed holdout scores for one issue date
GET /api/forecast/dates                          available issue dates and model names
GET /api/forecast/health                         host architecture and artefact status
GET /forecast                                    standalone before/after map

No model is trained or run per request; scores come from
``forecasting/outputs/holdout_predictions.csv``. Observed outcomes are
returned only when ``reveal=1`` is passed, mirroring the map's reveal step.

Usage: python3 -m forecasting.serve [--port 8010]
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config


def load(path=None):
    by = defaultdict(lambda: defaultdict(list))
    with open(path or config.OUTPUT_DIR / 'holdout_predictions.csv', newline='') as fh:
        for r in csv.DictReader(fh):
            by[r['forecast_date']][r['model_name']].append(r)
    return by


class Handler(BaseHTTPRequestHandler):
    data = None

    def send(self, obj, code=200, ctype='application/json'):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == '/forecast':
            return self.send((config.OUTPUT_DIR / 'forecast_map.html').read_bytes(), ctype='text/html; charset=utf-8')
        if u.path == '/api/forecast/health':
            return self.send(dict(machine=platform.machine(), python=platform.python_version(),
                                  issue_dates=len(self.data), source='precomputed holdout_predictions.csv'))
        if u.path == '/api/forecast/dates':
            models = sorted({m for d in self.data.values() for m in d})
            return self.send(dict(dates=sorted(self.data), models=models))
        if u.path == '/api/forecast':
            d = q.get('date')
            if d not in self.data:
                return self.send(dict(error='unknown date; see /api/forecast/dates'), 404)
            models = self.data[d]
            name = q.get('model') or sorted(models)[0]
            if name not in models:
                return self.send(dict(error=f'unknown model; choose from {sorted(models)}'), 404)
            reveal = q.get('reveal') == '1'
            cells = []
            for r in sorted(models[name], key=lambda r: -float(r['risk_score'])):
                c = dict(cell_id=r['cell_id'], centroid_lat=float(r['centroid_lat']),
                         centroid_lon=float(r['centroid_lon']), risk_score=float(r['risk_score']))
                if reveal:
                    c.update(observed_fire=int(r['observed_fire']), event_count=int(r['event_count']))
                cells.append(c)
            return self.send(dict(forecast_date=d, horizon_days=int(models[name][0]['horizon_days']),
                                  model_name=name, model_version=models[name][0]['model_version'],
                                  score_type='relative risk score (not a calibrated probability)',
                                  outcomes_included=reveal, cells=cells))
        self.send(dict(error='not found'), 404)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8010)
    a = ap.parse_args()
    Handler.data = load()
    print(f'serving http://{a.host}:{a.port}/forecast  ({len(Handler.data)} issue dates)')
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
