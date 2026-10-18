# EMBER forecast audit

Generated 2026-10-18T03:09:40+00:00 by `python3 -m forecasting.evaluate`. Reads saved predictions and models only; nothing was retrained or tuned.
Holdout: 2023-2024, 104 weeks, 8320 cell-weeks, 1369 with a reported fire (16.5%).

## 1. Reproducibility

- Holdout metrics recomputed from `holdout_predictions.csv`: largest difference from `metrics.json` = 0.000000 (rounding only).
- All splits re-scored from `models.pkl`: largest difference from saved holdout scores = 5.00e-07.
- Prediction-level file for every split and model: `all_predictions.csv.gz` (291,760 rows).

## 2. Equal-budget comparison

Each model gets the same number of most-confident cell-week calls over the whole holdout. CIs: calendar-month block bootstrap.

| Calls (share of cell-weeks) | Weather model E hit rate | Climatology A hit rate | E - A | 95% CI | E share of fire cell-weeks caught | A share |
|---|---|---|---|---|---|---|
| 276 (3.3%) | 87.3% | 88.0% | -0.7 pt | [-4.8, +2.6] | 17.6% | 17.8% |
| 449 (5.4%) | 83.3% | 82.4% | +0.9 pt | [-3.5, +2.4] | 27.3% | 27.0% |
| 786 (9.4%) | 71.9% | 70.9% | +1.0 pt | [-1.8, +3.6] | 41.3% | 40.7% |
| 832 (10.0%) | 70.0% | 69.2% | +0.7 pt | [-1.7, +3.7] | 42.5% | 42.1% |
| 1664 (20.0%) | 51.7% | 51.2% | +0.5 pt | [-1.0, +1.5] | 62.8% | 62.2% |

## 3. By season

| Season | Weeks | Fires | Base rate | E top-10% capture | A top-10% capture | E - A (95% CI) | E top-8 hit rate | Climatology expected for those picks | Excess |
|---|---|---|---|---|---|---|---|---|---|
| Winter (Dec-Feb) | 26 | 74 | 3.2% | 44.6% | 35.1% | +9.5 pt [-5.4, +16.1] | 13.0% | 13.9% | -0.9 pt |
| Spring (Mar-May) | 26 | 457 | 13.0% | 48.6% | 44.6% | +3.9 pt [-2.0, +6.2] | 43.8% | 41.8% | +2.0 pt |
| Summer (Jun-Aug) | 26 | 1393 | 30.5% | 45.2% | 45.4% | -0.1 pt [-1.8, +1.8] | 87.5% | 81.1% | +6.4 pt |
| Autumn (Sep-Nov) | 26 | 645 | 19.1% | 49.0% | 48.1% | +0.9 pt [-2.5, +3.6] | 65.4% | 59.0% | +6.4 pt |

## 4. High-confidence calls (score >= 0.7) versus climatology

| Model | Calls | Hit rate | Climatology expected | Excess | Share in Jun-Sep | Distinct cells | Share from the 10 busiest cells |
|---|---|---|---|---|---|---|---|
| E_gbm_history_weather | 449 | 83.3% | 74.6% | +8.7 pt | 76.8% | 14 | 88.2% |
| A_climatology | 276 | 88.0% | 84.2% | +3.9 pt | 81.9% | 11 | 94.9% |

"Climatology expected" = mean training-period seasonal fire rate (model A score) for the same cell-weeks. Excess near zero means the confident calls mostly identify cells that burn every season.

## 5. Confusion matrices (holdout cell-weeks)

| Rule | Model | Flagged | TP | FP | FN | TN | Precision | Recall | Specificity |
|---|---|---|---|---|---|---|---|---|---|
| top 8 cells per week (10%) | E_gbm_history_weather | 832 | 436 | 396 | 933 | 6555 | 52.4% | 31.9% | 94.3% |
| top 8 cells per week (10%) | A_climatology | 832 | 423 | 409 | 946 | 6542 | 50.8% | 30.9% | 94.1% |
| score >= 0.5 | E_gbm_history_weather | 786 | 565 | 221 | 804 | 6730 | 71.9% | 41.3% | 96.8% |
| score >= 0.5 | A_climatology | 648 | 492 | 156 | 877 | 6795 | 75.9% | 35.9% | 97.8% |
| score >= 0.7 | E_gbm_history_weather | 449 | 374 | 75 | 995 | 6876 | 83.3% | 27.3% | 98.9% |
| score >= 0.7 | A_climatology | 276 | 243 | 33 | 1126 | 6918 | 88.0% | 17.8% | 99.5% |

## 6. Feature timestamp audit

- Rows checked: 41,680 (all splits).
- Issue date minus latest weather day: min 7, max 7 days (required >= 7); violations: 0.
- Issue date minus latest fire-history day: min 1, max 1 (required >= 1); violations: 0.
- Weather windows: trailing 7/14/30/90 days ending at issue_date - 7 (inclusive). History windows: discoveries in [issue_date - N, issue_date - 1], N in 30/90/365.
- Never used as inputs: fire_size, fire_size_class, cause, containment date, any forecast-window data.
