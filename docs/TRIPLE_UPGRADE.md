# EMBER — Three-part competition upgrade (2026-10-18)

**Changes are additive. Your existing LinuxONE GNN checkpoint is preserved.** This package modifies only the files listed in `PATCH_README.txt`. The wildfire observations and learned weights already in your repo are NOT replaced.

## Exactly what was implemented

1. **Extra fire discovery + QC.** `scripts/expand_fire_dataset.py` queries NASA EONET v3 for archived, geographically located wildfires in 2020–2025. It uses EONET locations to bound historical NASA FIRMS satellite download requests and obtains Open-Meteo weather at the first observed thermal cluster. It rejects missing satellite history, fewer than three passes, fewer than 50 detections, and first-pass locations too far from EONET's event location. New cases are **provisional** and are excluded from training until listed in a manually reviewed approval file. This guards against accidentally treating two nearby fires as one fire. EONET coordinates are NOT trained as labels or features, and aren't guaranteed ignition points. Data access requires NASA MAP_KEY and internet access. **No new fires have been downloaded or independently validated inside this patch.**
2. **Stronger non-neural benchmark.** Every held-out next-pass test now compares (a) learned GNN, (b) persistence, (c) spatial proximity: ranking grid cells by their distance to today's satellite detections. Evaluation uses the SAME future labels and same grid for each approach. The new metrics are in `artifacts/gnn/gnn_report.json` and the replay UI. No retraining is needed to compare your current checkpoint against the stronger benchmark.
3. **Population-aware forecast prioritisation.** `scripts/enrich_population.py` reads 2017 WorldPop (for the 2018 Camp Fire) or a chosen other-year 1km population GeoTIFF and sums population values overlapping each forecast grid cell, with fractional raster-pixel overlap. A transparent uncalibrated **relative index = GNN score × log(1 + estimated residents in that cell)** ranks the top cells that might merit attention. Optional Census place gazetteer supplies approximate nearest town names. No additional learned model, no extra features passed to the GNN, no claim to predict the actual number of people affected. In the browser, click a ranked zone to pan to it.

## First: apply patch inside your IBM JupyterLab terminal

Upload `EMBER_Triple_Upgrade_Patch.zip` with JupyterLab's Upload arrow; then:

```bash
cd ~/EMBER-main
python3 -m zipfile -e ~/EMBER_Triple_Upgrade_Patch.zip .
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Expected: **26 tests pass** with rasterio installed, and the raster-dependent test skips if rasterio isn't installed. Your model weights remain unchanged.

## Quickest possible improvement (5 minutes): stronger baseline

```bash
cd ~/EMBER-main
PYTHONPATH=src python3 scripts/gnn_replay.py \
  --checkpoint artifacts/gnn/gnn_model.pt \
  --firms data/fire_sequences/camp_2018/firms.csv \
  --weather data/fire_sequences/camp_2018/weather.json \
  --name camp_2018 --output frontend/gnn_replay.json
```

Open `/forecast.html` on the running web server. Click **Reveal outcome**; it will now compare the GNN against persistence AND the distance baseline. On a reproduced three-epoch run using the preexisting four real fires, mean average precision across Camp Fire's 6 forecast windows was GNN **0.7711**, proximity **0.6480**, persistence **0.5431**. These are ranking metrics on ONE held-out wildfire, **not population-level accuracy or calibrated fire probabilities**.

## Collect more fires (network access + fresh NASA key required)

Never paste the FIRMS key into chat, scripts, Git or shell history. Regenerate the key previously disclosed.

```bash
# In IBM JupyterLab terminal. Key entry will not echo or enter command history.
read -rsp 'NASA FIRMS MAP_KEY: ' NASA_FIRMS_MAP_KEY; echo
export NASA_FIRMS_MAP_KEY

# List source incidents first. This needs only NASA EONET access, no FIRMS key usage.
PYTHONPATH=src python3 scripts/expand_fire_dataset.py --discover-only \
  --years 2020 2021 2022 2023 2024 2025 > artifacts/discovered_fires.json

