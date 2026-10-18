# EMBER overnight results — 18 October 2026

Branch `rayan` · code in `forecasting/` · every number below is read from saved files in this folder.

## Headline (for the pitch)

> **What EMBER predicted:** At the start of each week, EMBER selected the 8 of 80 Northern California areas (~25 km each) where it expected a new wildfire within seven days.
>
> **Success rate:** In 2025, **235 of 408 alerts** were followed by at least one newly reported wildfire: **57.6% correct fire alerts**.
>
> **Fair baseline:** With the same 8 alerts each week, a simple location-and-season model was **54.7% correct** (223 of 408). EMBER's difference was **+2.9 percentage points**, 95% interval **[−0.5, +6.0]**. **No measurable advantage is established.**
>
> **How many fires it caught:** EMBER's 8 weekly areas contained **627 of 1,563** reported 2025 ignitions (**40.1%**) from 10% of the map. Random picks would get about 10%.
>
> **Validation:** trained on 2015–2020, tuned on 2021–2022. Original test 2023–2024 (now used). Then 2025 as a frozen, pre-registered test on a different fire database (NIFC WFIGS), with no retraining.
>
> **What's new tonight:** six families of additional real-world signals were tested. **None gave a measurable improvement.** The best, NWS Red Flag Warnings, tied its matched control on 2025.
>
> **Limits:** ~25 km areas, a one-week horizon, *reported* fires only (records miss fires), not an exact ignition location or time. Random selection would be right ~19% of the time in 2025.
>
> **Spend:** free public data only. Claude account billing can't be verified from inside the session; the user confirmed a Claude Pro login.

**How to say it in one line:** *"Each week EMBER flags 8 of 80 areas; in 2025, 58% of those alerts were followed by a reported wildfire, three times the 19% rate for a random area. But a simple seasonal map does nearly as well (55%), so most of the skill comes from knowing where and when fires usually happen."*

**Don't say:** "accuracy" (a model predicting no fires anywhere would be 81% "accurate"), "predicts individual fires", or "83%" on its own.

## Where the 2025 number sits

| Test | Alerts | EMBER hit rate | Baseline hit rate (same budget) | Difference (95% CI) |
|---|---|---|---|---|
| 2023–2024 holdout (FPA-FOD labels; used) | 832 | 52.4% (436) | 50.8% (423) | +1.6 pt (top-10% capture +1.1 [−0.4, +3.0]) |
| **2025 frozen test (WFIGS labels)** | **408** | **57.6% (235)** | **54.7% (223)** | **+2.9 pt [−0.5, +6.0]** |

The confusion table for EMBER's 2025 alert rule is TP 235, FP 173, FN 555, TN 3,117. **The alerts cover 29.8% of all cell-weeks that had a fire.** Most fire cell-weeks fall outside the top 8, because fires are spread over many cells.

## What was tried overnight (all chosen on 2021–2022 validation only)

Full log: [experiments.md](experiments.md).

| # | Signal family | Source | Result on validation (top-8 hit rate vs matched control) | Decision |
|---|---|---|---|---|
| 1 | Better-timed weather | Open-Meteo reanalysis | Weather ending the day before: −0.8 pt. **Even the actual weather of the forecast week (a cheating ceiling): only +1.2 pt [−0.2, +2.7]** | Rejected; issued forecasts deprioritised because their maximum gain is too small to detect |
| 2 | Recent activity anomalies | Fire records (region-wide 7/30-day counts) | −0.1 pt [−1.0, +0.8] (small PR-AUC gain only) | Rejected |
| 3 | Holiday weeks (4 July, Memorial Day, Labor Day, Thanksgiving) | Calendar rules | +0.1 pt [−0.6, +0.7] | Rejected |
| 4 | Climatology + small dynamic adjustment | All of the above + 5, 6 | +0.0 pt [−2.3, +2.6] vs climatology | Rejected |
| 5 | Fuel dryness / fire danger (ERC, burning index, 100/1000-h fuel moisture, 4 km) | gridMET | −0.5 pt; −1.7 pt [−3.0, −0.4] when added to existing weather | Rejected |
| 6 | **Red Flag Warnings / Fire Weather Watches published by Monday 06:00** | NWS via IEM archive, 5 forecast offices | **+0.7 pt [−0.2, +1.6]** (best) | **Carried to 2025:** 55.1%, +0.5 pt vs baseline [−2.5, +3.5]; 0.0 vs its control |
| — | Lightning (GOES GLM) | NOAA | Not attempted: about 4,300 files/day, so years of history would be hundreds of GB | Deferred |
| — | Traffic, campsite bookings, social media | Caltrans PeMS, Recreation.gov, Instagram | Not attempted: accounts or privacy approval needed | Deferred |

