#!/usr/bin/env python3
"""EMBER forecasting: train an edge-aware GNN to predict next-pass FIRMS detections.

Real labels are FUTURE FIRMS pixels, not burned area. A non-detection is not
proof that a cell was unburned. Never split snapshots of one fire across train
and test. No official ignition coordinates are consumed by this module.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
import heapq
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
try:
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError as e:
    raise SystemExit('Install a supported CPU PyTorch build first: python3 -m pip install torch') from e

from wildfire.ingest import load_firms, load_weather, parse_utc
from wildfire.geo import LocalProjection
from wildfire.graph import build_grid, build_adjacency, SpreadParameters
from wildfire.features import weather_summary

FEATURE_COUNT = 8
EDGE_FEATURE_COUNT = 4


@dataclass
class GraphExample:
    """A single strictly chronological (input pass, later target pass) example."""
    name: str
    current_time: str
    future_time: str | None
    grid: object
    x: torch.Tensor
    src: torch.Tensor
    dst: torch.Tensor
    edge_features: torch.Tensor
    label: torch.Tensor | None
    current_mask: torch.Tensor
    coverage: float
    horizon_hours: float | None


def get_passes(observations: list[dict], gap_minutes: int = 30) -> list[list[dict]]:
    """Group temporally adjacent FIRMS pixels into approximate overpasses."""
    rows = sorted(observations, key=lambda d: d['observed_utc'])
    passes: list[list[dict]] = []
    for row in rows:
        if not passes or (parse_utc(row['observed_utc']) -
                          parse_utc(passes[-1][-1]['observed_utc'])).total_seconds() > gap_minutes * 60:
            passes.append([])
        passes[-1].append(row)
    return passes


def nearby_weather(weather: list[dict], time: str) -> dict | None:
    """Use weather available no later than the forecast issue time."""
    instant = parse_utc(time)
    recent = [w for w in weather if instant - timedelta(hours=8) <= parse_utc(w['timestamp_utc']) <= instant]
    if not recent:
        return None
    return weather_summary(recent, recent[0]['timestamp_utc'], recent[-1]['timestamp_utc'])


def cell_masks(grid, rows: list[dict]) -> tuple[list[float], list[float], list[float]]:
    """Aggregate present detections, count and FRP to grid cells."""
    n = len(grid.nodes)
    seen, count, intensity = [0.0]*n, [0.0]*n, [0.0]*n
    for row in rows:
        index = grid.nearest(row['latitude'], row['longitude'])
        seen[index] = 1.0
        count[index] += 1.0
        intensity[index] += float(row.get('frp', 0.0))
    return seen, count, intensity


def nearest_detection_distance(grid, mask: list[float]) -> list[float]:
    """Shortest undirected grid distance to a currently detected cell."""
    result = [math.inf] * len(mask)
    queue = []
    for i, value in enumerate(mask):
        if value > 0:
            result[i] = 0.0
            heapq.heappush(queue, (0.0, i))
    while queue:
        distance, index = heapq.heappop(queue)
        if distance > result[index]:
            continue
        row, col = divmod(index, grid.nx)
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                if di == dj == 0 or not 0 <= row+dj < grid.ny or not 0 <= col+di < grid.nx:
                    continue
                other = (row+dj)*grid.nx + col+di
                candidate = distance + grid.cell_m*math.hypot(di, dj)
                if candidate < result[other]:
                    result[other] = candidate
                    heapq.heappush(queue, (candidate, other))
    return result


def build_example(name: str, past: list[list[dict]], next_pass: list[dict] | None,
                  weather: list[dict], *, cell_m: float, margin_km: float,
                  max_cells: int) -> GraphExample | None:
    """Build features from strictly PAST observations, using future detections only as labels."""
    current = past[-1]
    time = min(row['observed_utc'] for row in current)
    # This bounding region comes from current observations only, NEVER the next pass.
    # Using all current points ensures that a distant observed fire front is included.
    guide = [{'latitude': r['latitude'], 'longitude': r['longitude']} for r in current]
    try:
        grid = build_grid(guide, cell_m=cell_m, margin_km=margin_km, max_cells=max_cells)
    except ValueError:
        return None
    past_rows = [row for group in past for row in group]
    latest, pixel_counts, frps = cell_masks(grid, current)
    cumulative, _, _ = cell_masks(grid, past_rows)
    dist = nearest_detection_distance(grid, latest)
    local_weather = nearby_weather(weather, time)
    # This uses fixed, declared physical edge weights as FEATURES, not trained parameters.
    adjacency, _ = build_adjacency(grid, local_weather, SpreadParameters())
    east = local_weather['wind_east_mps'] if local_weather else 0.0
    north = local_weather['wind_north_mps'] if local_weather else 0.0
    xs, ys = [], []
    active_x = sum(node.x for node in grid.nodes if latest[node.index]) / max(1, sum(latest))
    active_y = sum(node.y for node in grid.nodes if latest[node.index]) / max(1, sum(latest))
    for node in grid.nodes:
        i = node.index
        xs.append([latest[i], cumulative[i],
                   math.log1p(frps[i])/8, math.log1p(pixel_counts[i])/4,
                   min(dist[i]/30000, 3),
                   max(-3, min(3, (node.x-active_x)/30000)),
                   max(-3, min(3, (node.y-active_y)/30000)),
                   min(math.hypot(east, north)/15, 2)])
    src, dst, edge_features = [], [], []
    for i, neighbourhood in enumerate(adjacency):
        source = grid.nodes[i]
        for j, hours in neighbourhood:
            target = grid.nodes[j]
            dx, dy = target.x-source.x, target.y-source.y
            unit = math.hypot(dx, dy)
            alignment = (dx*east + dy*north)/(unit*math.hypot(east, north)) if math.hypot(east,north)>0 else 0.0
            src.append(i); dst.append(j)
            edge_features.append([math.log1p(hours), dx/unit, dy/unit, alignment])
    labels = None
    coverage = 1.0
    horizon_hours = None
    future_time = None
    if next_pass is not None:
        future_time = min(r['observed_utc'] for r in next_pass)
        horizon_hours = (parse_utc(future_time)-parse_utc(time)).total_seconds()/3600
        # Don't clamp out-of-bounds future labels onto border cells.
        positive = set()
        inside = 0
        for r in next_pass:
            x, y = grid.projection.xy(r['latitude'], r['longitude'])
            if grid.minx-grid.cell_m/2 <= x <= grid.minx+(grid.nx-.5)*grid.cell_m and \
               grid.miny-grid.cell_m/2 <= y <= grid.miny+(grid.ny-.5)*grid.cell_m:
                inside += 1
                positive.add(grid.nearest(r['latitude'], r['longitude']))
        coverage = inside / len(next_pass) if next_pass else 0.0
        if not positive:
            return None
        labels = torch.zeros(len(xs), dtype=torch.float32)
        labels[list(positive)] = 1.0
    return GraphExample(name, time, future_time, grid,
                        torch.tensor(xs, dtype=torch.float32),
                        torch.tensor(src, dtype=torch.long), torch.tensor(dst, dtype=torch.long),
                        torch.tensor(edge_features, dtype=torch.float32), labels,
                        torch.tensor(latest, dtype=torch.float32), coverage, horizon_hours)


class EdgeAwareGNN(nn.Module):
    """Two-layer directed message-passing GNN with LEARNED edge gates.

    Each neighbour sends a learned message whose importance depends on the
    source hidden state and the physics-derived edge attributes. This is a
    proper trainable GNN rather than a shortest-path optimizer.
    """
    def __init__(self, hidden: int = 32):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(FEATURE_COUNT, hidden), nn.ReLU())
        self.messages = nn.ModuleList([
            nn.Sequential(nn.Linear(hidden+EDGE_FEATURE_COUNT, hidden), nn.ReLU(),
                          nn.Linear(hidden, hidden)) for _ in range(2)
        ])
        self.gates = nn.ModuleList([
            nn.Sequential(nn.Linear(EDGE_FEATURE_COUNT, hidden), nn.ReLU(),
                          nn.Linear(hidden, 1), nn.Sigmoid()) for _ in range(2)
        ])
        self.updates = nn.ModuleList([
            nn.Sequential(nn.Linear(2*hidden, hidden), nn.ReLU(), nn.LayerNorm(hidden))
            for _ in range(2)
        ])
        self.classifier = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(),
                                        nn.Linear(hidden, 1))

    def forward(self, example: GraphExample) -> torch.Tensor:
        """Send directed trainable messages, then predict next-pass activity per node."""
        h = self.encoder(example.x)
        for message_net, gate_net, update_net in zip(self.messages, self.gates, self.updates):
            msg = message_net(torch.cat([h[example.src], example.edge_features], dim=1))
            msg = msg * gate_net(example.edge_features)
            aggregated = torch.zeros_like(h)
            aggregated.index_add_(0, example.dst, msg)
            counts = torch.zeros((h.shape[0], 1), dtype=h.dtype)
            counts.index_add_(0, example.dst, torch.ones((example.dst.shape[0],1)))
            aggregated = aggregated / counts.clamp(min=1)
            h = h + update_net(torch.cat([h, aggregated], dim=1))
        return self.classifier(h).squeeze(-1)


def average_precision(scores: torch.Tensor, labels: torch.Tensor) -> float:
    """Tie-aware AP for later FIRMS-detected cells, avoiding arbitrary tie order."""
    score=scores.detach().cpu().float()
    truth=labels.detach().cpu().float()
    order=torch.argsort(score,descending=True)
    score,truth=score[order],truth[order]
    n_positive=max(1.,truth.sum().item())
    # Average precision is integrated over score thresholds, so all equal
    # scores are treated as one threshold (important for binary persistence).
    changes=torch.nonzero(score[1:] != score[:-1]).flatten()+1
    ends=torch.cat((changes,torch.tensor([len(score)]))).tolist()
    true_so_far=torch.cumsum(truth,0)
    prev_recall=0.
    ap=0.
    for end in ends:
        tp=float(true_so_far[end-1].item())
        recall=tp/n_positive
        ap+=(recall-prev_recall)*(tp/end)
        prev_recall=recall
    return ap


def evaluate(model: nn.Module, examples: list[GraphExample]) -> list[dict]:
    """Compare trained predictions and a persistence baseline on unseen fires."""
    model.eval()
    output = []
    with torch.no_grad():
        for ex in examples:
            scores = model(ex)
            output.append({'fire': ex.name, 'issued_at': ex.current_time,
                           'observed_at': ex.future_time,
                           'lead_hours': round(ex.horizon_hours or 0,2),
                           'future_pixel_coverage_in_grid': round(ex.coverage,3),
                           'future_positive_cells': int(ex.label.sum().item()),
                           'gnn_average_precision': round(average_precision(scores,ex.label),4),
                           'persistence_average_precision': round(average_precision(ex.current_mask,ex.label),4)})
    return output


def load_examples(data_dir: Path, *, cell_m: float, margin_km: float,
                  max_cells: int, max_hours: float) -> tuple[dict[str,list[GraphExample]],dict]:
    """Load grouped sequences and report rejected snapshots and missing weather."""
    cases={}; stats={}
    for path in sorted(data_dir.glob('*/firms.csv')):
        name=path.parent.name
        try:
            observations=load_firms(path)
            weather_path=path.parent/'weather.json'
            weather=load_weather(weather_path) if weather_path.exists() else []
            passes=get_passes(observations)
            examples=[]
            for i in range(len(passes)-1):
                start=min(r['observed_utc'] for r in passes[i])
                end=min(r['observed_utc'] for r in passes[i+1])
                gap=(parse_utc(end)-parse_utc(start)).total_seconds()/3600
                if not (0.2 <= gap <= max_hours):
                    continue
                example=build_example(name,passes[max(0,i-2):i+1],passes[i+1],weather,
                                      cell_m=cell_m,margin_km=margin_km,max_cells=max_cells)
                if example is not None and example.coverage>=0.7:
                    examples.append(example)
            cases[name]=examples
            stats[name]={'passes':len(passes),'pairs_accepted':len(examples),
                         'detections':len(observations),'weather':bool(weather)}
        except Exception as exc:
            stats[name]={'error':f'{type(exc).__name__}: {exc}'}
    return cases,stats


def balanced_loss(logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Weight observed positive cells against unlabeled cells; negatives remain uncertain."""
    positive=labels.sum().clamp(min=1)
    negative=(len(labels)-positive).clamp(min=1)
    pos_weight=(negative/positive).clamp(min=1,max=35)
    return F.binary_cross_entropy_with_logits(logits,labels,pos_weight=pos_weight)


