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

## Skill beyond "usual places in summer"

Full tables: [SURPRISE_EVAL.md](SURPRISE_EVAL.md). Definitions were committed before computing.
- **Expectedness:** each cell-week is judged against its frozen 2015–2020 climatology rate.
- **What earns credit:** only correct departures from that rate. Recognising usual hotspots earns none.

| Measure (EMBER vs seasonal baseline) | 2025 | 2023–2024 |
|---|---|---|
| **Ranking among cell-weeks with the same historical risk** (within-decile ROC-AUC) | 0.670 vs 0.590: **+0.080 [+0.038, +0.125]** | 0.665 vs 0.627: **+0.038 [+0.016, +0.060]** |
| Information gain over climatology (millibits per cell-week) | **+27.7 [+2.2, +56.2]** | +7.1 [−0.6, +15.3] |
| Excess fires per alert beyond climatology's expectation, confident rule | **+0.048 [+0.022, +0.077]** | **+0.026 [+0.002, +0.051]** |
| Truly unexpected fires (climatology < 10%) | 111 fire cell-weeks; EMBER alerts there rarely (≤ 13 alerts, 4–5 caught; the baseline can't alert there at all) | 171; EMBER made 5 alerts there, 2 caught |

**This is the strongest evidence of real forecasting skill in the project, and it replicates in both test periods.**
- **What it shows:** among places and weeks that history rates equally, EMBER is significantly better at telling which will see a fire. Its alerts find more fires than climatology already expected.
- **Why the fixed top-8 metric missed it:** the top 8 are nearly always the same high-climatology hotspots, so the dynamic skill only shows away from them.
- **The honest limit:** fires in places that almost never burn remain essentially unpredicted. Too few alerts land there to judge.

**Pitch line:** *"Even among places and weeks with identical fire history, EMBER can tell which are more likely to burn, a significant edge confirmed on two separate test periods, which a seasonal map cannot do by definition."*

## Live alerts now vary with risk

`python3 -m forecasting.predict` no longer flags a fixed top 8.
- **Rule:** a cell is alerted when its risk clears that model's threshold, chosen on 2021–2022 validation ([alert_thresholds.json](alert_thresholds.json)).
- **Rules available:** the default is `precision70`; `precision50` and `best_f1` are also saved.
- **The 19 Oct 2026 forecast:** re-flagged from its saved scores (scores unchanged; the original top-8 version is in git history). Under the default rule EMBER alerts **6 cells**, the baseline 4 and the candidate 2. Under the broader rules EMBER alerts 15–19.

## Without a fixed number of alerts per week

Full tables: [FLEXIBLE_ALERTS.md](FLEXIBLE_ALERTS.md).
- **Method:** a cell is alerted whenever its risk score clears a threshold, so the number of alerts rises and falls with conditions (EMBER: 0–19 a week in 2025 under the confident rule).
- **Thresholds:** set per model on 2021–2022 only, by three rules fixed in advance:
  - best F1 balance;
  - ≥ 70% hit rate on validation;
  - ≥ 50% hit rate on validation.

**"Confident" rule (aim for ≥ 70% hit rate):**

| | 2025 EMBER | 2025 baseline | 2023–24 EMBER | 2023–24 baseline |
|---|---|---|---|---|
| Alerts | 332 | 220 | 580 | 440 |
| Hit rate | 76.8% | 81.8% | 78.5% | 83.0% |
| Fire cell-weeks caught | **32.3%** | 22.8% | **33.2%** | 26.7% |
| Reported fires in alerted cells | **44.7%** | 34.7% | **50.1%** | 42.7% |
| F1 difference (95% CI) | **+9.8 pt [+6.8, +12.5]** | | **+6.3 pt [+4.1, +9.0]** | |

What this shows:
- **Same setup, more fires caught.** Set up the same way, EMBER makes more alerts and **catches significantly more fires** in both test periods, at a hit rate about 5 points lower. Its overall balance (F1) is significantly better under the confident and broad rules in 2025, and the confident rule in 2023–2024.
- **But not better ranking.** **Given the same total number of alerts**, placed anywhere in the period, EMBER's and the baseline's hit rates match (all CIs include zero). The advantage comes from EMBER raising more alerts when its signals say risk is up, not from picking better cells per alert.
- **It adapts to busier years.** In 2025, a busier year, EMBER's average predicted risk was 18.6% against an actual 19.4%; the static baseline stayed at 16.6%. 2025 ROC-AUC improved **+0.018 [+0.003, +0.036]**, a significant but small gain. PR-AUC and Brier also improved but weren't significant. No threshold-free difference is significant in 2023–2024.

**Pitch line (variable alerts):** *"Set up the same way on past data, EMBER flagged about 50% more areas than a seasonal map in 2025 and caught 42% more of the weeks that had fires (32% vs 23%), with 77% of its alerts followed by a reported fire."*

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
