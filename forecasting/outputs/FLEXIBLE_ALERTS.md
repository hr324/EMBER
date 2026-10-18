# Threshold-based alerts (no fixed number per week)

Every cell-week whose risk score clears a threshold is an alert, so alert counts rise and fall with the season and conditions. Thresholds were chosen per model on **2021-2022 validation only**, by rules fixed before any test number was computed. 2023-2024 and 2025 were both used before; these are additional readings of frozen models. CIs: calendar-month block bootstrap. Regenerate: `python3 -m forecasting.flexible_alerts`.

## Thresholds (from validation)

| Model | best F1 | precision >= 70% | precision >= 50% |
|---|---|---|---|
| Seasonal baseline (A) | 0.299 | 0.601 | 0.386 |
| EMBER (E) | 0.275 | 0.606 | 0.335 |
| Overnight candidate (E0+redflag) | 0.254 | 0.600 | 0.331 |

## test 2025 (WFIGS)

4,080 cell-weeks, 790 with a reported fire (19.4%).

### Best balance (max F1)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 749 | 0-13-33 | 9 of 51 | **57.5%** | 54.6% | 64.9% | 0.560 |
| EMBER (E) | 958 | 0-14-52 | 4 of 51 | **52.2%** | 63.3% | 73.5% | 0.572 |
| Overnight candidate (E0+redflag) | 1117 | 0-18-65 | 4 of 51 | **47.6%** | 67.3% | 76.1% | 0.558 |

| Versus baseline | Difference | 95% CI |
|---|---|---|
| EMBER (E), precision | -5.3 pt | [-10.7, +0.6] |
| EMBER (E), recall | +8.7 pt | [+4.6, +13.4] |
| EMBER (E), f1 | +1.2 pt | [-2.8, +6.3] |
| Overnight candidate (E0+redflag), precision | -9.9 pt | [-16.2, -5.3] |
| Overnight candidate (E0+redflag), recall | +12.8 pt | [+8.7, +16.9] |
| Overnight candidate (E0+redflag), f1 | -0.2 pt | [-4.4, +3.7] |

### Confident (>= 70% on validation)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 220 | 0-4-13 | 21 of 51 | **81.8%** | 22.8% | 34.7% | 0.356 |
| EMBER (E) | 332 | 0-5-19 | 20 of 51 | **76.8%** | 32.3% | 44.7% | 0.455 |
| Overnight candidate (E0+redflag) | 336 | 0-5-21 | 18 of 51 | **73.8%** | 31.4% | 43.7% | 0.441 |

| Versus baseline | Difference | 95% CI |
|---|---|---|
| EMBER (E), precision | -5.0 pt | [-7.6, -2.5] |
| EMBER (E), recall | +9.5 pt | [+6.4, +11.8] |
| EMBER (E), f1 | +9.8 pt | [+6.8, +12.5] |
| Overnight candidate (E0+redflag), precision | -8.0 pt | [-14.3, -4.4] |
| Overnight candidate (E0+redflag), recall | +8.6 pt | [+4.8, +11.3] |
| Overnight candidate (E0+redflag), f1 | +8.4 pt | [+4.3, +12.0] |

### Broad (>= 50% on validation)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 559 | 0-9-28 | 17 of 51 | **64.6%** | 45.7% | 57.6% | 0.535 |
| EMBER (E) | 782 | 0-12-43 | 7 of 51 | **57.9%** | 57.3% | 68.3% | 0.576 |
| Overnight candidate (E0+redflag) | 826 | 0-15-46 | 4 of 51 | **54.8%** | 57.3% | 68.5% | 0.561 |

| Versus baseline | Difference | 95% CI |
|---|---|---|
| EMBER (E), precision | -6.7 pt | [-11.4, -2.9] |
| EMBER (E), recall | +11.6 pt | [+9.8, +13.7] |
| EMBER (E), f1 | +4.1 pt | [+1.4, +7.6] |
| Overnight candidate (E0+redflag), precision | -9.7 pt | [-18.1, -5.4] |
| Overnight candidate (E0+redflag), recall | +11.6 pt | [+9.1, +14.9] |
| Overnight candidate (E0+redflag), f1 | +2.5 pt | [-1.0, +6.5] |

### Same total number of alerts, placed anywhere in the period

