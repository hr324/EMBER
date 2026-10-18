# EMBER — 1 km spatial resolution and new-detection evaluation

## What the patch changes

- `scripts/gnn_replay.py`: exports top 500 ranked cells, plus a separate ranking of cells that were NOT detected in the current satellite pass; adds comparative average precision and top-K precision/recall for this harder **new-detection** task.
- `frontend/forecast.html`: switch between all future activity and previously-undetected cells; top 10/25/50/100/200/400; outcome evaluation in the selected mode; grouping repeated nearest-place labels.
- `scripts/enrich_population.py`: prioritises newly-undetected forecast candidates when available, without changing the trained GNN or using population as a learned feature.
- Does **not** change graph model architecture or overwrite an existing checkpoint. A genuinely finer 1 km model must be trained separately.

## On IBM LinuxONE

Upload the zip using JupyterLab, then from `~/EMBER-main`:

```bash
python3 -m zipfile -e ~/EMBER_Granularity_Decision_Patch.zip .
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Train and retain a separate 1 km checkpoint, using the existing automatically screened fire list (the previously used 2 km checkpoint is untouched):

```bash
PYTHONPATH=src python3 scripts/gnn_forecast.py train \
  --data data/fire_sequences \
  --approved-list artifacts/auto_screened_fires.txt \
  --test-fire camp_2018 \
  --cell-m 1000 --margin-km 15 --max-cells 16000 \
  --epochs 14 --patience 4 --threads 2 \
  --output artifacts/gnn_1km \
  2>&1 | tee artifacts/gnn_1km_training.log
```

If you see `Killed` or memory errors, stop and revert to 2 km rather than risking the submission. The grid size increases by about 4x at 1 km; some examples may be excluded by the grid-size or future-coverage filters. Compare `dataset` and `split` entries in both model reports to see whether the training examples actually match.

Create the new (historical, not live) replay:

```bash
PYTHONPATH=src python3 scripts/gnn_replay.py \
  --checkpoint artifacts/gnn_1km/gnn_model.pt \
  --firms data/fire_sequences/camp_2018/firms.csv \
  --weather data/fire_sequences/camp_2018/weather.json \
  --name camp_2018 \
  --output frontend/gnn_replay.json
```

Download `frontend/gnn_replay.json` from JupyterLab.

## On Windows

Apply this SAME patch to your existing PowerShell project directory:

```powershell
Expand-Archive "$HOME\Downloads\EMBER_Granularity_Decision_Patch.zip" -DestinationPath . -Force
```

Replace `frontend\gnn_replay.json` with the one downloaded from LinuxONE. Then run population enrichment using your existing downloaded real WorldPop raster (you don't need to download it again):

```powershell
py scripts\enrich_population.py --replay frontend\gnn_replay.json --output frontend\gnn_replay.json --year 2017 --places
```

Launch your existing local server and visit `/forecast.html`, then refresh with Ctrl+Shift+R.

## Interpretation / safeguards

- 1 km x 1 km cells are **finer model decision regions**, not 1 km positional accuracy. VIIRS pixel footprints and observation gaps still limit ground truth.
- “New” means not detected by the satellite on the issue pass. It does not mean the ground was unburned at that time, and later observations are still incomplete.
- Average precision in the **new-only** mode ranks previously-undetected cells only; its values must not be compared numerically to average precision in the **all-cells** mode.
- Future observations are only revealed after pressing the button. Their labels are not features at forecast time.
- Named place rows group a small set of ranked candidate cells by nearest US Census reference point; they are not full town polygons or town population totals.
- Camp Fire has already been inspected repeatedly. These are exploratory comparisons, not a fresh independent estimate of generalisation.
