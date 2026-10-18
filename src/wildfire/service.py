"""API-independent application service. Importable by FastAPI and stdlib server."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from .cli import read_detections,sha256
from .ingest import load_weather,observation_gate
from .inference import infer_origin,InferenceOptions,public_result
from .evidence import build_evidence_graph

@dataclass
class ServerSettings:
    """Server input paths must be passed by operator (no hidden test label)."""
    detections:str
    weather:str|None=None
    covariates:str|None=None
    powerlines:str|None=None
    lightning:str|None=None
    mode:str='historical_unverified'
    perimeter:str|None=None

class ApplicationService:
    """Load deterministic input snapshot and serve fresh inference on request."""
    def __init__(self,settings:ServerSettings):
        if not Path(settings.detections).exists():raise FileNotFoundError(settings.detections)
        self.settings=settings
        self.detections=read_detections(settings.detections)
        self.weather=load_weather(settings.weather) if settings.weather else None
        self.last_output=None

    def health(self)->dict:
        """Return execution platform and whether observation coverage passes gate."""
        import platform
        return {'status':'ready','python':platform.python_version(),'machine':platform.machine(),
            'data_mode':self.settings.mode,'gate':observation_gate(self.detections),
            'snapshot_sha256':sha256(self.settings.detections),
            'execution':'on this backend (no claimed hardware acceleration)'}

    def observations(self)->dict:
        """Return canonical hotspots to animate by acquisition timestamp."""
        return {'detections':self.detections,'data_mode':self.settings.mode}


    def context(self)->dict:
        """Return optional unmodified georeferenced background layers for display.

        These features do not enter inverse inference or candidate scoring.
        Whole-country GIS files should be pre-cropped by the operator.
        """
        def load_small_geojson(path):
            if not path:return None
            if Path(path).stat().st_size>6_000_000:
                raise ValueError('Context GeoJSON too large (>6 MB): clip to incident bounds')
            return json.loads(Path(path).read_text())
        lightning=[]
        if self.settings.lightning:
            import csv
            with open(self.settings.lightning,newline='',encoding='utf-8-sig') as f:
                for i,r in enumerate(csv.DictReader(f)):
                    if i>=2000:break
                    if all(k in r for k in ('latitude','longitude','timestamp_utc')):
                        lightning.append({'latitude':r['latitude'],'longitude':r['longitude'],
                                          'timestamp_utc':r['timestamp_utc']})
        return {'powerlines':load_small_geojson(self.settings.powerlines),
                'perimeter':load_small_geojson(self.settings.perimeter),
                'lightning':lightning,
                'caution':'Overlays are context, not training labels or verified causes'}

    def infer(self,variant:str='fusion',cell_m:float=850.,margin_km:float=9.,ensemble:bool=True)->dict:
        """Recompute propagation and rank candidates for live browser controls."""
        if cell_m<300 or cell_m>2500 or not 2<=margin_km<=20:
            raise ValueError('cell_m must be 300..2500 and margin_km must be 2..20')
        opts=InferenceOptions(cell_m=cell_m,margin_km=margin_km,ensemble=ensemble)
        result=infer_origin(self.detections,self.weather,opts,self.settings.covariates,variant)
        graph=build_evidence_graph(result,self.settings.powerlines,self.settings.lightning)
        payload={'inference':public_result(result),'evidence_graph':graph,
             'data_mode':self.settings.mode,
             'integrity':{'dataset_sha256':sha256(self.settings.detections),
                          'label_used_in_inference':False}}
        self.last_output=payload
        return payload
