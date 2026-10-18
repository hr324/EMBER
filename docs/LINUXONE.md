# IBM LinuxONE VM runbook (Python 3.12.15)

## No-pip fallback: guaranteed Python stdlib dependencies

The graph engine and `scripts/serve_stdlib.py` import standard-library modules only. The VM must have its Python 3.12.15 interpreter, appropriate CPU/runtime capacity, and SSH access. We have **not** accessed the user's VM; the instructions below are unverified there.

1. Transfer repository and real input snapshots. Do not include your NASA API key, SSH private key or archived evaluation ground truth among model input files.
2. `cd ~/wildfire-forensics && python3 --version && uname -m`. On IBM Z/LinuxONE, expect `s390x`, but record the actual result.
3. `export FIRE_DATA=data/processed/camp_fire_observations.json`. Set `FIRE_WEATHER` to the Open-Meteo JSON and optional `FIRE_COVARIATES` to a precropped CSV.
4. Set `FIRE_POWERLINES`, `FIRE_LIGHTNING`, `FIRE_PERIMETER` only if validated local files exist (GeoJSON context must be under ~6 MB).
5. `bash scripts/deploy_linuxone.sh` (binds localhost by default); from your local machine `ssh -N -L 8000:127.0.0.1:8000 USER@VM`.
6. In another SSH session, call `curl -s http://127.0.0.1:8000/api/health` and `curl -s 'http://127.0.0.1:8000/api/infer?variant=fusion' > artifacts/linuxone_result.json`.
7. Record timestamps, input SHA256, model options, `uname -m`, wall-clock latency (`time curl ...`), screenshots and endpoint output.

**Development tests elsewhere are not proof of executing on LinuxONE.** Only count actual VM calls in the final presentation. Do not claim performance acceleration without measured comparisons.

## Config keys

| Variable | Meaning |
|---|---|
| `FIRE_DATA` | Required NASA standard CSV or canonical JSON |
| `FIRE_WEATHER` | Optional Open-Meteo JSON or canonical CSV |
| `FIRE_COVARIATES` | Optional preprocessed elevation/fuel numeric CSV |
| `FIRE_POWERLINES` | Optional local line GeoJSON (associations only) |
| `FIRE_LIGHTNING` | Optional timed coordinate CSV (associations only) |
| `FIRE_PERIMETER` | Optional historical perimeter GeoJSON (display only) |
| `FIRE_HOST` | Address to bind, default `127.0.0.1` |
| `FIRE_PORT` | Port, default 8000 |
| `FIRE_MODE` | Set `synthetic` for toy fixtures, otherwise historical unverified |

## HTTP routes

- `GET /` : offline-capable local Canvas dashboard
- `GET /api/health` : Python, machine architecture, SHA256, observation coverage
- `GET /api/observations` : canonical time-ordered satellite detections
- `GET /api/context` : optional geometry (presentation only)
- `GET /api/infer?variant=fusion&cell_m=850&margin_km=9&ensemble=true` : **fresh** inference
- `GET /api/evidence` : most recently inferred optional evidence graph

Variants: `satellite` (isotropic), `wind` (wind-aware), `fusion` (wind + available preprocessed elevation/fuel). The API never loads CAL FIRE ground truth.

### Troubleshooting

- **No data, HTTP 503 or process exits:** `FIRE_DATA` wrong / missing; make path relative to repo or absolute.
- **FIRMS raw file has too many out-of-incident hotspots:** use the case ingest filter, inspect early points before ranking; don't use CAL FIRE truth to trim.
- **Grid too large:** use 1200m or 1500m cell setting rather than changing bounding box based on evaluation result.
- **Historical weather missing:** run satellite-only baseline, fetch actual UTC hourly archive or change pilot.
- **TuringDB unavailable on s390x:** use `scripts/export_heterograph.py` to produce portable graph CSV on a compatible separate machine.
- **FastAPI doesn't pip-install due to compiled wheels:** avoid FastAPI and use the dependency-free server; the same inference core runs on both.
- **Browser page cannot be reached:** SSH tunnel binds local port 8000, remote process must be alive; don't expose LinuxONE to the world.
