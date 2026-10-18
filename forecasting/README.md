# EMBER — weekly new-ignition occurrence forecast

A real-data, retrospective backtest of a prospective wildfire occurrence forecast.
For every 25 km cell in Northern California and every Monday, the model ranks how
likely the cell is to have **at least one newly reported wildfire in the next 7
days**, using only information available before that Monday.

This is separate from EMBER's origin-reconstruction code in `src/wildfire/`,
which it does not import or modify.

## What exactly is predicted

| | |
|---|---|
| Unit | one 25 km × 25 km cell (EPSG:3310 California Albers) × one Monday issue date |
| Region | 39.0–41.0 °N, 122.8–120.8 °W, covered by an 8 × 10 lattice (80 cells; includes Butte County) |
| Label | 1 if ≥ 1 FPA-FOD fire has `discovery_date` in [issue, issue + 6 days]; 0 = **no reported fire** (not proof of none) |
| Weather inputs | trailing 7/14/30/90-day windows ending at **issue − 7 days** |
| Fire-history inputs | FPA-FOD discoveries strictly **before** the issue date |
| Never used as inputs | fire size, cause, containment, anything in the forecast window |
| Splits (by issue date) | train 2015–2020 · validation 2021–2022 · **frozen holdout 2023–2024** |
| Output | relative **risk score** for ranking cells (not a calibrated probability) |

## Reproduce

Python 3.12+, `numpy`, `pandas`, `scikit-learn` (already standard in most installs).
No paid services; both sources are free public endpoints.

```bash
make forecast          # download → labels → features → models → map → provenance → tests
make forecast-serve    # http://127.0.0.1:8010/forecast  (stdlib only)
```

Or step by step: `python3 -m forecasting.fetch_fires`, `fetch_weather`, `labels`,
`features`, `models`, `export`, `provenance`. Downloads are cached
(`data/raw/forecasting/`, `data/cache/forecasting/`, gitignored), so reruns are offline.
The weather download takes ~10–15 min on the free tier and waits politely if the
hourly quota is reached.

Tests: `python3 -m unittest tests.test_occurrence_forecast` (uses verbatim real
extracts in `forecasting/samples/`).

## Data sources

* **USFS FPA-FOD 7th edition** fire occurrence, ArcGIS MapServer layer 0
  (<https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_FireOccurrenceCurrentEdition_01/MapServer/0>);
  archive citation: Short, K. C., *Spatial wildfire occurrence data for the United States*,
  7th edition (fires 1992–2024), USDA Forest Service Research Data Archive,
  <https://doi.org/10.2737/RDS-2013-0009.7>.
  `discovery_date`'s UTC calendar date matched `discovery_doy` for all records, so it is
  used directly as a local calendar date.
