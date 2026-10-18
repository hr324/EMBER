# EMBER Forecast GNN — 9-hour hackathon handoff

**Target:** Predict cells that will be detected by NASA FIRMS in the NEXT satellite pass, based on earlier passes and contemporaneous weather. This is **not** a 30- or 60-minute forecast, a burn-perimeter prediction, or an emergency warning.

## What is actually implemented in this optional add-on?

- A **trainable 2-layer edge-aware message-passing GNN**, with neural networks computing messages and gates from neighbour and edge features.
- Nodes are geographical cells (default **1.5 km**, configurable); edges join **eight neighbours in each direction**.
- Node inputs: current/previous thermal detections, brightness proxy FRP, observed pixel count, distance to recently observed fire, relative location and available recent wind speed.
- Edge inputs: physics-based travel-time estimate, relative direction and wind alignment.
- Training target: which cells NASA FIRMS actually detects in a **later** pass. The later pass NEVER appears in the input features.
- PyTorch + AdamW, weighted binary classification loss, validation-based early stopping.
- Whole-fire training/validation/test separation. Training on snapshots of one fire and testing snapshots of the same fire is **not** treated as generalisation.
- Baseline: persistence of current detections. Metric: average precision on later **detected** active cells, with explicit detection-coverage limitations.
- A separate `/forecast.html` replay map with **Show next actual detections** button, using outputs from saved learned weights.

**Important limitations:** There are missing negatives because lack of an FIRMS hotspot does not prove a cell was unburned. Confidence scores are not calibrated. A NASA VIIRS overpass can be hours later. Geographic AOIs require manual checks for contamination by unrelated fires. This is research-prototype predictive learning only.

## Tonight: PowerShell laptop

Apply the patch ZIP to the **root** of the existing `wildfire-forensics` folder; keep existing frontend hotfixes intact.

```powershell
Expand-Archive "$HOME\Downloads\EMBER_GNN_Forecast_Patch.zip" -DestinationPath . -Force
$env:PYTHONPATH = "src"
py -m pip install torch
py -m unittest discover -s tests -v
```

Set a **regenerated** FIRMS API key locally (never put it in Git or screenshots):

```powershell
$env:NASA_FIRMS_MAP_KEY = "YOUR_NEW_KEY"
py scripts\download_fire_collection.py
```

That attempts Camp (2018), Dixie (2021), Park (2024), Eaton (2025), Palisades (2025), including weather near the earliest observed detections. **These are starting AOIs, not certified clean one-fire datasets**. Inspect each CSV/first-pass map. The train command requires **at least three fires with eligible temporal pairs**. More is preferable.

If API calls fail, use the FIRMS archive manually and place raw CSVs at `data/fire_sequences/CASE/firms.csv`; optional weather is `weather.json`.

Transfer the repo with raw snapshot files to LinuxONE (use your normal SSH/SCP credentials), then run there:

```bash
cd wildfire-forensics
python3 --version
uname -m
python3 -m pip show torch || python3 -m pip install torch
PYTHONPATH=src python3 scripts/gnn_forecast.py train --data data/fire_sequences \
  --test-fire camp_2018 --epochs 18 --cell-m 1500 --margin-km 20 \
  --threads 2 --output artifacts/gnn | tee artifacts/gnn_training.log
```

If the LinuxONE `torch` wheel is unavailable in the VM's pip environment, check IBM-provided runtime/container support. **Do not try compiling PyTorch from source during the hackathon.** If needed, train where PyTorch is already available, and report deployment locations accurately.

### Evaluate + replay a held-out fire

The training command saves `artifacts/gnn/gnn_report.json` with a *held-out-fire* comparison and `gnn_model.pt` with learned weights.

```bash
PYTHONPATH=src python3 scripts/gnn_replay.py \
  --checkpoint artifacts/gnn/gnn_model.pt \
  --firms data/fire_sequences/camp_2018/firms.csv \
  --weather data/fire_sequences/camp_2018/weather.json \
  --name camp_2018 --output frontend/gnn_replay.json
python3 scripts/serve_stdlib.py --dataset data/fire_sequences/camp_2018/firms.csv \
  --weather data/fire_sequences/camp_2018/weather.json --host 127.0.0.1
```

Open **`http://localhost:8000/forecast.html`** (SSH port-forward if remote). Select a satellite pass, show orange GNN prediction, and reveal next actual hotspots in red. `forecast.html` uses external Leaflet and OpenStreetMap resources; it needs internet access.

## Critical decision gates

1. **Within 40 minutes:** Download at least 3 wildfire CSVs and confirm each has 2+ independent passes with later detections inside the grid. If not, stop pursuing GNN rather than invent training records.
2. **Within 90 minutes:** Run successful `train` and verify validation and held-out metrics. Never report synthetic fixture metrics as real accuracy.
3. **Within 120 minutes:** Save machine information, train log, learned weights and a working prediction-reveal demo. Finish submission materials.

## In your pitch

**Say:** "We train an edge-aware GNN on historical NASA satellite observations to predict where thermal activity will be detected in the next pass, using weather-informed spatial relationships. Training and inference run on LinuxONE [only once verified]."

**Do not say:** "We forecast wildfire perimeter exactly", "we predict 30 minutes ahead" or "we beat the baseline" without matching real held-out evidence.

The old origin-reconstruction demo remains available at `/`; it is the earlier Dijkstra baseline, **not** the trained forecast model. The GNN demo is `/forecast.html`.
