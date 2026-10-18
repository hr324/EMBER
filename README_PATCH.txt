EMBER / CLEAR FORECAST UI PATCH
===============================

Contents (only these existing files are replaced):
  frontend/forecast.html
  scripts/gnn_replay.py

What changes:
- The existing AI and checkpoint are NOT altered, retrained or replaced.
- Map defaults to only the TOP 25 ranked 2km cells, as orange squares.
- Select top 10 / top 25 / top 50 without rerunning the model.
- Future satellite detections are hidden until the presenter clicks Reveal outcome.
- Replay generator exports exact later-detected grid cells, cell-level top-K matches,
  and average precision versus persistence for the CURRENT checkpoint.
- Each step explains what is being shown. Satellite non-detections are not treated
  as proof an area is safe; scores are NOT calibrated probabilities.

1. WINDOWS LAPTOP: OVERWRITE JUST THE TWO FILES

   In your current wildfire-forensics PowerShell directory:

     Expand-Archive "$HOME\Downloads\EMBER_Clear_Forecast_Patch.zip" -DestinationPath . -Force

2. IBM JUPYTERLAB: APPLY THE SAME PATCH THERE AS WELL

   Upload EMBER_Clear_Forecast_Patch.zip using JupyterLab's Upload button.
   If uploaded to your home folder, in the IBM terminal run:

     cd ~/EMBER-main
     python3 -m zipfile -e ~/EMBER_Clear_Forecast_Patch.zip .

   This updates frontend/forecast.html and scripts/gnn_replay.py on IBM.

3. REGENERATE REPLAY FROM YOUR EXISTING IBM-TRAINED CHECKPOINT

   In ~/EMBER-main on LinuxONE:

     PYTHONPATH=src python3 scripts/gnn_replay.py \
       --checkpoint artifacts/gnn/gnn_model.pt \
       --firms data/fire_sequences/camp_2018/firms.csv \
       --weather data/fire_sequences/camp_2018/weather.json \
       --name camp_2018 \
       --output frontend/gnn_replay.json

   It should print 'frames': 6. No need to train again.

4. GET THE UPDATED REPLAY ONTO YOUR WINDOWS LAPTOP

   In IBM JupyterLab, right-click frontend/gnn_replay.json > Download.
   Move it into your Windows folder: wildfire-forensics\frontend\gnn_replay.json
   Overwrite the old replay JSON.

5. REFRESH THE ALREADY-RUNNING WINDOWS DASHBOARD

   Keep using your existing Windows server. Open:
     http://127.0.0.1:8000/forecast.html

   Press Ctrl+Shift+R. If it isn't running:

     py scripts\serve_stdlib.py --dataset data\fire_sequences\camp_2018\firms.csv --weather data\fire_sequences\camp_2018\weather.json

HOW TO DEMO
-----------
1. Begin on Pass 1, with outcome hidden (the default).
2. Explain: turquoise=current detected fire; orange=25 highest-ranked
   future satellite-detection cells. Not all orange cells will be hit.
3. Click Reveal outcome. Red=actual NEXT satellite-detected cells.
4. The side panel shows exact top-25 matches and average precision vs a baseline.
5. Show Pass 3 as an example where the GNN is weaker, then Pass 5 as a stronger case.
6. State clearly that 2 training fires cannot establish operational safety.

VALIDATION
----------
- Updated replay matched the existing held-out evaluation's AP scores for
  all six Camp Fire prediction windows with the same checkpoint.
- All 20 existing Python tests passed.
- Frontend JS syntax and reveal/slide/top-K UI behaviour were checked.
- This is a presentation/visualisation improvement, NOT an accuracy improvement.