| Alerts (= EMBER under rule) | Share of cell-weeks | Model | Its hit rate | Baseline hit rate | Difference | 95% CI |
|---|---|---|---|---|---|---|
| 958 (best_f1) | 23.5% | EMBER (E) | 52.2% | 51.8% | +0.4 pt | [-1.6, +4.9] |
| 958 (best_f1) | 23.5% | Overnight candidate (E0+redflag) | 50.9% | 51.8% | -0.8 pt | [-2.9, +2.9] |
| 332 (precision70) | 8.1% | EMBER (E) | 76.8% | 73.8% | +3.0 pt | [-2.4, +6.2] |
| 332 (precision70) | 8.1% | Overnight candidate (E0+redflag) | 73.8% | 73.8% | +0.0 pt | [-6.6, +2.7] |
| 782 (precision50) | 19.2% | EMBER (E) | 57.9% | 56.4% | +1.5 pt | [-1.8, +5.3] |
| 782 (precision50) | 19.2% | Overnight candidate (E0+redflag) | 56.3% | 56.4% | -0.1 pt | [-3.3, +3.2] |

### Threshold-free

| Model | PR-AUC | ROC-AUC | Brier | Mean risk vs observed rate |
|---|---|---|---|---|
| Seasonal baseline (A) | 0.613 | 0.836 | 0.1123 | 16.6% vs 19.4% |
| EMBER (E) | 0.629 | 0.854 | 0.1076 | 18.6% vs 19.4% |
| Overnight candidate (E0+redflag) | 0.609 | 0.843 | 0.1119 | 19.6% vs 19.4% |

| Versus baseline | PR-AUC (higher better) | ROC-AUC (higher better) | Brier (lower better) |
|---|---|---|---|
| EMBER (E) | +0.0165 [-0.0091, +0.0484] | +0.0177 [+0.0026, +0.0359] | -0.0046 [-0.0099, +0.0008] |
| Overnight candidate (E0+redflag) | -0.0041 [-0.0338, +0.0213] | +0.0062 [-0.0105, +0.0253] | -0.0004 [-0.0059, +0.0061] |

## test 2023-2024 (FPA-FOD)

8,320 cell-weeks, 1,369 with a reported fire (16.4%).

### Best balance (max F1)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 1498 | 0-13-33 | 20 of 104 | **54.0%** | 59.1% | 73.0% | 0.564 |
| EMBER (E) | 1605 | 0-14-47 | 18 of 104 | **52.9%** | 62.0% | 74.7% | 0.571 |
| Overnight candidate (E0+redflag) | 1789 | 0-16-59 | 18 of 104 | **49.4%** | 64.6% | 76.2% | 0.560 |

| Versus baseline | Difference | 95% CI |
|---|---|---|
| EMBER (E), precision | -1.1 pt | [-2.9, +0.8] |
| EMBER (E), recall | +2.9 pt | [+0.9, +5.5] |
| EMBER (E), f1 | +0.7 pt | [-0.4, +2.0] |
| Overnight candidate (E0+redflag), precision | -4.6 pt | [-6.5, -2.2] |
| Overnight candidate (E0+redflag), recall | +5.5 pt | [+3.5, +7.9] |
| Overnight candidate (E0+redflag), f1 | -0.5 pt | [-2.1, +1.7] |

### Confident (>= 70% on validation)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 440 | 0-3-13 | 44 of 104 | **83.0%** | 26.7% | 42.7% | 0.404 |
| EMBER (E) | 580 | 0-4-17 | 41 of 104 | **78.5%** | 33.2% | 50.1% | 0.467 |
| Overnight candidate (E0+redflag) | 566 | 0-4-16 | 42 of 104 | **79.1%** | 32.7% | 49.1% | 0.463 |

| Versus baseline | Difference | 95% CI |
|---|---|---|
| EMBER (E), precision | -4.5 pt | [-7.0, -2.1] |
| EMBER (E), recall | +6.6 pt | [+4.6, +8.8] |
| EMBER (E), f1 | +6.3 pt | [+4.1, +9.0] |
| Overnight candidate (E0+redflag), precision | -3.8 pt | [-6.2, -1.4] |
| Overnight candidate (E0+redflag), recall | +6.1 pt | [+4.5, +7.6] |
| Overnight candidate (E0+redflag), f1 | +5.9 pt | [+4.3, +7.8] |

### Broad (>= 50% on validation)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 1118 | 0-9-28 | 36 of 104 | **62.6%** | 51.1% | 66.2% | 0.563 |
| EMBER (E) | 1293 | 0-13-35 | 25 of 104 | **58.7%** | 55.4% | 69.2% | 0.570 |
| Overnight candidate (E0+redflag) | 1316 | 0-12-39 | 21 of 104 | **58.4%** | 56.2% | 70.3% | 0.573 |

