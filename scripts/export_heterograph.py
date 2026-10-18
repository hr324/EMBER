#!/usr/bin/env python3
"""Generate typed CSV node and edge tables for an optional graph database.

Use on x86_64/ARM64 for TuringDB imports if desired. The propagation solver
remains natively executable on LinuxONE s390x via Python stdlib.
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from wildfire.cli import infer_from_files
from wildfire.heterograph import build_heterograph


def main():
    """Compute label-free inference then export a joined typed graph snapshot."""
    p=argparse.ArgumentParser()
    p.add_argument('--detections',required=True);p.add_argument('--weather')
    p.add_argument('--covariates');p.add_argument('--powerlines');p.add_argument('--lightning')
    p.add_argument('--top',type=int,default=80);p.add_argument('--output',default='artifacts/heterograph')
    args=p.parse_args()
    result,_,_=infer_from_files(args.detections,args.weather,covariates_path=args.covariates)
    graph=build_heterograph(result,covariates_csv=args.covariates,
         powerlines_path=args.powerlines,lightning_path=args.lightning,max_ranked=args.top)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    with open(out/'nodes.csv','w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['id','label','properties_json'])
        for n in graph['nodes']:w.writerow([n['id'],n['label'],json.dumps(n['properties'])])
    with open(out/'edges.csv','w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['source_id','target_id','relationship','properties_json'])
        for e in graph['edges']:w.writerow([e['source'],e['target'],e['relation'],json.dumps(e['properties'])])
    (out/'metadata.json').write_text(json.dumps(graph['metadata'],indent=2))
    print('Exported',len(graph['nodes']),'nodes and',len(graph['edges']),'directed edges, types:',graph['metadata']['typed_edges'])

if __name__=='__main__':main()