def train(args) -> None:
    """Train on whole fires, checkpoint by validation loss, evaluate on held-out fires."""
    torch.manual_seed(args.seed);random.seed(args.seed)
    torch.set_num_threads(max(1,args.threads))
    cases, stats=load_examples(Path(args.data),cell_m=args.cell_m,
                              margin_km=args.margin_km,max_cells=args.max_cells,
                              max_hours=args.max_hours)
    usable=[name for name,items in cases.items() if items]
    report={'dataset':stats,'fire_count':len(usable),'method':'edge-aware message passing GNN',
            'evaluation_caution':'Later FIRMS detections are partial observations, NOT complete burn area.'}
    if len(usable)<3:
        print(json.dumps(report,indent=2))
        raise SystemExit('Need at least THREE usable fires for train/validation/held-out test. Acquire more incidents; no invented evaluation.')
    # Reproducible whole-fire split. User may force named incident held out.
    if args.test_fire:
        if args.test_fire not in usable:raise SystemExit(f'Test fire {args.test_fire!r} has no accepted examples')
        heldout=args.test_fire
        rest=sorted(n for n in usable if n!=heldout)
    else:
        heldout=sorted(usable)[-1]
        rest=sorted(n for n in usable if n!=heldout)
    validation=rest[-1]
    training=rest[:-1]
    train_data=[ex for f in training for ex in cases[f]]
    val_data=cases[validation]
    test_data=cases[heldout]
    report['split']={'training':training,'validation':validation,'test':[heldout]}
    model=EdgeAwareGNN(args.hidden)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=1e-4)
    best_loss=math.inf
    best_state=None
    patience=0
    log=[]
    for epoch in range(args.epochs):
        model.train()
        random.shuffle(train_data)
        losses=[]
        for ex in train_data:
            optimizer.zero_grad(set_to_none=True)
            logits=model(ex)
            loss=balanced_loss(logits, ex.label)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),5.0)
            optimizer.step()
            losses.append(loss.item())
        model.eval()
        with torch.no_grad():
            val_loss=sum(balanced_loss(model(ex),ex.label).item()
                         for ex in val_data)/len(val_data)
        entry={'epoch':epoch+1,'train_loss':round(sum(losses)/len(losses),5),
               'val_loss':round(val_loss,5)}
        log.append(entry)
        print(json.dumps(entry),flush=True)
        if val_loss<best_loss-1e-5:
            best_loss=val_loss
            best_state={name:tensor.detach().clone() for name,tensor in model.state_dict().items()}
            patience=0
        else:
            patience+=1
            if patience>=args.patience:break
    model.load_state_dict(best_state)
    test_scores=evaluate(model,test_data)
    report['history']=log
    report['test_predictions']=test_scores
    report['training_note']='No test-fire labels used for training or early stopping.'
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    torch.save({'state_dict':best_state,'hidden':args.hidden,
                'grid':{'cell_m':args.cell_m,'margin_km':args.margin_km,'max_cells':args.max_cells},
                'split':report['split']},out/'gnn_model.pt')
    (out/'gnn_report.json').write_text(json.dumps(report,indent=2))
    print('SAVED',out/'gnn_model.pt',out/'gnn_report.json',flush=True)
    print('HELD-OUT RESULTS',json.dumps(test_scores,indent=2),flush=True)


