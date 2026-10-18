# EMBER — Wildfire Intelligence

**IBM Z Datathon 2026 · Research prototype · Two complementary wildfire prediction tasks**

EMBER investigates wildfire intelligence at two different timescales: **before ignition**, it ranks where a *new* wildfire may be reported during the next seven days; **after an active fire is observed**, an edge-aware graph neural network (GNN) ranks where *new satellite thermal detections* are likely at the next available pass. A separate, earlier prototype reconstructs possible ignition origins retrospectively.

> **Important:** These are separate models, not a jointly trained end-to-end system. Neither forecasts exact ignition points, verified burn perimeters, or emergency outcomes. Their scores are not validated operational probabilities.

## Capabilities and evidence

| Component | Question | Implemented approach | Current evidence |
|---|---|---|---|
| **Weekly ignition occurrence** — `forecasting/` (on the `rayan` branch, not yet merged into `main`) | Which ~25 km cells will contain **at least one newly reported ignition** in the next 7 days? | FPA-FOD fire history + ERA5-family weather; seasonal/geographic features; scikit-learn histogram gradient boosting; climatology and logistic baselines; later WFIGS evaluation | In the **2025 historical test**, 255/332 validation-thresholded high-confidence alerts were followed by a reported ignition (**76.8% precision**). The seasonal model reached **81.8%** on 220 alerts. EMBER found more fire-positive cell-weeks but did not show a statistically established precision advantage at matched alert counts. |
| **Next-pass satellite activity** — `scripts/gnn_forecast.py` | Which ~1 km cells will be **detected** as active at the next VIIRS satellite observation? | Trainable edge-aware message-passing GNN with spatial, recent hotspot, wind and FRP features; stronger proximity and persistence baselines | Saved **Camp Fire V3 replay**, 13 sequential prediction windows from **one** held-out wildfire: mean AP **0.651** versus proximity **0.545** for all next-pass detections; for *newly detected* cells, **0.276** versus **0.172**. Saved V3 run evidence, not an independently reproduced training run. |
| **Retrospective origin reconstruction** — `src/wildfire/` | Where might earlier ignition have occurred, given late observations? | Wind-aware directed lattice, reverse Dijkstra, latent ignition-time search, sensitivity scenarios | Saved Camp Fire result: **17.757 km** error versus **11.153 km** earliest-pass centroid baseline; does **not** beat baseline on this case. |

**Read metrics carefully:** ignition **precision** is the fraction of alerted region-weeks followed by at least one *reported* wildfire; it does not measure the accuracy of precise coordinates. GNN **average precision (AP)** measures detection ranking, **not percent correct** or physically observed burned area. The 13 GNN windows are correlated observations from a single incident, not 13 independent wildfires.

## Try the project

### A. Seven-day ignition forecasts (real historical data)

The weekly forecasting code (`forecasting/` and the `make forecast` targets) is on the **`rayan` branch** and is not merged into `main` yet; check out `rayan` to run it. Requires Python **3.12+** and `numpy`, `pandas`, `scikit-learn` to train or generate fresh forecasts. From the repository root:

```bash
python3 -m pip install numpy pandas scikit-learn
make forecast                  # ingest historical sources, construct features, fit/evaluate models
make forecast-serve            # read-only historical forecast UI; stdlib server on port 8010
```

Open **http://127.0.0.1:8010/forecast**. The server presents **precomputed** historical predictions; it does **not** retrain or infer on each web request. It can serve saved results with just the Python standard library, including on `s390x`.

For new Monday issue dates, use the separately implemented **live-source scoring** command (requires the saved fitted bundles and processed data/cache, and the Python ML stack):

```bash
python3 -m forecasting.predict --date 2026-10-19 --refresh-fires
```

This produces `forecasting/outputs/live/forecast_2026-10-19.csv` and `.geojson`, ranking every cell. **Current live exports still flag the top eight cells**, despite the separately evaluated *variable-count threshold* policies in `forecasting/flexible_alerts.py`; do not describe variable-alert evaluation as the live API's current alert policy. For later scoring against reported incidents, see the CLI help and `forecasting/README.md`.

