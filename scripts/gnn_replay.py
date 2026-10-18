#!/usr/bin/env python3
"""Make a time-ordered GNN forecast replay for the EMBER browser dashboard.

Every forecast uses only current/prior observations. The next pass is written
separately so a presenter can REVEAL it after showing the forecast.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from gnn_forecast import (EdgeAwareGNN, average_precision, build_example, get_passes,
                          load_firms, load_weather, parse_utc, torch)


def main() -> None:
    """Load saved learned weights and export chronological non-leaking predictions."""
    p=argparse.ArgumentParser()
    p.add_argument('--checkpoint',default='artifacts/gnn/gnn_model.pt')
    p.add_argument('--firms',required=True)
    p.add_argument('--weather')
    p.add_argument('--name',default='historical_fire')
    p.add_argument('--output',default='frontend/gnn_replay.json')
    p.add_argument('--top',type=int,default=300)
    p.add_argument('--threads',type=int,default=2)
    args=p.parse_args()
    torch.set_num_threads(max(1,args.threads))
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    model=EdgeAwareGNN(checkpoint['hidden']);model.load_state_dict(checkpoint['state_dict']);model.eval()
    observations=load_firms(args.firms)
    passes=get_passes(observations)
    weather=load_weather(args.weather) if args.weather else []
    settings=checkpoint['grid']
    frames=[]
    with torch.no_grad():
        for i,obs in enumerate(passes[:-1]):
            graph=build_example(args.name,passes[max(0,i-2):i+1],None,weather,
                                cell_m=settings['cell_m'],margin_km=settings['margin_km'],
                                max_cells=settings['max_cells'])
            if graph is None:continue
            # Make this prediction before constructing any labels from the future.
            predicted_scores=torch.sigmoid(model(graph))
            probs=predicted_scores.cpu().tolist()
            top=sorted(range(len(probs)),key=probs.__getitem__,reverse=True)[:args.top]
            next_time=passes[i+1][0]['observed_utc']

            # Build labels AFTER predicting. This separate construction uses the
            # same past-only features, and the next pass solely for evaluation.
            labelled=build_example(args.name,passes[max(0,i-2):i+1],passes[i+1],weather,
                                   cell_m=settings['cell_m'],margin_km=settings['margin_km'],
                                   max_cells=settings['max_cells'])
            evaluation=None
            next_cells=[]
            if labelled is not None:
                labels=labelled.label.cpu().tolist()
                future_ids=[j for j,flag in enumerate(labels) if flag > 0.5]
                next_cells=[[round(graph.grid.nodes[j].lat,5),round(graph.grid.nodes[j].lon,5)]
                            for j in future_ids]
                # For every fixed-size forecast shortlist, compare cell IDs rather
                # than approximate geographic distances to later detections.
                top_k={}
                for k in (10,25,50):
                    shortlist=top[:min(k,len(top))]
                    hits=sum(labels[j] > 0.5 for j in shortlist)
                    top_k[str(k)]={'hits':hits, 'shown':len(shortlist),
                                   'precision':round(hits/max(1,len(shortlist)),4),
                                   'recall':round(hits/max(1,len(future_ids)),4)}
                evaluation={
                    'gnn_average_precision':round(average_precision(predicted_scores,labelled.label),4),
                    'persistence_average_precision':round(average_precision(labelled.current_mask,labelled.label),4),
                    'future_positive_cells':len(future_ids),
                    'future_pixel_coverage_in_grid':round(labelled.coverage,3),
                    'top_k':top_k
                }

            frames.append({'issue_time':graph.current_time,'pass_index':i,
                'next_observation_time':next_time,
                'horizon_hours':round((parse_utc(next_time)-parse_utc(graph.current_time)).total_seconds()/3600,2),
                'cell_m':settings['cell_m'],
                'grid_cell_count':len(probs),
                'observations':[[round(d['latitude'],5),round(d['longitude'],5)]
                                 for d in obs[::max(1,len(obs)//800)]],
                'forecast':[[round(graph.grid.nodes[j].lat,5),round(graph.grid.nodes[j].lon,5),round(probs[j],5)]
                            for j in top],
                'next_cells':next_cells,
                'evaluation':evaluation,
                # Retained for compatibility with older forecast viewers.
                'next_observations':[[round(d['latitude'],5),round(d['longitude'],5)]
                                     for d in passes[i+1][::max(1,len(passes[i+1])//800)]]})
    result={'case':args.name,'frames':frames,'test_fire':checkpoint['split']['test'],
        'trained_on':checkpoint['split']['training'],
        'warning':'Forecasts concern NEXT satellite detections, not fire perimeter or burned area. Model scores not calibrated. Later satellite detections are not exhaustive ground truth.'}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result))
    print(json.dumps({'saved':str(out),'frames':len(frames),'trained_on':result['trained_on'],
                      'test_fire':result['test_fire']},indent=2))

if __name__=='__main__':main()