def predict(args) -> None:
    """Predict next detected-active cells using only observations through issue pass."""
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    model=EdgeAwareGNN(checkpoint['hidden'])
    model.load_state_dict(checkpoint['state_dict'])
    model.eval();torch.set_num_threads(max(1,args.threads))
    observations=load_firms(args.firms)
    passes=get_passes(observations)
    index=args.pass_index if args.pass_index>=0 else len(passes)-1
    if not 0<=index<len(passes):raise SystemExit(f'Pass index must be 0..{len(passes)-1}')
    weather=load_weather(args.weather) if args.weather else []
    settings=checkpoint['grid']
    example=build_example(args.fire_name,passes[max(0,index-2):index+1],None,weather,
                          cell_m=settings['cell_m'],margin_km=settings['margin_km'],
                          max_cells=settings['max_cells'])
    if example is None:raise SystemExit('Selected pass exceeds graph-size limit')
    with torch.no_grad():
        probability=torch.sigmoid(model(example)).cpu().tolist()
    # Save a compact map layer; probabilities are uncalibrated ranking scores.
    top=sorted(range(len(probability)),key=probability.__getitem__,reverse=True)[:args.top]
    features=[]
    for rank,index in enumerate(top,1):
        node=example.grid.nodes[index]
        features.append({'type':'Feature',
            'geometry':{'type':'Point','coordinates':[node.lon,node.lat]},
            'properties':{'rank':rank,'score':round(probability[index],6),
                          'current_detection':bool(example.current_mask[index]),
                          'cell_m':settings['cell_m']}})
    output={'type':'FeatureCollection','features':features,
            'metadata':{'fire':args.fire_name,'issue_time_utc':example.current_time,
                'prediction_target':'next FIRMS-observed active cell',
                'score_warning':'Uncalibrated scores. Non-detection is not evidence of no fire.',
                'trained_on':checkpoint['split']['training'],
                'held_out_test':checkpoint['split']['test'],
                'passes_available':len(passes)}}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(output))
    print(json.dumps({'saved':str(out),'issue_time_utc':example.current_time,
           'grid_cells':len(probability),'top_cells':len(top)},indent=2))


