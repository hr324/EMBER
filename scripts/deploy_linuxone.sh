#!/usr/bin/env bash
# Run on IBM LinuxONE via SSH after copying this repository and data snapshot.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 --version
uname -m
python3 -m venv .venv
source .venv/bin/activate
# Minimal inference and dashboard use only the Python 3.12 standard library.
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
: "${FIRE_DATA:?Set FIRE_DATA to canonical FIRMS CSV or JSON snapshot}"
CMD=(python3 scripts/serve_stdlib.py --dataset "$FIRE_DATA" --host "${FIRE_HOST:-127.0.0.1}" --port "${FIRE_PORT:-8000}")
if [[ -n "${FIRE_WEATHER:-}" ]]; then CMD+=(--weather "$FIRE_WEATHER"); fi
if [[ -n "${FIRE_COVARIATES:-}" ]]; then CMD+=(--covariates "$FIRE_COVARIATES"); fi
if [[ -n "${FIRE_POWERLINES:-}" ]]; then CMD+=(--powerlines "$FIRE_POWERLINES"); fi
if [[ -n "${FIRE_LIGHTNING:-}" ]]; then CMD+=(--lightning "$FIRE_LIGHTNING"); fi
if [[ -n "${FIRE_PERIMETER:-}" ]]; then CMD+=(--perimeter "$FIRE_PERIMETER"); fi
if [[ "${FIRE_MODE:-}" == 'synthetic' ]]; then CMD+=(--demo); fi
exec "${CMD[@]}"
