#!/usr/bin/env python3
"""Zero-third-party dependency HTTP server for s390x LinuxONE fallback.

The core engine uses Python standard library only. This runs real inference on
GET /api/infer, serves local static frontend files, and needs no native wheels.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wildfire.service import ApplicationService,ServerSettings  # noqa: E402

class FireHandler(SimpleHTTPRequestHandler):
    """Serve transparent live inference and a same-origin, no-CDN dashboard."""
    service:ApplicationService

    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT/'frontend'),**kwargs)

    def respond(self,obj:object,status:int=200)->None:
        """Serialize JSON with no-cache headers for live computations."""
        payload=json.dumps(obj,allow_nan=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)

    def do_GET(self)->None:
        """Route API requests or static web files with guarded parameter parsing."""
        path=urlsplit(self.path);args=parse_qs(path.query)
        try:
            if path.path=='/api/health':return self.respond(self.service.health())
            if path.path=='/api/observations':return self.respond(self.service.observations())
            if path.path=='/api/context':return self.respond(self.service.context())
            if path.path=='/api/infer':
                variant=args.get('variant',['fusion'])[0]
                cell=float(args.get('cell_m',[850])[0]);margin=float(args.get('margin_km',[9])[0])
                ensemble=args.get('ensemble',['true'])[0].lower() in ('true','1','yes')
                return self.respond(self.service.infer(variant,cell,margin,ensemble))
            if path.path=='/api/evidence':
                if self.service.last_output is None:return self.respond({'error':'Run /api/infer first'},404)
                return self.respond(self.service.last_output['evidence_graph'])
        except (ValueError,FileNotFoundError) as exc:
            return self.respond({'error':str(exc)},400)
        except Exception as exc:
            return self.respond({'error':type(exc).__name__+': '+str(exc)},500)
        if path.path=='/':self.path='/index.html'
        elif path.path.startswith('/static/'):
            self.path=path.path.removeprefix('/static')
        else:self.path=path.path
        return super().do_GET()


def main()->None:
    """Start multithreaded API server and print synthetic-data disclosure."""
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',required=True);p.add_argument('--weather');p.add_argument('--covariates')
    p.add_argument('--powerlines');p.add_argument('--lightning');p.add_argument('--perimeter');p.add_argument('--demo',action='store_true')
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000)
    args=p.parse_args()
    FireHandler.service=ApplicationService(ServerSettings(args.dataset,args.weather,args.covariates,
        args.powerlines,args.lightning,'SYNTHETIC DEMO — NOT REAL' if args.demo else 'historical_unverified',args.perimeter))
    print(f'Listening http://{args.host}:{args.port}; data={args.dataset}; mode={FireHandler.service.settings.mode}',flush=True)
    with ThreadingHTTPServer((args.host,args.port),FireHandler) as server:
        server.serve_forever()

if __name__=='__main__':main()
