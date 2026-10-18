#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
python3 scripts/make_synthetic.py
python3 -m wildfire.cli evaluate \
  --detections data/synthetic/toy_firms.csv \
  --weather data/synthetic/toy_weather.json \
  --powerlines data/synthetic/toy_powerlines.geojson \
  --lightning data/synthetic/toy_lightning.csv \
  --label data/synthetic/toy_reference.json \
  --output artifacts/synthetic_demo.json
printf '\nOffline demo complete. Serving at http://localhost:8000\n'
python3 scripts/serve_stdlib.py --dataset data/synthetic/toy_firms.csv --weather data/synthetic/toy_weather.json --powerlines data/synthetic/toy_powerlines.geojson --lightning data/synthetic/toy_lightning.csv --demo