def main() -> None:
    """Provide explicit train and historical-replay forecast commands."""
    parser=argparse.ArgumentParser(description='Train an edge-aware GNN to predict next FIRMS observations')
    sub=parser.add_subparsers(dest='command',required=True)
    tr=sub.add_parser('train')
    tr.add_argument('--data',default='data/fire_sequences')
    tr.add_argument('--output',default='artifacts/gnn')
    tr.add_argument('--test-fire',default='camp_2018')
    tr.add_argument('--epochs',type=int,default=20)
    tr.add_argument('--patience',type=int,default=5)
    tr.add_argument('--hidden',type=int,default=32)
    tr.add_argument('--lr',type=float,default=.002)
    tr.add_argument('--seed',type=int,default=42)
    tr.add_argument('--cell-m',type=float,default=1500)
    tr.add_argument('--margin-km',type=float,default=20)
    tr.add_argument('--max-cells',type=int,default=7000)
    tr.add_argument('--max-hours',type=float,default=20)
    tr.add_argument('--threads',type=int,default=2)
    pr=sub.add_parser('predict')
    pr.add_argument('--checkpoint',default='artifacts/gnn/gnn_model.pt')
    pr.add_argument('--firms',required=True)
    pr.add_argument('--weather')
    pr.add_argument('--fire-name',default='historical_fire')
    pr.add_argument('--pass-index',type=int,default=0)
    pr.add_argument('--top',type=int,default=250)
    pr.add_argument('--threads',type=int,default=2)
    pr.add_argument('--output',default='frontend/forecast.geojson')
    args=parser.parse_args()
    if args.command=='train':train(args)
    else:predict(args)

if __name__=='__main__':main()
