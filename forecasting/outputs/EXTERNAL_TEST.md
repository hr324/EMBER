# Independent test on the live WFIGS fire feed

Rules fixed in advance in `PREREG_2025.md`. Frozen models from `models.pkl`; nothing refit or tuned. Regenerate with `python3 -m forecasting.external_test compare|shift|test|report`.

## Results

| Test | Weeks | Fires | Fire cell-weeks | Weather model E top-10% | Climatology A top-10% | E - A | 95% CI |
|---|---|---|---|---|---|---|---|
| 2025 primary (2025-01-06 to 2025-12-22) | 51 | 1563 | 790 (19.4%) | **40.1%** | 39.3% | +0.8 pt | [-0.4, +3.1] |
| 2026 to date secondary (2026-01-05 to 2026-09-28) | 39 | 778 | 514 (16.5%) | **38.4%** | 38.2% | +0.3 pt | [-2.8, +3.1] |
| reference: 2023-2024 holdout, same WFIGS labels and history | 104 | 2537 | 1396 (16.8%) | 45.3% | 44.9% | +0.4 pt | [-1.1, +2.2] |

Random ranking would capture about 10%.

### All models

| Model | 2025 top-5% | 2025 top-10% | 2025 top-20% | 2025 PR-AUC | 2026 top-10% | 2026 PR-AUC |
|---|---|---|---|---|---|---|
| A_climatology | 24.8% | 39.3% | 57.3% | 0.613 | 38.2% | 0.455 |
| B_logit_season_loc | 25.0% | 38.2% | 57.6% | 0.610 | 38.7% | 0.461 |
| C_logit_weather | 25.0% | 38.5% | 58.6% | 0.615 | 39.1% | 0.478 |
| D0_gbm_season_loc | 24.7% | 38.1% | 55.9% | 0.576 | 37.3% | 0.452 |
| D_gbm_weather | 24.7% | 39.2% | 55.8% | 0.611 | 33.7% | 0.435 |
| E0_gbm_history | 25.1% | 38.9% | 60.0% | 0.609 | 40.2% | 0.473 |
| E_gbm_history_weather | 24.3% | 40.1% | 59.2% | 0.629 | 38.4% | 0.475 |

### Equal budget (same number of most-confident calls, 5.4% of cell-weeks)

| Test | Calls | E hit rate | A hit rate | E - A | 95% CI |
|---|---|---|---|---|---|
| 2025 primary | 220 | 83.2% | 81.8% | +1.4 pt | [-2.3, +6.2] |
| 2026 to date secondary | 168 | 64.3% | 66.7% | -2.4 pt | [-5.7, +6.0] |

### By season, 2025 (top-10% capture)

| Season | Fires | E | A |
|---|---|---|---|
| Winter (Dec-Feb) | 90 | 48.9% | 36.7% |
| Spring (Mar-May) | 280 | 47.1% | 48.9% |
| Summer (Jun-Aug) | 907 | 36.6% | 36.2% |
| Autumn (Sep-Nov) | 286 | 41.6% | 40.6% |

## Data-quality checks (run before scoring 2025)

### WFIGS vs FPA-FOD, cell-week labels

| Year | FPA-FOD fires | WFIGS fires | Label agreement | Kappa | FPA fire cell-weeks also in WFIGS |
|---|---|---|---|---|---|
| 2015 | 1290 | 417 | 85.9% | 0.40 | 31.8% |
| 2016 | 974 | 235 | 89.3% | 0.40 | 29.5% |
| 2017 | 1172 | 480 | 88.9% | 0.49 | 40.6% |
| 2018 | 1173 | 346 | 87.6% | 0.43 | 33.7% |
| 2019 | 722 | 643 | 89.2% | 0.47 | 48.4% |
| 2020 | 1424 | 1375 | 84.5% | 0.49 | 59.8% |
| 2021 | 776 | 1325 | 88.6% | 0.56 | 74.4% |
| 2022 | 1283 | 1553 | 96.9% | 0.90 | 99.3% |
| 2023 | 1335 | 1274 | 98.8% | 0.96 | 96.6% |
| 2024 | 1235 | 1265 | 98.4% | 0.94 | 96.8% |

WFIGS is close to FPA-FOD from 2022 (kappa 0.90-0.96) and sparse before 2020. Of 6,053 FPA-FOD records in 2020-2024, 74.4% have a WFIGS record within 2 km and 3 days; 97.1% of those matches fall on the same Pacific calendar day.

### Effect of switching source (2023-2024, frozen models)

| Labels | Fire history | E top-10% | A top-10% | E - A |
|---|---|---|---|---|
| FPA | FPA | 46.8% | 45.6% | +1.1 pt |
| FPA | WFIGS | 46.2% | 45.6% | +0.6 pt |
| WFIGS | FPA | 45.5% | 44.9% | +0.6 pt |
| WFIGS | WFIGS | 45.3% | 44.9% | +0.4 pt |

The first row reproduces the original holdout exactly. Switching to WFIGS lowers capture by about 1-1.5 points for E and 0.7 for A, so a 2025 drop larger than that is real, not a source artefact.