**Live-data limitation:** the historical FPA-FOD fire database is not a live feed. The live scorer uses WFIGS for recent history and labels, and archived/reanalysis weather for lagged weather features. Reporting delays and the availability dates of each source limit operational interpretation.

### B. Fire-activity GNN replay (saved Camp Fire demonstration)

The `frontend/forecast.html` interface and `frontend/gnn_replay.json` provide a chronological current-detections → predicted next-pass activity → reveal-next-pass workflow. Training code and reproduction instructions are in `docs/GNN_QUICKSTART.md`.

```bash
# From the repository root; historical Camp Fire files are needed for the server's origin endpoint:
PYTHONPATH=src python3 scripts/serve_stdlib.py \
  --dataset data/processed/camp_fire_observations.json
```

Open **http://127.0.0.1:8000/forecast.html** to inspect the **saved replay**. The web UI uses external map tiles/Leaflet and needs network access; a display of the saved replay does **not** prove that PyTorch inference is running on the serving machine.

**V3 evidence caveat:** `frontend/gnn_replay.json` supplies saved rankings and next-pass labels. The V3 report and training log (`artifacts/gnn_v3/gnn_report.json`, `artifacts/gnn_v3_training.log`) are on the `rayan` branch; the model checkpoint and raw training inputs are not committed, so the 13-window evaluation cannot yet be retrained end to end from the repository. LinuxONE training/inference claims require separate **`s390x` runtime and model-execution logs** before inclusion in a submission.

### C. Retrospective ignition-origin demonstration

The original stdlib-only synthetic demonstration and the historical origin methodology remain documented further below. They are **not** the trained weekly ignition model or the next-pass GNN.

## Seven-day forecasting: modelling, validation and results

- **Region and target:** 80 cells (~25 km squares) in Northern California, one issue each Monday. Label = at least one newly **reported** fire in a cell in the following Monday–Sunday window; non-reports are not proof of no ignition.
- **Features:** location, cyclic seasonality, historical per-cell fire frequency, trailing fire reports in cell/neighbours, and 7/14/30/90-day weather statistics. The original reanalysis weather features end **seven days before issue**.
- **Model:** histogram gradient-boosted trees (scikit-learn), evaluated against seasonal climatology, logistic regression and feature-ablation controls. Training rows use leave-one-year-out climatology features.
- **Chronological splits:** train **2015–2020**; tune thresholds/models **2021–2022**; evaluate **2023–2024**; additionally score frozen models on **2025 WFIGS** records. The 2023–24 and 2025 outcomes have now been inspected during development and are **not untouched future holdouts**.
- **2025 variable-alert result:** under a risk threshold selected solely on 2021–22 to target at least 70% validation precision, EMBER issued **332** alerts, **255** followed by reported fire (**76.8% precision**), spanning **32.3%** of positive area-weeks and **44.7%** of recorded ignition events. Climatology issued **220** alerts at **81.8% precision**; this is a *different alert budget*. At equal 332-alert budget, EMBER scored **76.8%** versus climatology **73.8%**, a difference whose reported 95% interval included zero.
- **Other evaluations:** fixed top-8 ranking was retained as an equal-budget diagnostic, **not a recommended production policy**. Six additional signal families (including Red Flag Warnings, holidays, weather timing and gridMET) were tested; no clear additional predictive benefit was established.
- **Limits:** coarse cells and week-long horizon, source-dependent fire reporting, strong climatology baseline, unverified deployment-time availability for every historical covariate. Risk scores are not asserted to be reliable individual ignition probabilities.

On the `rayan` branch, see `forecasting/README.md`, `forecasting/outputs/OVERNIGHT_RESULTS.md`, `forecasting/outputs/FLEXIBLE_ALERTS.md`, `forecasting/outputs/AUDIT.md`, and `forecasting/PREREG_2025.md` for metrics, caveats and reproducibility details.

## Next-pass GNN: model and test definition

The GNN uses a directed/spatial neighbour graph of **approximately 1 km cells**, with temporal satellite hotspot history, active detection counts, FRP and wind/distance/directional edge features. The target is **appearance in the next available satellite observation**, so lead time varies with overpasses; in the saved Camp Fire V3 replay it ranges from about **0.8 hours** to **11.5 hours**. A newly *detected* cell is not necessarily newly ignited or newly burned.