**Scientific takeaway:** at this scale (25 km, one week, all causes), the ranking of where fires start is dominated by place and season. Every dynamic signal tested shifts risk in the expected direction (drier heavy fuels and recent nearby fires raise it), but too little to change which 8 cells are flagged. The oracle diagnostic suggests the ceiling for any weather-based improvement here is about +1 point. Bigger gains likely need either a different target (which fires become large: weather and wind should matter far more there) or finer, faster human-activity data.

## Integrity checks

- **Reproducibility:** every reported holdout number recomputes from the saved predictions ([AUDIT.md](AUDIT.md)). Re-scoring from the saved models matches to 5e-7.
- **Timestamps:** all 41,680 training/validation/holdout rows have weather ending exactly 7 days before issue and fire history ending the day before (0 violations). Red Flag inputs count only products published by Monday 06:00 Pacific. gridMET uses a 3-day lag.
- **Pre-registration:** both 2025 tests had their rules committed before any score ([PREREG_2025.md](../PREREG_2025.md), [PREREG_2025_v2.md](../PREREG_2025_v2.md)). One code crash before the first 2025 run is logged there; no rule changed.
- **The 2025 caveat:** 2025 was scored once for the original model before tonight's candidate was chosen. The candidate was chosen on 2021–2022 only.
- **Data consistency:** WFIGS and FPA-FOD agree closely in 2022–2024 (kappa 0.90–0.96). Switching sources moves the 2023–2024 score by about 1 point.

## Live forecast (a truly untouched test)

A real forecast for **Monday 19 October 2026** (week of 19–25 Oct) was issued at 03:46 UTC on 18 October 2026 (recorded in the GeoJSON as `issued_utc`), before any outcome existed. It's in [live/forecast_2026-10-19.csv](live/forecast_2026-10-19.csv) and `.geojson`, with EMBER, baseline and candidate alerts. Score it once reports settle (about two weeks):

```bash
python3 -m forecasting.fetch_wfigs --refresh
python3 -m forecasting.predict --date 2026-10-19 --score-outcomes
```

## Files

| File | What |
|---|---|
| `headline_metrics.json` | The numbers above, machine-readable |
| `experiments.md` / `.json` | Every overnight experiment: hypothesis, source, timing, coverage, result, decision |
| `candidate_2025.json`, `candidate_2025_predictions.csv` | Pre-registered 2025 test, per cell-week predictions for A, E0, E, candidate |
| `external_test.json`, `EXTERNAL_TEST.md`, `external_predictions_*.csv` | First frozen 2025 / 2026 test and WFIGS reconciliation |
| `AUDIT.md`, `audit.json`, `all_predictions.csv.gz` | Equal-budget audit, confusion matrices, timestamp audit, all predictions |
| `forecast_map_2025.html` | Map: step through 2025 weeks, switch EMBER and baseline, reveal reported fires |
| `forecast_map.html` | The same for the 2023–2024 holdout (Park Fire week) |
| `models.pkl`, `candidate_v2.pkl` | Fitted models (scikit-learn 1.9) |
| `live/` | Live forecasts |

## Run it

```bash
make forecast                                     # rebuild original pipeline + audit (cached data)
python3 -m forecasting.experiments <family>       # weather_timing | activity | holidays | gridmet | redflag | offset
python3 -m forecasting.candidate fit|test         # overnight candidate (test already run once; don't rerun for a new claim)
python3 -m forecasting.predict --date YYYY-MM-DD  # forecast any Monday from live sources
make forecast-serve                               # map + read-only API on http://127.0.0.1:8010
```
