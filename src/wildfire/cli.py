"""CLI tasks for reproducible inference, ablations and provenance."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from .ingest import load_firms,load_weather,normalize_detection_file,observation_gate
from .inference import infer_origin,public_result,InferenceOptions
from .evaluation import evaluate_result,ablation_study
from .evidence import build_evidence_graph


def read_detections(path:str)->list[dict]:
    """Accept preprocessed JSON or a standard raw NASA FIRMS CSV."""
    return json.loads(Path(path).read_text()) if path.endswith('.json') else load_firms(path)


def sha256(path:str)->str:
    """Fingerprint original data files for scenario reproducibility."""
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def infer_from_files(detections_path:str,weather_path:str|None=None,
                     *,covariates_path:str|None=None,variant:str='fusion',
                     options:InferenceOptions|None=None,electric_path:str|None=None,
                     lightning_path:str|None=None)->tuple[dict,dict,dict]:
    """Run label-free inference and optional secondary evidence linkages."""
    detections=read_detections(detections_path)
    weather=load_weather(weather_path) if weather_path else None
    result=infer_origin(detections,weather,options,covariates_path,variant)
    evidence=build_evidence_graph(result,electric_path,lightning_path)
    provenance={'run_timestamp_utc':datetime.now(timezone.utc).isoformat(),
      'files':[{ 'path':str(Path(path)), 'sha256':sha256(path)} for path in
        (detections_path,weather_path,covariates_path,electric_path,lightning_path) if path],
      'model':result['model'],'model_options':result['options'],
      'warning':'Evaluation labels were not loaded during model inference'}
    return result,evidence,provenance


def main(argv:list[str]|None=None)->int:
    """Run argparse-based ingest, data-gate, infer, and evaluate subcommands."""
    parser=argparse.ArgumentParser(description='Historical wildfire inverse reconstruction (Python 3.12)')
    sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('ingest');prep.add_argument('--firms',required=True);prep.add_argument('--case',required=True);prep.add_argument('--output',required=True)
    gate=sub.add_parser('gate');gate.add_argument('--detections',required=True)
    for command in ('infer','evaluate'):
        p=sub.add_parser(command)
        p.add_argument('--detections',required=True);p.add_argument('--weather')
        p.add_argument('--covariates');p.add_argument('--powerlines');p.add_argument('--lightning')
        p.add_argument('--output',default='artifacts/latest.json')
        p.add_argument('--variant',choices=['satellite','wind','fusion'],default='fusion')
        p.add_argument('--cell-m',type=float,default=850.)
        p.add_argument('--margin-km',type=float,default=9.)
        p.add_argument('--no-ensemble',action='store_true')
        if command=='evaluate':p.add_argument('--label',required=True)
    args=parser.parse_args(argv)
    if args.command=='ingest':
        print(json.dumps(normalize_detection_file(args.firms,args.output,json.loads(Path(args.case).read_text())),indent=2));return 0
    if args.command=='gate':print(json.dumps(observation_gate(read_detections(args.detections)),indent=2));return 0
    opts=InferenceOptions(cell_m=args.cell_m,margin_km=args.margin_km,ensemble=not args.no_ensemble)
    result,evidence,provenance=infer_from_files(args.detections,args.weather,
        covariates_path=args.covariates,variant=args.variant,options=opts,
        electric_path=args.powerlines,lightning_path=args.lightning)
    payload={'inference':public_result(result),'evidence_graph':evidence,'provenance':provenance}
    if args.command=='evaluate':
        payload['evaluation']=evaluate_result(result,args.label)
        payload['ablations']=ablation_study(read_detections(args.detections),
              load_weather(args.weather) if args.weather else None,args.label,
              args.covariates,opts)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2))
    print(json.dumps({'saved':str(out),'status':result['status'],
          'best_origin':result['best_origin'], 'warnings':result['warnings'],
          **({'evaluation':payload['evaluation']} if args.command=='evaluate' else {})},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