| Saved replay metric (Camp Fire, 13 windows) | Simple proximity baseline | GNN |
|---|---:|---:|
| Mean AP on **all** next-pass detections | 0.545 | **0.651** |
| Mean AP on **new** next-pass detections only | 0.172 | **0.276** |

Persistence baseline for **all** detections was **0.445**. New-only AP excludes currently detected cells **from both** compared ranking methods. The GNN won **13/13** windows for all detections and **12/13** for new detections; this is a **single-fire exploratory evaluation**, not general operational validation. The V3 run trained on 15 incidents and used Palisades 2025 as a separate validation incident. See `docs/GNN_QUICKSTART.md` and the saved replay for implementation details.

## Repository map

```text
forecasting/                 (rayan branch) Weekly new-ignition ML, inputs, baselines, tests, saved predictions
forecasting/outputs/         (rayan branch) Historical and prospective forecasts, metrics, audit reports, maps
scripts/gnn_forecast.py      Edge-aware GNN training/evaluation
scripts/gnn_replay.py        Saved-replay export
frontend/forecast.html       Next-pass wildfire activity investigation UI
frontend/gnn_replay.json     Camp Fire V3 saved detections/predictions
src/wildfire/               Retrospective origin inference and context/evidence graphs
scripts/serve_stdlib.py     Original offline-friendly origin API / UI service
api/                        Optional FastAPI wrapper for the original engine
docs/                       Methodology, GNN and deployment guides
```

---

## Retrospective-origin subsystem: five-minute synthetic demonstration

Requirements: **Python 3.12+**. This original origin-reconstruction demonstration deliberately uses synthetic observations and **no pip dependencies**:

```bash
cd EMBER
python3 scripts/make_synthetic.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m wildfire.cli evaluate \
  --detections data/synthetic/toy_firms.csv \
  --weather data/synthetic/toy_weather.json \
  --powerlines data/synthetic/toy_powerlines.geojson \
  --lightning data/synthetic/toy_lightning.csv \
  --label data/synthetic/toy_reference.json \
  --output artifacts/synthetic_demo.json
PYTHONPATH=src python3 scripts/serve_stdlib.py \
  --dataset data/synthetic/toy_firms.csv \
  --weather data/synthetic/toy_weather.json \
  --powerlines data/synthetic/toy_powerlines.geojson \
  --lightning data/synthetic/toy_lightning.csv --demo
```

Open **http://127.0.0.1:8000**. Click **RUN INFERENCE**, animate the hotspots with the replay slider, and compare variants. The dashboard visibly labels synthetic mode. Optional more convenient command: `bash scripts/run_demo.sh`.

### Working notebooks

For notebooks only, install Python research dependencies on your laptop, not necessarily on LinuxONE:

```bash
python3 -m pip install -e '.[notebooks]'
jupyter lab notebooks/
```

| Notebook | Runnable implementation |
|---|---|
| `00_environment_and_gate.ipynb` | Platform, detection count, independent-pass GO/NO-GO |
| `01_ingest_and_provenance.ipynb` | Schema normalization, timestamps, file hashes |
| `02_spatiotemporal_exploration.ipynb` | Raw hotspot visualization, overpass clustering, wind |
| `03_propagation_graph.ipynb` | Explicit directed spatial lattice and anisotropy |
| `04_inverse_inference.ipynb` | Reverse Dijkstra, origin ranking, score field |
| `05_heldout_validation.ipynb` | LABEL FIRST OPENED HERE, centroid baseline and ablations |
| `06_hypothesis_graph_and_service.ipynb` | Power-line/lightning evidence graph and API interface |

All seven were executed successfully on local Python 3.13 with installed notebook dependencies. Their default observations and labels are **synthetic**.

## Exact architecture