* **Open-Meteo Historical Weather API** (<https://open-meteo.com/en/docs/historical-weather-api>),
  reanalysis from the ERA5 / ERA5-Land family, daily aggregates in America/Los_Angeles.
  Variables: max/mean temperature, precipitation, mean/min relative humidity,
  max wind speed, max vapour-pressure deficit, reference evapotranspiration,
  0–7 cm soil moisture. Weather data © Open-Meteo, CC BY 4.0; ERA5 © ECMWF / Copernicus.

Full query parameters, page hashes, weather points and derived-file hashes are in
`outputs/provenance.json`.

## Models (ablation)

| id | model | inputs |
|---|---|---|
| A | climatology | smoothed cell × week-of-year rate from training years (±2 weeks, shrunk to regional season × cell rate) |
| B | logistic | season harmonics + cell one-hot |
| C | logistic | B + lagged weather |
| D0 | gradient boosting | season + cell centroid + climatology (no weather): nonlinear control |
| D | gradient boosting | D0 + lagged weather |
| E0 | gradient boosting | D0 + prior fire counts in cell / neighbours (no weather) |
| E | gradient boosting | E0 + lagged weather |

Each learned model tries 3 configurations, all fit on 2015–2020, and keeps the one
with the best **validation** top-10% capture. The holdout is scored once. The
climatology feature given to D/E training rows is leave-one-year-out, so it never
contains the row's own label.

**Primary metric**: for each week, the share of that week's reported fires that fall in
the model's top 10% of cells (8 of 80). Weekly captures are summed over all holdout
weeks. Ties at the cut-off are shared fractionally. Random ranking scores ~10%.
Secondary: top-5/20%, PR-AUC, ROC-AUC, Brier. Uncertainty: calendar-month block
bootstrap of the difference between two models on the same weeks.

## Results (holdout 2023–2024, scored once)

The holdout has 104 weeks, 8,320 cell-weeks and 2,569 reported fires. 1,369 cell-weeks (16.5%) had at least one fire.

| model | top-5% | **top-10%** | top-20% | PR-AUC | ROC-AUC | Brier |
|---|---|---|---|---|---|---|
| A climatology | 0.296 | **0.456** | 0.657 | 0.615 | 0.857 | 0.0946 |
| B logistic season+cell | 0.299 | **0.464** | 0.673 | 0.619 | 0.864 | 0.0943 |
| C logistic + weather | 0.299 | **0.463** | 0.668 | 0.616 | 0.864 | 0.0944 |
| D0 GBM season+location | 0.301 | **0.450** | 0.655 | 0.593 | 0.849 | 0.0972 |
| D GBM + weather | 0.288 | **0.445** | 0.655 | 0.593 | 0.851 | 0.0972 |
| E0 GBM + fire history | 0.296 | **0.462** | 0.656 | 0.615 | 0.861 | 0.0939 |
| E GBM + history + weather ★ | 0.290 | **0.468** | 0.660 | 0.616 | 0.862 | 0.0935 |

★ Among the models that use weather, E had the best validation (2021–2022) top-10% capture: 0.441, against 0.433 for C and 0.427 for D. That makes it the headline model. The decision was made before the holdout was scored.

**Plain-language result.** Every model puts about 45–47% of the next week's reported
fires into the 10% of cells it ranks highest, about 4.5× better than random.
**Nearly all of that comes from where and when fires usually happen.** Adding lagged
reanalysis weather did **not** produce a statistically credible improvement on the
unseen 2023–2024 period. Differences in top-10% capture, using a calendar-month block bootstrap on the same weeks:

| comparison | Δ capture | 95% CI |
|---|---|---|
| C − B (weather, linear) | −0.1 pt | [−0.4, +0.1] |
| D − D0 (weather, nonlinear) | −0.6 pt | [−2.5, +1.1] |
| E − E0 (weather on top of fire history) | +0.5 pt | [−0.5, +1.3] |
| E − A (headline vs climatology) | +1.1 pt | [−0.4, +3.0] |

So the stretch goal, "environmental signals improve prediction", is **not supported** by this
backtest. Possible reasons, untested: weather lagged by 7 days loses the short-term
dryness/wind signal; ~50 km weather sampling; ignitions are dominated by human activity
patterns that location and season already encode.

The scores are reasonably calibrated in the upper deciles. In the top tenth of cell-weeks, model E averaged 0.72
and 70% of those cell-weeks had a reported fire (`holdout_reliability` in `metrics.json`). They are still presented as risk scores.

**Demo week (22–28 July 2024, issue 22 July).** 55 fires were reported in the window.
The headline model's top 8 cells contained 18 of them; the climatology's contained 19.
**The Park Fire's own cell (`c04_03`) was ranked 62/80 by model E and 50/80 by
climatology, so neither model flagged it.** Present it as an honest example of the
forecast's limits, not as a hit.

Development note: the no-weather models (A, B, D0, E0) were run once on the holdout during a
pipeline dry run before the weather download finished. No setting was changed afterwards.
Configurations are chosen only on 2021–2022.

## Outputs (`forecasting/outputs/`)

* `metrics.json` — every model × split, selection trials, holdout significance tests, reliability tables, limitations
* `holdout_predictions.csv` — `forecast_date, horizon_days, cell_id, centroid_lat, centroid_lon, risk_score, observed_fire, event_count, model_name, model_version`
* `forecast_map.geojson` — cell polygons with headline-model and baseline scores/ranks for the demo week (no outcomes)
* `observed_events.geojson` — fires actually reported in that window (reveal / evaluation layer only)
* `forecast_map.html` — standalone map: step through all 104 holdout weeks, switch model, reveal outcomes
* `provenance.json` — sources, queries, hashes, cut-offs, assumptions

**Demo week rule**, fixed before looking at any score for it: the holdout week containing the
**2024 Park Fire** discovery (FPA-FOD: 24 July 2024, Butte County, cell `c04_03`), i.e.
issue date Monday 22 July 2024.

## Limitations

* FPA-FOD is a compiled record of *reported* fires; omissions and coordinate imprecision exist, and discovery dates are date-only.
* Reanalysis weather is a retrospective estimate, not the forecast that existed on the issue date. The 7-day lag reduces but does not remove that advantage.
* Weather is sampled once per ~50 km block (2 × 2 cells) to stay inside Open-Meteo's free daily quota; cells in a block share weather.
* Fire-history features assume that discoveries before the issue date were known by then. Real reporting latency can be longer.
* One region, temporal holdout only. Neighbouring cells are spatially correlated, so independent evidence is smaller than the row count suggests.
* Equal-area cells differ in burnable land, population and reporting effort, so lift is not "equal opportunity".
* Not an operational warning system.

## IBM LinuxONE

`forecasting/serve.py` and `forecasting/grid.py` are standard-library only, so they run
on s390x without native wheels. **No s390x execution has been verified yet.** To verify, run
`uname -m` and `curl 'http://127.0.0.1:8010/api/forecast/health'` on the VM and record
both outputs.
