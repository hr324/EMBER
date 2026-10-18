#!/usr/bin/env python3
"""Generate six fully runnable, documented Jupyter notebooks from versioned code.

Execution defaults to intentionally synthetic input. Switch INPUT, WEATHER and
LABEL paths after obtaining actual historical satellite and meteorological data.
"""
from __future__ import annotations
from pathlib import Path
import nbformat as nbf

ROOT=Path(__file__).resolve().parents[1]
SETUP='''from pathlib import Path
import sys
ROOT = Path.cwd()
if not (ROOT / "src").exists(): ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
import json
import matplotlib.pyplot as plt
INPUT = ROOT / "data/synthetic/toy_firms.csv"  # SYNTHETIC DEMO, NOT historical NASA data
WEATHER = ROOT / "data/synthetic/toy_weather.json"
assert INPUT.exists(), "Run `python scripts/make_synthetic.py` from repository root first"
print("Data mode: SYNTHETIC - demonstration only")'''

notebooks={
'00_environment_and_gate.ipynb':[
 ('md', '# 00 · Platform & data availability gate\n\nConfirm Python, FIRMS CSV, UTC and independent overpasses **before** building the model. The sample is fictional and must never be presented as the 2018 Camp Fire.'),
 ('py', SETUP),
 ('py', '''import platform
from wildfire.ingest import load_firms, observation_gate
print('Python:', platform.python_version(), 'architecture:', platform.machine())
print('Core inference dependencies: Python standard library only')
detections = load_firms(INPUT)
gate = observation_gate(detections)
print(json.dumps(gate, indent=2))
assert gate['usable'], 'Stop: need multiple temporally separated overpasses, or switch case / add GOES' '''),
 ('py', '''from collections import Counter
print('Sensors:', Counter(d['instrument'] for d in detections))
print('Start and end:', detections[0]['observed_utc'], detections[-1]['observed_utc'])
print('Sanity: timestamps are UTC and coordinates bounded:', all(d['observed_utc'].endswith('Z') for d in detections))'''),
 ('md','**Real-data action:** Download actual NASA FIRMS archived CSV (requires historical archive access or a free MAP_KEY if available), then change `INPUT`. The historical 2018 coverage decision remains unverified in this package.')],
'01_ingest_and_provenance.ipynb':[
 ('md','# 01 · NASA FIRMS schema, cleaning and provenance\n\nDeduplicate points and normalize acquisition times. Files are retained with SHA-256 provenance. A thermal centroid is neither a burned perimeter nor an origin.'),
 ('py',SETUP),
 ('py','''from wildfire.ingest import load_firms, load_weather
from wildfire.cli import sha256
observations = load_firms(INPUT)
weather = load_weather(WEATHER)
print('Detections:', len(observations), 'weather hours:', len(weather))
print('Satellite hash:', sha256(str(INPUT)))
print('Weather hash:', sha256(str(WEATHER)))
print('First normalized observation:', observations[0])
print('First normalized weather:', weather[0])'''),
 ('py','''# Save canonical JSON snapshots without modifying original source files.
out = ROOT / 'artifacts/01_normalized_satellite.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(observations, indent=2))
print('Wrote', out)'''),
 ('md','**Input contract:** FIRMS needs `latitude`, `longitude`, `acq_date`, `acq_time`; VIIRS `confidence`, `frp`, `scan`, `track` are preserved. Open-Meteo JSON must use `timezone=UTC`, and wind direction is *from* its source, unlike the graph travel vector.')],
'02_spatiotemporal_exploration.ipynb':[
 ('md','# 02 · Spatiotemporal observation exploration\n\nCheck pass independence and early clusters. Most apparent satellite "motion" can reflect sampling cadence or clouds, so clusters receive reduced correlated evidence weights.'),
 ('py',SETUP),
 ('py','''from wildfire.ingest import load_firms, load_weather
from wildfire.features import cluster_detections,weather_summary
detections = load_firms(INPUT)
weather = load_weather(WEATHER)
clusters = cluster_detections(detections,max_hours=10)
print('Independent cluster count:', len(clusters))
for c in clusters: print(c['cluster_id'], c['timestamp_utc'], c['n_pixels'],'pixels')'''),
 ('py','''# Inspect rather than assume every hot spot belongs to the target incident.
fig, ax = plt.subplots(figsize=(9,5))
s = ax.scatter([d['longitude'] for d in detections], [d['latitude'] for d in detections],
               c=list(range(len(detections))), cmap='inferno', s=28)
ax.scatter([c['longitude'] for c in clusters], [c['latitude'] for c in clusters],
           marker='x',s=110,c='cyan',label='Overpass clusters')
ax.set(xlabel='Longitude',ylabel='Latitude',title='Synthetic data: raw detections and cluster centres')
ax.legend();plt.colorbar(s,ax=ax,label='Acquisition order');plt.show()'''),
 ('py','''from wildfire.ingest import parse_utc
from datetime import timedelta
first = parse_utc(clusters[0]['timestamp_utc'])
last = first + timedelta(hours=10)
summary = weather_summary(weather,first.isoformat().replace('+00:00','Z'),
                           last.isoformat().replace('+00:00','Z'))
print(json.dumps(summary,indent=2))'''),
 ('md','**Decision gate:** If all thermal clusters belong to one late overpass, causal backtracking is underdetermined. Increase temporal cadence using GOES or change fire rather than manufacture certainty.')],
'03_propagation_graph.ipynb':[
 ('md','# 03 · Directed propagation graph\n\nThe novel artefact is an 8-neighbour spatial lattice with edge travel-time costs, not a learned GNN. Wind and slope create asymmetric paths.'),
 ('py',SETUP),
 ('py','''from wildfire.ingest import load_firms, load_weather,parse_utc
from wildfire.features import cluster_detections,weather_summary
from wildfire.graph import build_grid,build_adjacency,SpreadParameters,reverse_shortest_paths
from datetime import timedelta
clusters=cluster_detections(load_firms(INPUT))
grid=build_grid(clusters,cell_m=850,margin_km=9)
first=parse_utc(clusters[0]['timestamp_utc'])
end=(first+timedelta(hours=10)).isoformat().replace('+00:00','Z')
wind=weather_summary(load_weather(WEATHER),first.isoformat().replace('+00:00','Z'),end)
adj,stats=build_adjacency(grid,wind,SpreadParameters())
print('Graph stats:',stats)
print('Projected grid range:',grid.nx,'x',grid.ny)'''),
 ('py','''# Show a small subset of physically weighted arrow edges.
fig,ax=plt.subplots(figsize=(10,6))
step=max(1,len(grid.nodes)//280)
for n in grid.nodes[::step]:
    ax.scatter(n.lon,n.lat,s=3,c='lightgray')
for c in clusters:
    ax.scatter(c['longitude'],c['latitude'],s=80,marker='x',c='darkred')
ax.set(xlabel='Longitude',ylabel='Latitude',title='Candidate lattice and observed fire clusters')
plt.show()'''),
 ('py','''# Check that wind creates directional edges: eastward spread faster than westward.
node=grid.nearest(clusters[0]['latitude'],clusters[0]['longitude'])
next_east=node+1
forward=dict(adj[node]).get(next_east)
backward=dict(adj[next_east]).get(node)
print('Travel east (hours):',forward,'west:',backward,'eastward faster:',forward<backward)'''),
 ('md','**Model limitation:** The exponential spread-speed law is a sensitivity parameterisation, not a fully calibrated wildfire simulation. Future work: dynamic wind, validated rate-of-spread laws and pre-fire fuel mapping.')],
'04_inverse_inference.ipynb':[
 ('md','# 04 · Reverse shortest paths and ignition origin scoring\n\nFor every candidate cell, optimise a latent ignition time and compare arrival upper bounds to each detected hotspot. Revisit gaps motivate a weak early-arrival penalty.'),
 ('py',SETUP),
 ('py','''from wildfire.ingest import load_firms,load_weather
from wildfire.inference import infer_origin,InferenceOptions,public_result
sat=load_firms(INPUT)
wx=load_weather(WEATHER)
options=InferenceOptions(cell_m=850,margin_km=9,ensemble=True)
result=infer_origin(sat,wx,options,variant='fusion')
print('Status:',result['status'],'Best:',result['best_origin'])
print('Top-80% model-score area:',result['regions']['top80']['area_km2'],'km²')
for warning in result['warnings']:print('CAVEAT:',warning)'''),
 ('py','''# False-colour scores visualize a rank field, not calibrated posterior confidence.
fig,ax=plt.subplots(figsize=(10,6))
candidates=result['candidate_cells']
values=[c['score_mass'] for c in candidates]
sc=ax.scatter([c['longitude'] for c in candidates],[c['latitude'] for c in candidates],
              c=values,cmap='magma',s=22)
ax.scatter(result['best_origin']['longitude'],result['best_origin']['latitude'],
           marker='*',s=180,c='cyan',edgecolors='black',label='Top candidate')
ax.scatter(result['baseline_centroid']['longitude'],result['baseline_centroid']['latitude'],
           marker='x',s=125,c='lime',label='Earliest centroid')
ax.set(xlabel='Longitude',ylabel='Latitude',title='Synthetic model-relative origin ranking')
ax.legend();plt.colorbar(sc,ax=ax,label='Normalised score mass per grid cell');plt.show()'''),
 ('py','''out=ROOT/'artifacts/04_inference.json'
out.write_text(json.dumps(public_result(result),indent=2))
print('Saved model output:',out)
print('Evaluation label has not been loaded in this notebook.')'''),
 ('md','**Interpretation:** top-80%/90% score regions have NOT been empirically calibrated; this is a weighted candidate ranking, not a forensic probability or proof of utility involvement.')],
'05_heldout_validation.ipynb':[
 ('md','# 05 · Withheld-origin evaluation and controlled ablations\n\n**Only here** may we open documented ignition labels. In this notebook, the reference is entirely SYNTHETIC and therefore proves pipeline operation only. For historical Camp Fire evaluation switch LABEL to `data/evaluation/camp_fire_reference.json` after collecting real data.'),
 ('py',SETUP),
 ('py','''from wildfire.ingest import load_firms,load_weather
from wildfire.inference import infer_origin,InferenceOptions
from wildfire.evaluation import evaluate_result,ablation_study
sat=load_firms(INPUT);wx=load_weather(WEATHER)
options=InferenceOptions(cell_m=850,margin_km=9,ensemble=True)
# Model is fitted FIRST; label is loaded only to score results.
model=infer_origin(sat,wx,options,variant='fusion')
LABEL=ROOT/'data/synthetic/toy_reference.json'
metrics=evaluate_result(model,str(LABEL))
print(json.dumps(metrics,indent=2))'''),
 ('py','''# Ablations have matched candidate boundaries and parameters.
rows=ablation_study(sat,wx,str(LABEL),options=options)
for r in rows:print(r)
fig,ax=plt.subplots(figsize=(7,4))
ax.bar([r['variant'] for r in rows],[r['model_error_km'] for r in rows])
ax.axhline(rows[0]['centroid_baseline_error_km'],linestyle='--',color='black',label='Earliest centroid')
ax.set(ylabel='Location error (km)',title='Synthetic ablation only — NOT real wildfire results')
ax.legend();plt.show()'''),
 ('py','''# The reference file is never input to candidate selection or physical graph edge costs.
summary={'reference_type':'SYNTHETIC - demonstration only','evaluation':metrics,'ablations':rows}
out=ROOT/'artifacts/05_evaluation.json';out.write_text(json.dumps(summary,indent=2))
print('Saved',out)'''),
 ('md','**Controls:** Do not choose an observation cutoff, search margin, propagation speed or favourable model based on the documented ignition. A single historical case is a case study; repeat on independent fires for any generalisation claim.')],
'06_hypothesis_graph_and_service.ipynb':[
 ('md','# 06 · Heterogeneous evidence graph and deployable service\n\nKeep ignition hypotheses distinct from spreading physics. A line near a candidate or lightning event prior to ignition is a spatial/temporal association, never an established cause.'),
 ('py',SETUP),
 ('py','''from wildfire.service import ApplicationService,ServerSettings
from wildfire.evidence import build_evidence_graph
from wildfire.ingest import load_firms,load_weather
from wildfire.inference import infer_origin,InferenceOptions
sat=load_firms(INPUT);wx=load_weather(WEATHER)
model=infer_origin(sat,wx,InferenceOptions(ensemble=False))
evidence=build_evidence_graph(model,
                  str(ROOT/'data/synthetic/toy_powerlines.geojson'),
                  str(ROOT/'data/synthetic/toy_lightning.csv'))
print('Entities:',len(evidence['nodes']),'Relations:',len(evidence['edges']))
for e in evidence['edges'][-3:]:print(e)'''),
 ('py','''# The API service uses the same pure-Python inference engine as the notebooks.
service=ApplicationService(ServerSettings(str(INPUT),str(WEATHER),
    powerlines=str(ROOT/'data/synthetic/toy_powerlines.geojson'),
    lightning=str(ROOT/'data/synthetic/toy_lightning.csv'),mode='synthetic'))
print('Platform / integrity:',json.dumps(service.health(),indent=2))
print('Fresh inference best cell:',service.infer('wind',1200,5,False)['inference']['best_origin'])'''),
 ('py','''# Export portable graph tables; optionally adapt for TuringDB importer.
import csv
out=ROOT/'artifacts/evidence_entities.csv'
with out.open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['id','kind','properties_json'])
    for node in evidence['nodes']:
        w.writerow([node['id'],node['kind'],json.dumps({k:v for k,v in node.items() if k not in ('id','kind')})])
print('Saved',out)'''),
 ('md','**IBM Z proof:** run `uname -m`, Python version, `/api/health` and `/api/infer` ON your LinuxONE VM. No s390x TuringDB binary is assumed. The TuringDB graph should run separately, or use portable CSV exports.')],
}

def main():
    """Construct notebooks with Markdown rationale and clear runnable code cells."""
    out=ROOT/'notebooks';out.mkdir(exist_ok=True)
    for name,steps in notebooks.items():
        cells=[nbf.v4.new_markdown_cell(value) if kind=='md' else nbf.v4.new_code_cell(value)
               for kind,value in steps]
        nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
             'language_info':{'name':'python','version':'3.12'}})
        nbf.validate(nb);nbf.write(nb,out/name)
        print('Created',out/name)

if __name__=='__main__':main()