```text
Historical FIRMS CSV ─── time / confidence QC ─── temporal + spatial pass clusters ┐
                                                                               │
Open-Meteo hourly wind ─── correct FROM→TO vectors ─── vector-mean early wind ├──► directed grid
                                                                               │   edge travel times
Pre-fire DEM / fuel-factor tiles (optional) ── grid-cell covariates ───────────┘         │
                                                                                      ▼
                                                    K × reverse Dijkstra from hotspots
                                                                                      │
                                      Per-cell latent ignition-time grid optimisation
                                                                                      │
                           Five predeclared spread/wind hypotheses + mean ranked mass
                                                                                      │
                      inferred origin + model-relative 80/90% support areas + baseline
                                                                                      │
                                             API on LinuxONE → Canvas investigation UI
                                                                                      │
Power lines / lightning / perimeter ─────────────────► evidence/geometry CONTEXT ONLY
```

**Graph construction** — regular grid around early *observations* (not the documented origin); 8-neighbour directed edges. Relative speed uses base spread rate, wind alignment, uphill/downhill directional grade and, if supplied, vegetation multipliers. Candidate travel time to each satellite cluster comes from shortest directed paths.

**Origin score** — choose the assumed ignition time within a **fixed 12-hour lookback**. Penalize arrivals after detection strongly; penalize predictions substantially earlier than detection only weakly because no previous pixel detection does **not** mean unburned. Separate satellite passes have comparable influence rather than treating all pixels as independent.

**Robustness** — evaluate five different spread/wind hypotheses. Softmax-normalized objective scores are **model-relative ranking masses**, **not calibrated posterior probabilities**. Top-80/90% area is not frequentist confidence coverage. Compare against earliest pass centroid, isotropic satellite-only graph, wind-aware and optional covariate-aware fusion.

**Causal firewall** — power lines and lightning are deliberately *NOT* inputs to candidate ranking. Adding a close mapped line creates `NEAR_POWERLINE`, not `PROPAGATES_TO`, and cannot prove fault. The Camp Fire's documented power-line cause is known and must stay outside inference.

Read `docs/METHOD.md` for exact formulas and limitations.

## Retrospective-origin workflow: historical Camp Fire data

The commands below document how the original retrospective model acquires or regenerates inputs. **A real Camp Fire VIIRS archive and retrospective evaluation are now available in project artifacts; these instructions are not a statement that historical data is still missing.** The saved historical evaluation reports **17.757 km** model-origin error versus **11.153 km** for the earliest-pass centroid baseline. This experiment does not demonstrate a gain in origin accuracy.

### 1. NASA FIRMS archived S-NPP VIIRS / NOAA-20 CSV

- Pilot date: **8 November 2018** onward (weather 8–10 November UTC), coarse pilot bbox `[-121.85, 39.55, -121.20, 40.05]` from the shared brief.
- Source: https://firms.modaps.eosdis.nasa.gov/download/ and https://firms.modaps.eosdis.nasa.gov/api/area/
- Area API key: https://firms.modaps.eosdis.nasa.gov/api/map_key
- NASA's *standard processing* sources include `VIIRS_SNPP_SP` and `VIIRS_NOAA20_SP`. Check the product archive’s date availability; historical downloads may require Earthdata access even with an API key.

When a free `MAP_KEY` permits this older date:

```bash
export NASA_FIRMS_MAP_KEY='YOUR_KEY'  # never commit it
python3 scripts/download_data.py --source firms --date 2018-11-08 --days 3 \
  --instrument VIIRS_SNPP_SP --out data/raw/camp_fire_viirs.csv
```

Otherwise download the actual 2018 archive CSV manually. **Do not substitute recent NRT data and call it the Camp Fire.** Then:

```bash
PYTHONPATH=src python3 -m wildfire.cli ingest \
 --firms data/raw/camp_fire_viirs.csv \
 --case config/camp_fire.json \
 --output data/processed/camp_fire_observations.json
PYTHONPATH=src python3 -m wildfire.cli gate \
 --detections data/processed/camp_fire_observations.json
```

**GO/NO-GO:** inspect early coverage and unwanted surrounding incidents. More than one satellite pass is necessary but *not sufficient* for credible origin inference. A late first overpass can make Camp Fire unsuitable; use GOES historical fire detection or change fire if necessary. CAL FIRE records a second ignition; our MVP assumes one dominant spreading fire component and may not explain all observations.

### 2. Hourly Open-Meteo, chosen WITHOUT reading documented origin

Take latitude and longitude from the **earliest observed cluster** (first scatterplot / `clusters[0]`), not CAL FIRE's published ignition coordinates:

