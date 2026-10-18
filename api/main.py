"""Optional FastAPI deployment for IBM LinuxONE / s390x Python 3.12.

Start: export FIRE_DATA=... ; uvicorn api.main:app --host 0.0.0.0 --port 8000
Alternative with zero third-party dependencies: scripts/serve_stdlib.py
"""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from wildfire.service import ApplicationService,ServerSettings

ROOT=Path(__file__).resolve().parents[1]

def path_env(name:str)->str|None:
    """Resolve operator-supplied relative input filenames against repo root."""
    value=os.environ.get(name)
    if not value:return None
    return str((ROOT/value).resolve()) if not Path(value).is_absolute() else value

app=FastAPI(title='Wildfire Forensics',version='0.1.0',
    description='Label-isolated historic wildfire origin reconstruction')
service=None

def get_service()->ApplicationService:
    """Load operator-selected data once; never load evaluation reference automatically."""
    global service
    if service is None:
        if not os.environ.get('FIRE_DATA'):
            raise HTTPException(503,'Set FIRE_DATA to a historic FIRMS CSV or synthetic fixture JSON')
        try:
            service=ApplicationService(ServerSettings(
                detections=path_env('FIRE_DATA'),weather=path_env('FIRE_WEATHER'),
                covariates=path_env('FIRE_COVARIATES'),powerlines=path_env('FIRE_POWERLINES'),
                lightning=path_env('FIRE_LIGHTNING'),mode=os.environ.get('FIRE_MODE','historical_unverified'),
                perimeter=path_env('FIRE_PERIMETER')))
        except Exception as exc:raise HTTPException(500,str(exc)) from exc
    return service

@app.get('/api/health')
def health():
    """Show LinuxONE/host execution and data-gate status."""
    return get_service().health()

@app.get('/api/observations')
def observations():
    """Send time-stamped satellites to the front end."""
    return get_service().observations()

@app.get('/api/context')
def context():
    """Display-only geographic infrastructure/incident layers."""
    return get_service().context()

@app.get('/api/infer')
def infer(variant:str='fusion',cell_m:float=850,margin_km:float=9,ensemble:bool=True):
    """Perform FRESH origin ranking each HTTP call (not static mock output)."""
    try:return get_service().infer(variant,cell_m,margin_km,ensemble)
    except (ValueError,FileNotFoundError) as exc:raise HTTPException(400,str(exc)) from exc

@app.get('/api/evidence')
def evidence():
    """Expose last computed hypothetical evidence relationships."""
    if get_service().last_output is None:raise HTTPException(404,'Run /api/infer first')
    return get_service().last_output['evidence_graph']

@app.get('/')
def index():
    """Deliver interactive site from same origin as inference API."""
    return FileResponse(ROOT/'frontend/index.html')

app.mount('/static',StaticFiles(directory=str(ROOT/'frontend')),name='static')
