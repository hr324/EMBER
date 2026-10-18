# Immediate handoff for IBM Z Datathon team

## What's implemented and independently exercised

- Python 3.12 compatible, **stdlib-only** core including historical FIRMS parsing, UTC normalization, satellite-pass clustering, wind vectors and derived confidence features.
- Directed 8-neighbour propagation graph, optional terrain/fuel covariates, reverse-Dijkstra inverse ignition ranking, 5-scenario parameter ensemble, two uncalibrated support regions.
- Isolated official-origin evaluation module, centroid baseline, wind/terrain ablation hooks, retrospective-source cautions.
- Power-line/lightning context, typed heterogeneous propagation/evidence graph export for optional TuringDB.
- Offline browser dashboard, working stdlib HTTP service, optional FastAPI service, seven executable notebooks.
- 18 passing automated tests. All seven notebooks executed successfully. Synthetic ground truth is only used in the evaluation stage.

## First five actions for the human team

1. **IBM VM owner:** verify SSH, run `python3 --version && uname -m`, copy/unzip repo. Run synthetic smoke tests and `scripts/deploy_linuxone.sh` with `FIRE_MODE=synthetic` to prove inference is on `s390x`, then port-forward dashboard. Capture evidence.
2. **Satellite owner:** fetch historical 8–10 Nov 2018 FIRMS *standard-processing* archive data; run `fireforensics ingest` and `gate`. Determine first detection time and number of independent overpasses. Camp Fire GO/NO-GO should be decided immediately.
3. **Weather owner:** derive the sample location from observed early hotspot clusters, fetch the matching UTC Open-Meteo hourly reanalysis, and check physical direction convention.
4. **ML owner:** freeze grid resolution, margin, speed priors and observation processing before opening `data/evaluation/camp_fire_reference.json`. Run real inference once and record SHA256; **only then** run real evaluation.
5. **Frontend/graph owner:** connect the supplied historical files to VM backend. Optional pre-2018 DEM/fuel and power-line/lightning overlays should not delay the end-to-end demo. TuringDB import is a stretch objective.

## Visible blockers / no unsupported claims

- 2018 FIRMS actual archive and Open-Meteo weather data are NOT included; a NASA key / Earthdata archive access and outbound connectivity may be required.
- Historical coverage GO/NO-GO has NOT been run. The Camp Fire may be underdetermined by polar-orbiting observations and contains documented additional ignition.
- No actual LinuxONE VM was accessed; local test machine was x86_64 Python 3.13.5. Stdlib core is designed for Python 3.12.15 but remains unverified on the VM.
- TuringDB is NOT installed/tested; graph CSV is ready for importer adaptation on a supported architecture.
- No GNN, XGBoost, conformal guarantees or calibrated physical spread model are claimed.
- The single synthetic smoke test yields 0.799km origin error versus 2.328km centroid error. This is **not** a real wildfire evaluation result.

## Commands to copy

```bash
cd wildfire-forensics
make test
make infer
make demo
# Once real CSV and JSON arrive:
PYTHONPATH=src python3 -m wildfire.cli ingest --firms data/raw/camp_fire_viirs.csv --case config/camp_fire.json --output data/processed/camp_fire_observations.json
PYTHONPATH=src python3 -m wildfire.cli gate --detections data/processed/camp_fire_observations.json
PYTHONPATH=src python3 -m wildfire.cli infer --detections data/processed/camp_fire_observations.json --weather data/raw/camp_fire_weather.json --output artifacts/camp_fire_blind_model.json
```