```bash
python3 scripts/download_data.py --source weather --date 2018-11-08 \
 --days 3 --lat YOUR_EARLY_CLUSTER_LAT --lon YOUR_EARLY_CLUSTER_LON \
 --out data/raw/camp_fire_weather.json
```

Source: https://open-meteo.com/en/docs/historical-weather-api . Requested timezone is UTC; speed is in m/s. This is historical gridded reanalysis, **not** a per-slope direct wind measurement.

### 3. Optional historical terrain and pre-fire fuel

Download localized 3DEP elevation GeoTIFF and a dated LAND​FIRE (e.g. appropriate 2016) vegetation/relative-fuel data product. Convert raw categorical fuel codes to relative *rates* using an independently documented mapping. **Do not treat categorical fuel class numbers as physical speed multipliers.** Rasterio is used **only on the preprocessing machine**:

```bash
python3 -m pip install -e '.[geo]'
python3 scripts/prepare_grid_rasters.py \
 --detections data/processed/camp_fire_observations.json \
 --dem data/raw/local_3dep.tif \
 --output data/processed/camp_fire_covariates.csv \
 --cell-m 850 --margin-km 9
```

Optional `--fuel-factor-raster` must be an already validated numeric multiplier raster. If raster preprocessing is missing, terrain/fuel are **neutral and reported as missing**, not pretended to be available. Regenerate aligned raster samples if the UI grid cell size or search margin changes.

### 4. Optional power lines, lightning and incident perimeter

- Power lines: **historically validated** locally clipped mapped lines in a GeoJSON FeatureCollection (`LineString`/`MultiLineString`); current HIFLD high-voltage lines can omit local distribution assets and do not demonstrate infrastructure in 2018.
- Lightning: CSV with `latitude,longitude,timestamp_utc` (UTC), with source and location-accuracy provenance kept separately. GOES GLM event footprints can be many kilometres across.
- Perimeter: local incident GeoJSON in `--perimeter` for display only. Final boundaries are not ignition labels.

### 5. Execute historical inference BEFORE revealing CAL FIRE origin

```bash
PYTHONPATH=src python3 -m wildfire.cli infer \
 --detections data/processed/camp_fire_observations.json \
 --weather data/raw/camp_fire_weather.json \
 --output artifacts/camp_fire_blind_model.json
```

Freeze this file, parameters, and source hashes; **then** score (separate command):

```bash
PYTHONPATH=src python3 -m wildfire.cli evaluate \
 --detections data/processed/camp_fire_observations.json \
 --weather data/raw/camp_fire_weather.json \
 --label data/evaluation/camp_fire_reference.json \
 --output artifacts/camp_fire_evaluated.json
```

**Important:** `evaluate` recomputes the model using passed settings; for a stronger audit, compare it with the frozen `infer` artifact and verify input hashes. The repository includes a historical reference evaluation at `artifacts/camp_evaluation.json`, where the origin model underperforms its centroid baseline.

## IBM LinuxONE VM instructions (retrospective origin service)

`src/wildfire` and `scripts/serve_stdlib.py` are **stdlib-only**; no SciPy, rasterio, GraphSAGE, TuringDB or FastAPI installation is required for the core. FastAPI is offered as optional `api/main.py` if native dependencies work:

```bash
# Copy files to the VM (on your laptop):
scp -r wildfire-forensics USER@VM_HOST:~/
# Then SSH onto the VM:
cd ~/wildfire-forensics
python3 --version && uname -m
export FIRE_DATA=data/processed/camp_fire_observations.json
export FIRE_WEATHER=data/raw/camp_fire_weather.json
# Use local-only binding and an SSH tunnel; don't expose test services publicly.
bash scripts/deploy_linuxone.sh
```