# Start conservatively; may take time and API requests may be refused.
PYTHONPATH=src python3 scripts/expand_fire_dataset.py \
  --max-new 12 --max-candidates 35 \
  2>&1 | tee artifacts/expansion_download.log

PYTHONPATH=src python3 scripts/audit_sequences.py
```

Review `data/fire_sequences/expansion_report.json` and `artifacts/fire_quality_audit.json`. **Quality-gate success is not proof the bounding box contains only one wildfire**. Inspect early and late satellite observations on a map before including a new fire. Don't automatically train on every downloaded EONET folder.

Create `data/fire_sequences/approved_fires.txt` (one folder name per line), beginning with the FOUR checked incident folders and adding **only visually reviewed** additional cases:

```text
camp_2018
dixie_2021
eaton_2025
palisades_2025
```

Train on the reviewed cases only:

```bash
PYTHONPATH=src python3 scripts/gnn_forecast.py train \
  --data data/fire_sequences \
  --approved-list data/fire_sequences/approved_fires.txt \
  --test-fire camp_2018 \
  --epochs 18 --cell-m 2000 --margin-km 20 --threads 2 \
  --output artifacts/gnn_v2 \
  2>&1 | tee artifacts/gnn_v2_training.log
```

This will not overwrite the existing `artifacts/gnn/gnn_model.pt`. Inspect `artifacts/gnn_v2/gnn_report.json` and choose the better validated run (do not pick the best test score by tuning on Camp Fire; reserve additional held-out fires when dataset permits). To run new model replay, point `--checkpoint` to `artifacts/gnn_v2/gnn_model.pt` only after training.

**Note:** source years and event dates are EONET event metadata, which can be imprecise. The script uses only geolocated events in California and surrounding territory, and limits duplicate nearby events. If EONET access fails, keep the existing four fires and submit the already-tested prototype.

## Add actual population exposure (optional 15–30 minutes if downloads work)

Best on **Windows PowerShell**, where installing `rasterio` is simpler. Copy the latest `frontend/gnn_replay.json` from the LinuxONE Jupyter file browser to your Windows `wildfire-forensics/frontend/` directory, and apply the same patch locally first.

```powershell
py -m pip install rasterio
$env:PYTHONPATH = 'src'
py scripts\enrich_population.py --replay frontend\gnn_replay.json --output frontend\gnn_replay.json --year 2017 --download --places
```

For a 2021 or 2025 fire, use `--year 2020`. The WorldPop USA 1km raster is about 50 MB. `--places` optionally downloads the 2024 US Census California places Gazetteer for approximate nearest municipality names. The enriched JSON can be downloaded/uploaded via JupyterLab to replace `frontend/gnn_replay.json` on LinuxONE. The GNN requires neither rasterio nor the raster file for inference.

Why **2017** for Camp? Using post-fire 2020 population would badly distort interpretation for Paradise, which was devastated in 2018. Population is only a static **contextual overlay**, never a training feature, and still not a verified count of people at risk during the fire. For 2021–2025 events, 2020 is a historical approximation, not current population.

Raw download sources:
- NASA EONET event records: https://eonet.gsfc.nasa.gov/docs/v3
- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/api/
- Open-Meteo historical archive: https://open-meteo.com/en/docs/historical-weather-api
- WorldPop 2017 USA 1km: https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2017/USA/
- WorldPop 2020 USA 1km: https://hub.worldpop.org/geodata/summary?id=29755
- Census CA places: https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_gaz_place_06.txt

## Responsible claim / slide wording

> EMBER trains an edge-aware GNN on satellite observation sequences using IBM Z, and forecasts the next satellite-detected fire locations. We test on a held-out wildfire against persistence and a stronger nearest-hotspot baseline. A separate, experimental WorldPop layer ranks population-bearing forecast cells for investigation. New training incidents undergo a provenance and quality review.

**Don't say:** predicts all areas that will burn, 77% correct, accurately estimates lives at risk, real-time evacuation-ready, calibrated probability, 15–25 fires successfully trained (unless the new review/long training run actually occurs).
