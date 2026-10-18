# EMBER / Wildfire Forensics

**A reproducible, label-isolated, retrospective wildfire ignition-origin reconstruction prototype for IBM Z Datathon 2026.**

> *We can see a fire from space. Can independently observed hotspots and weather help narrow where it began, before looking at the official origin?*

**Status (17 October 2026):** the standard-library propagation engine, seven executable notebooks, live API, browser dashboard, data acquisition scripts, evaluation tools and heterograph exports have been implemented and smoke-tested **with explicitly synthetic observations**. **No real 2018 Camp Fire inference result is reported.** The historical NASA FIRMS archive, optional terrain/fuel rasters, historical power infrastructure and LinuxONE VM still require access and independent validation by the team. Zero claims of IBM Z acceleration.

## First five minutes — working demonstration

Requirements: **Python 3.12+** (the IBM VM is reportedly 3.12.15). This path uses **no pip dependencies**:

```bash
cd wildfire-forensics
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

Read [`docs/METHOD.md`](docs/METHOD.md) for exact formulas and limitations.

## Historical Camp Fire data: what the team must supply

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

**Important:** `evaluate` recomputes model with the same passed settings; for a stronger audit, save the prior `infer` artifact and check its input hashes, then evaluate that frozen output or compare both run outputs. No reported historical score is included in this repo.

## IBM LinuxONE VM instructions (Python 3.12.15)

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

`/api/infer` **computes fresh on each call**. Hashes, model parameters, UTC stamps and candidate ranks enable provenance. Set `FIRE_POWERLINES`, `FIRE_LIGHTNING` and/or `FIRE_PERIMETER` to add contextual overlays. The dashboard uses local HTML/CSS/JS with **no CDN or tile dependency**, so it runs via SSH without public internet (it displays actual coordinates, not an offline basemap). See [`docs/LINUXONE.md`](docs/LINUXONE.md).

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

## Reality-check checklist

- [x] Pure-Python (3.12 syntax) geospatial projection, time handling, clustering and inverse solver
- [x] Wind-aware directed spatial graph and nominal time optimisation
- [x] 5-scenario uncertainty ranking and two uncalibrated support regions
- [x] Label-isolated API and held-out evaluation module
- [x] Historical NASA/Open-Meteo acquisition scripts / input schemas
- [x] Offline browser demo, replay slider, configurable inference, warnings, geo overlays
- [x] Four-type optional heterogeneous graph export
- [x] Seven runnable notebooks, unit tests and synthetic fixtures
- [ ] Historical FIRMS archive input acquired and manually incident-checked
- [ ] Pre-fire elevation/fuel included and validated on the real case
- [ ] Genuine historical evaluation result / second wildfire robustness test
- [ ] IBM LinuxONE VM end-to-end run with `/api/health` proving `s390x`
- [ ] Optional TuringDB live import and query

## Source material & licence

- [NASA FIRMS Data and API](https://firms.modaps.eosdis.nasa.gov/)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [CAL FIRE Camp Fire incident / withheld reference](https://www.fire.ca.gov/incidents/2018/11/8/camp-fire)
- [USGS 3DEP elevation](https://www.usgs.gov/3d-elevation-program)
- [LANDFIRE data](https://www.landfire.gov/)
- [NOAA GOES satellite data](https://www.goes.noaa.gov/)
- [HIFLD](https://hifld-geoplatform.opendata.arcgis.com/)

**Not emergency operations software; not causal attribution or legal fault evidence.** Dataset accuracy, access rights, source timestamps, 2018 historic coverage and hackathon submission requirements must be verified by the participating team.