From your laptop, forward remote localhost port 8000 with `ssh -N -L 8000:127.0.0.1:8000 USER@VM_HOST`, then visit http://127.0.0.1:8000 . For proof of actual VM inference:

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s 'http://127.0.0.1:8000/api/infer?variant=fusion&ensemble=true' > artifacts/linuxone_result.json
uname -m
```

`/api/infer` **computes fresh on each call**. Hashes, model parameters, UTC stamps and candidate ranks enable provenance. Set `FIRE_POWERLINES`, `FIRE_LIGHTNING` and/or `FIRE_PERIMETER` to add contextual overlays. The dashboard uses local HTML/CSS/JS with **no CDN or tile dependency**, so it runs via SSH without public internet (it displays actual coordinates, not an offline basemap). See `docs/LINUXONE.md`.

### Optional FastAPI deployment

```bash
python3 -m pip install -e '.[api]'
export FIRE_DATA=data/processed/camp_fire_observations.json
export FIRE_WEATHER=data/raw/camp_fire_weather.json
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

If pip cannot install s390x-native packages, return immediately to the stdlib server. Never make optional tools essential for the demo.

## Optional TuringDB / heterogeneous evidence graph

`src/wildfire/heterograph.py` exports a **physical + evidence** property graph with `SPATIAL_CELL`, `THERMAL_OBSERVATION`, `INFRASTRUCTURE` and `LIGHTNING_EVENT` node types. Relationships:

| Edge label | Interpretation | Affects origin ranking? |
|---|---|---|
| `PROPAGATES_TO` | Directional, modelled edge travel time between spatial cells | **Yes**, via Python Dijkstra graph |
| `OBSERVED_AT` | Satellite cluster seen near a cell | Yes, through observed cluster constraints |
| `NEAR_POWERLINE` | Mapped line within spatial radius | **No** |
| `NEAR_LIGHTNING` | Space/time association with nearby flash | **No** |

```bash
PYTHONPATH=src python3 scripts/export_heterograph.py \
  --detections data/synthetic/toy_firms.csv \
  --weather data/synthetic/toy_weather.json \
  --powerlines data/synthetic/toy_powerlines.geojson \
  --lightning data/synthetic/toy_lightning.csv \
  --top 50 --output artifacts/heterograph
```

Outputs: `nodes.csv`, `edges.csv`, `metadata.json`. TuringDB-specific importer adapters depend on the chosen version/schema and have **not been integration-tested**. Place that DB on an architecture officially supported by its distribution; don't rely on an `s390x` binary. You can adapt generic CSV import into TuringDB or any graph store. Graph data remains explorable in the web UI without it.

## Retrospective-origin reality-check checklist

- [x] Pure-Python (3.12 syntax) geospatial projection, time handling, clustering and inverse solver
- [x] Wind-aware directed spatial graph and nominal time optimisation
- [x] 5-scenario uncertainty ranking and two uncalibrated support regions
- [x] Label-isolated API and held-out evaluation module
- [x] Historical NASA/Open-Meteo acquisition scripts / input schemas
- [x] Offline browser demo, replay slider, configurable inference, warnings, geo overlays
- [x] Four-type optional heterogeneous graph export
- [x] Seven runnable notebooks, unit tests and synthetic fixtures
- [x] Historical FIRMS VIIRS archive used for the Camp Fire evaluation (2,277 detections across 7 passes; coverage limits still apply)
- [ ] Pre-fire elevation/fuel included and validated on the real case
- [x] Single real-case Camp Fire origin evaluation saved (17.757 km model error versus 11.153 km centroid baseline; model underperforms)
- [ ] Independent second-fire robustness test for retrospective origin reconstruction
- [ ] IBM LinuxONE VM end-to-end run with `/api/health` proving `s390x`
- [ ] Optional TuringDB live import and query

## Source material & licence

- NASA FIRMS Data and API: https://firms.modaps.eosdis.nasa.gov/
- Open-Meteo Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
- CAL FIRE Camp Fire incident / withheld reference: https://www.fire.ca.gov/incidents/2018/11/8/camp-fire
- USGS 3DEP elevation: https://www.usgs.gov/3d-elevation-program
- LANDFIRE data: https://www.landfire.gov/
- NOAA GOES satellite data: https://www.goes.noaa.gov/
- HIFLD: https://hifld-geoplatform.opendata.arcgis.com/

**Not emergency operations software; not causal attribution or legal fault evidence.** Neither forecast is an operational evacuation recommendation. Dataset accuracy, source timestamps, satellite detection completeness, architecture/deployment proof and hackathon submission requirements must be verified by the participating team.