| Versus baseline | Difference | 95% CI |
|---|---|---|
| EMBER (E), precision | -3.9 pt | [-6.7, -1.2] |
| EMBER (E), recall | +4.3 pt | [+1.9, +7.0] |
| EMBER (E), f1 | +0.7 pt | [-0.7, +2.4] |
| Overnight candidate (E0+redflag), precision | -4.2 pt | [-7.0, -1.1] |
| Overnight candidate (E0+redflag), recall | +5.0 pt | [+2.5, +8.0] |
| Overnight candidate (E0+redflag), f1 | +1.0 pt | [-0.6, +3.0] |

### Same total number of alerts, placed anywhere in the period

| Alerts (= EMBER under rule) | Share of cell-weeks | Model | Its hit rate | Baseline hit rate | Difference | 95% CI |
|---|---|---|---|---|---|---|
| 1605 (best_f1) | 19.3% | EMBER (E) | 52.9% | 52.1% | +0.8 pt | [-1.0, +1.6] |
| 1605 (best_f1) | 19.3% | Overnight candidate (E0+redflag) | 53.0% | 52.1% | +0.8 pt | [-1.3, +2.2] |
| 580 (precision70) | 7.0% | EMBER (E) | 78.5% | 78.8% | -0.3 pt | [-2.2, +3.1] |
| 580 (precision70) | 7.0% | Overnight candidate (E0+redflag) | 78.6% | 78.8% | -0.2 pt | [-1.9, +2.8] |
| 1293 (precision50) | 15.5% | EMBER (E) | 58.7% | 57.7% | +1.0 pt | [-1.0, +2.3] |
| 1293 (precision50) | 15.5% | Overnight candidate (E0+redflag) | 58.9% | 57.7% | +1.2 pt | [-1.0, +2.8] |

### Threshold-free

| Model | PR-AUC | ROC-AUC | Brier | Mean risk vs observed rate |
|---|---|---|---|---|
| Seasonal baseline (A) | 0.615 | 0.857 | 0.0945 | 16.3% vs 16.4% |
| EMBER (E) | 0.616 | 0.862 | 0.0935 | 16.5% vs 16.4% |
| Overnight candidate (E0+redflag) | 0.615 | 0.862 | 0.0935 | 16.7% vs 16.4% |

| Versus baseline | PR-AUC (higher better) | ROC-AUC (higher better) | Brier (lower better) |
|---|---|---|---|
| EMBER (E) | +0.0011 [-0.0112, +0.0137] | +0.0052 [-0.0015, +0.0124] | -0.0011 [-0.0024, +0.0002] |
| Overnight candidate (E0+redflag) | -0.0000 [-0.0130, +0.0163] | +0.0051 [-0.0024, +0.0125] | -0.0011 [-0.0030, +0.0008] |

## validation 2021-2022

8,320 cell-weeks, 1,264 with a reported fire (15.2%).

### Best balance (max F1)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 1498 | 0-13-33 | 20 of 104 | **44.9%** | 53.2% | 63.2% | 0.487 |
| EMBER (E) | 1571 | 0-15-36 | 19 of 104 | **45.8%** | 56.9% | 68.0% | 0.507 |
| Overnight candidate (E0+redflag) | 1719 | 0-14-52 | 22 of 104 | **43.8%** | 59.5% | 69.1% | 0.504 |

### Confident (>= 70% on validation)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 440 | 0-3-13 | 44 of 104 | **70.0%** | 24.4% | 36.5% | 0.361 |
| EMBER (E) | 488 | 0-4-14 | 38 of 104 | **70.1%** | 27.1% | 40.7% | 0.390 |
| Overnight candidate (E0+redflag) | 478 | 0-3-17 | 39 of 104 | **70.1%** | 26.5% | 39.9% | 0.385 |

### Broad (>= 50% on validation)

| Model | Alerts | Alerts/week (min-median-max) | Weeks with no alert | Hit rate | Fire cell-weeks caught | Fires caught | F1 |
|---|---|---|---|---|---|---|---|
| Seasonal baseline (A) | 1118 | 0-9-28 | 36 of 104 | **50.0%** | 44.2% | 55.3% | 0.469 |
| EMBER (E) | 1236 | 0-12-32 | 25 of 104 | **50.0%** | 48.9% | 60.9% | 0.494 |
| Overnight candidate (E0+redflag) | 1256 | 0-10-33 | 24 of 104 | **50.0%** | 49.7% | 61.4% | 0.498 |

### Threshold-free

| Model | PR-AUC | ROC-AUC | Brier | Mean risk vs observed rate |
|---|---|---|---|---|
| Seasonal baseline (A) | 0.500 | 0.810 | 0.1022 | 16.3% vs 15.2% |
| EMBER (E) | 0.521 | 0.833 | 0.0985 | 15.9% vs 15.2% |
| Overnight candidate (E0+redflag) | 0.519 | 0.831 | 0.0989 | 15.8% vs 15.2% |
