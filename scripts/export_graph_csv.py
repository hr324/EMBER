#!/usr/bin/env python3
"""Export a simple evidence-property-graph interchange format.

TuringDB is OPTIONAL: install/run on x86_64/ARM64 if it is appropriate, not
on the critical path of s390x inverse inference. These generic CSVs contain
node/edge IDs and JSON properties for adaptation to your graph DB's importer.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path


def main()->None:
    """Write nodes/edges CSV from a completed infer/evaluate JSON artifact."""
    p=argparse.ArgumentParser()
    p.add_argument('--result',required=True);p.add_argument('--outdir',default='artifacts/graph_export')
    a=p.parse_args()
    graph=json.loads(Path(a.result).read_text())['evidence_graph'];out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    with open(out/'nodes.csv','w',newline='') as f:
        w=csv.writer(f);w.writerow(['id','label','properties_json'])
        for n in graph['nodes']:
            w.writerow([n['id'],n['kind'].upper(),json.dumps({k:v for k,v in n.items() if k not in ('id','kind')})])
    with open(out/'edges.csv','w',newline='') as f:
        w=csv.writer(f);w.writerow(['source_id','target_id','relationship','properties_json'])
        for e in graph['edges']:
            w.writerow([e['source'],e['target'],e['type'],json.dumps({k:v for k,v in e.items() if k not in ('source','target','type')})])
    print('Exported',len(graph['nodes']),'nodes /',len(graph['edges']),'edges to',out)

if __name__=='__main__':main()
