# Rewarding unexpected fires

Expectedness of a cell-week = its frozen 2015-2020 climatology rate c (how often that cell burned in that week of the year). These measures give **no credit for recognising usual hotspots**; only correct departures from climatology count. Definitions were committed before computing (`surprise_eval.py`). Alert thresholds come from 2021-2022 validation (`alert_thresholds.json`). Both test periods were used before. CIs: calendar-month block bootstrap.

## test 2025 (WFIGS)

4,080 cell-weeks; 790 with a reported fire. Share of fire cell-weeks that were unexpected (c < 5% / 10% / 20%): 7.2% / 14.1% / 31.5%.

### Skill beyond climatology (all cell-weeks)

| Model | Information gain (millibits/cell-week) | Brier skill vs climatology | Ranking within same-risk deciles (ROC-AUC) |
|---|---|---|---|
| Seasonal baseline (A) | +0.0 | +0.0000 | 0.590 |
| EMBER (E) | +27.7 | +0.0412 | 0.670 |
| Overnight candidate (E0+redflag) | +12.1 | +0.0034 | 0.637 |

| Versus baseline | Information gain 95% CI (millibits) | Within-decile ROC-AUC difference |
|---|---|---|
| EMBER (E) | [+2.2, +56.2] | +0.080 [+0.038, +0.125] |
| Overnight candidate (E0+redflag) | [-16.7, +41.1] | +0.047 [+0.011, +0.090] |

### Unexpected fires (climatology < 10%) caught by validation-threshold alerts

Stratum: 2,149 cell-weeks, 5.2% of which had a fire. The baseline's score IS climatology, and all its thresholds exceed 10%, so it cannot alert here by construction; the test for EMBER is whether its alerts in this stratum beat the stratum base rate.

| Rule | Model | Unexpected fire cell-weeks | Caught | Recall | Alerts in that stratum | Their hit rate | Surprise-weighted recall |
|---|---|---|---|---|---|---|---|
| best_f1 | Seasonal baseline (A) | 111 | 0 | 0.0% | 0 | - | 0.0% |
| best_f1 | EMBER (E) | 111 | 5 | 4.5% | 13 | 38.5% | 3.4% |
| best_f1 | Overnight candidate (E0+redflag) | 111 | 2 | 1.8% | 20 | 10.0% | 1.3% |
| precision70 | Seasonal baseline (A) | 111 | 0 | 0.0% | 0 | - | 0.0% |
| precision70 | EMBER (E) | 111 | 0 | 0.0% | 0 | - | 0.0% |
| precision70 | Overnight candidate (E0+redflag) | 111 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | Seasonal baseline (A) | 111 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | EMBER (E) | 111 | 4 | 3.6% | 7 | 57.1% | 2.6% |
| precision50 | Overnight candidate (E0+redflag) | 111 | 0 | 0.0% | 3 | 0.0% | 0.0% |

| Versus baseline: unexpected-fire recall | Rule | Difference | 95% CI |
|---|---|---|---|
| EMBER (E) | best_f1 | +4.5 pt | [+0.0, +9.3] |
| EMBER (E) | precision70 | +0.0 pt | [+0.0, +0.0] |
| EMBER (E) | precision50 | +3.6 pt | [+0.0, +7.3] |
| Overnight candidate (E0+redflag) | best_f1 | +1.8 pt | [+0.0, +3.9] |
| Overnight candidate (E0+redflag) | precision70 | +0.0 pt | [+0.0, +0.0] |
| Overnight candidate (E0+redflag) | precision50 | +0.0 pt | [+0.0, +0.0] |

### Excess hits: fires found beyond what climatology expected in the alerted cells

| Rule | Model | Alerts | Hits | Expected by climatology | Excess hits | Excess per alert |
|---|---|---|---|---|---|---|
| best_f1 | Seasonal baseline (A) | 749 | 431 | 393.7 | +37.3 | +0.050 |
| best_f1 | EMBER (E) | 958 | 500 | 422.5 | +77.5 | +0.081 |
| best_f1 | Overnight candidate (E0+redflag) | 1117 | 532 | 456.8 | +75.2 | +0.067 |
| precision70 | Seasonal baseline (A) | 220 | 180 | 169.4 | +10.6 | +0.048 |
| precision70 | EMBER (E) | 332 | 255 | 222.9 | +32.1 | +0.097 |
| precision70 | Overnight candidate (E0+redflag) | 336 | 248 | 222.9 | +25.1 | +0.075 |
| precision50 | Seasonal baseline (A) | 559 | 361 | 329.9 | +31.1 | +0.056 |
| precision50 | EMBER (E) | 782 | 453 | 378.6 | +74.4 | +0.095 |
| precision50 | Overnight candidate (E0+redflag) | 826 | 453 | 390.6 | +62.4 | +0.076 |

| Versus baseline: excess per alert | Rule | Difference | 95% CI |
|---|---|---|---|
| EMBER (E) | best_f1 | +0.031 | [-0.002, +0.083] |
| EMBER (E) | precision70 | +0.048 | [+0.022, +0.077] |
| EMBER (E) | precision50 | +0.040 | [+0.014, +0.074] |
| Overnight candidate (E0+redflag) | best_f1 | +0.018 | [-0.020, +0.054] |
| Overnight candidate (E0+redflag) | precision70 | +0.026 | [-0.013, +0.064] |
| Overnight candidate (E0+redflag) | precision50 | +0.020 | [-0.018, +0.053] |

## test 2023-2024 (FPA-FOD)

8,320 cell-weeks; 1,369 with a reported fire. Share of fire cell-weeks that were unexpected (c < 5% / 10% / 20%): 5.3% / 12.5% / 28.0%.

### Skill beyond climatology (all cell-weeks)

| Model | Information gain (millibits/cell-week) | Brier skill vs climatology | Ranking within same-risk deciles (ROC-AUC) |
|---|---|---|---|
| Seasonal baseline (A) | +0.0 | +0.0000 | 0.627 |
| EMBER (E) | +7.1 | +0.0112 | 0.665 |
| Overnight candidate (E0+redflag) | +7.3 | +0.0115 | 0.660 |

| Versus baseline | Information gain 95% CI (millibits) | Within-decile ROC-AUC difference |
|---|---|---|
| EMBER (E) | [-0.6, +15.3] | +0.038 [+0.016, +0.060] |
| Overnight candidate (E0+redflag) | [-2.2, +17.3] | +0.033 [+0.008, +0.060] |

### Unexpected fires (climatology < 10%) caught by validation-threshold alerts

Stratum: 4,452 cell-weeks, 3.8% of which had a fire. The baseline's score IS climatology, and all its thresholds exceed 10%, so it cannot alert here by construction; the test for EMBER is whether its alerts in this stratum beat the stratum base rate.

| Rule | Model | Unexpected fire cell-weeks | Caught | Recall | Alerts in that stratum | Their hit rate | Surprise-weighted recall |
|---|---|---|---|---|---|---|---|
| best_f1 | Seasonal baseline (A) | 171 | 0 | 0.0% | 0 | - | 0.0% |
| best_f1 | EMBER (E) | 171 | 2 | 1.2% | 5 | 40.0% | 0.9% |
| best_f1 | Overnight candidate (E0+redflag) | 171 | 5 | 2.9% | 16 | 31.2% | 2.6% |
| precision70 | Seasonal baseline (A) | 171 | 0 | 0.0% | 0 | - | 0.0% |
| precision70 | EMBER (E) | 171 | 0 | 0.0% | 0 | - | 0.0% |
| precision70 | Overnight candidate (E0+redflag) | 171 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | Seasonal baseline (A) | 171 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | EMBER (E) | 171 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | Overnight candidate (E0+redflag) | 171 | 2 | 1.2% | 3 | 66.7% | 1.0% |

| Versus baseline: unexpected-fire recall | Rule | Difference | 95% CI |
|---|---|---|---|
| EMBER (E) | best_f1 | +1.2 pt | [+0.0, +3.0] |
| EMBER (E) | precision70 | +0.0 pt | [+0.0, +0.0] |
| EMBER (E) | precision50 | +0.0 pt | [+0.0, +0.0] |
| Overnight candidate (E0+redflag) | best_f1 | +2.9 pt | [+0.0, +7.0] |
| Overnight candidate (E0+redflag) | precision70 | +0.0 pt | [+0.0, +0.0] |
| Overnight candidate (E0+redflag) | precision50 | +1.2 pt | [+0.0, +3.0] |

### Excess hits: fires found beyond what climatology expected in the alerted cells

| Rule | Model | Alerts | Hits | Expected by climatology | Excess hits | Excess per alert |
|---|---|---|---|---|---|---|
| best_f1 | Seasonal baseline (A) | 1498 | 809 | 787.5 | +21.5 | +0.014 |
| best_f1 | EMBER (E) | 1605 | 849 | 781.4 | +67.6 | +0.042 |
| best_f1 | Overnight candidate (E0+redflag) | 1789 | 884 | 825.5 | +58.5 | +0.033 |
| precision70 | Seasonal baseline (A) | 440 | 365 | 338.7 | +26.3 | +0.060 |
| precision70 | EMBER (E) | 580 | 455 | 405.5 | +49.5 | +0.085 |
| precision70 | Overnight candidate (E0+redflag) | 566 | 448 | 400.2 | +47.8 | +0.085 |
| precision50 | Seasonal baseline (A) | 1118 | 700 | 659.9 | +40.1 | +0.036 |
| precision50 | EMBER (E) | 1293 | 759 | 690.7 | +68.3 | +0.053 |
| precision50 | Overnight candidate (E0+redflag) | 1316 | 769 | 696.4 | +72.6 | +0.055 |

| Versus baseline: excess per alert | Rule | Difference | 95% CI |
|---|---|---|---|
| EMBER (E) | best_f1 | +0.028 | [+0.016, +0.043] |
| EMBER (E) | precision70 | +0.026 | [+0.002, +0.051] |
| EMBER (E) | precision50 | +0.017 | [+0.002, +0.036] |
| Overnight candidate (E0+redflag) | best_f1 | +0.018 | [+0.006, +0.037] |
| Overnight candidate (E0+redflag) | precision70 | +0.025 | [+0.007, +0.045] |
| Overnight candidate (E0+redflag) | precision50 | +0.019 | [+0.001, +0.041] |

## validation 2021-2022

8,320 cell-weeks; 1,264 with a reported fire. Share of fire cell-weeks that were unexpected (c < 5% / 10% / 20%): 8.9% / 16.7% / 33.8%.

### Skill beyond climatology (all cell-weeks)

| Model | Information gain (millibits/cell-week) | Brier skill vs climatology | Ranking within same-risk deciles (ROC-AUC) |
|---|---|---|---|
| Seasonal baseline (A) | +0.0 | +0.0000 | 0.597 |
| EMBER (E) | +26.6 | +0.0356 | 0.672 |
| Overnight candidate (E0+redflag) | +25.1 | +0.0318 | 0.670 |

### Unexpected fires (climatology < 10%) caught by validation-threshold alerts

Stratum: 4,452 cell-weeks, 4.7% of which had a fire. The baseline's score IS climatology, and all its thresholds exceed 10%, so it cannot alert here by construction; the test for EMBER is whether its alerts in this stratum beat the stratum base rate.

| Rule | Model | Unexpected fire cell-weeks | Caught | Recall | Alerts in that stratum | Their hit rate | Surprise-weighted recall |
|---|---|---|---|---|---|---|---|
| best_f1 | Seasonal baseline (A) | 211 | 0 | 0.0% | 0 | - | 0.0% |
| best_f1 | EMBER (E) | 211 | 2 | 0.9% | 17 | 11.8% | 0.7% |
| best_f1 | Overnight candidate (E0+redflag) | 211 | 2 | 0.9% | 19 | 10.5% | 0.7% |
| precision70 | Seasonal baseline (A) | 211 | 0 | 0.0% | 0 | - | 0.0% |
| precision70 | EMBER (E) | 211 | 0 | 0.0% | 0 | - | 0.0% |
| precision70 | Overnight candidate (E0+redflag) | 211 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | Seasonal baseline (A) | 211 | 0 | 0.0% | 0 | - | 0.0% |
| precision50 | EMBER (E) | 211 | 0 | 0.0% | 5 | 0.0% | 0.0% |
| precision50 | Overnight candidate (E0+redflag) | 211 | 0 | 0.0% | 5 | 0.0% | 0.0% |

### Excess hits: fires found beyond what climatology expected in the alerted cells

| Rule | Model | Alerts | Hits | Expected by climatology | Excess hits | Excess per alert |
|---|---|---|---|---|---|---|
| best_f1 | Seasonal baseline (A) | 1498 | 673 | 787.5 | -114.5 | -0.076 |
| best_f1 | EMBER (E) | 1571 | 719 | 761.5 | -42.5 | -0.027 |
| best_f1 | Overnight candidate (E0+redflag) | 1719 | 752 | 803.5 | -51.5 | -0.030 |
| precision70 | Seasonal baseline (A) | 440 | 308 | 338.7 | -30.7 | -0.070 |
| precision70 | EMBER (E) | 488 | 342 | 346.5 | -4.5 | -0.009 |
| precision70 | Overnight candidate (E0+redflag) | 478 | 335 | 344.4 | -9.4 | -0.020 |
| precision50 | Seasonal baseline (A) | 1118 | 559 | 659.9 | -100.9 | -0.090 |
| precision50 | EMBER (E) | 1236 | 618 | 660.0 | -42.0 | -0.034 |
| precision50 | Overnight candidate (E0+redflag) | 1256 | 628 | 668.7 | -40.7 | -0.032 |

## Sensitivity: unexpected-fire recall at other cut-offs (2025, confident rule)

| Cut-off | Model | Unexpected fire cell-weeks | Recall |
|---|---|---|---|
| c < 0.05 | Seasonal baseline (A) | 57 | 0.0% |
| c < 0.05 | EMBER (E) | 57 | 0.0% |
| c < 0.05 | Overnight candidate (E0+redflag) | 57 | 0.0% |
| c < 0.10 | Seasonal baseline (A) | 111 | 0.0% |
| c < 0.10 | EMBER (E) | 111 | 0.0% |
| c < 0.10 | Overnight candidate (E0+redflag) | 111 | 0.0% |
| c < 0.20 | Seasonal baseline (A) | 249 | 0.0% |
| c < 0.20 | EMBER (E) | 249 | 0.0% |
| c < 0.20 | Overnight candidate (E0+redflag) | 249 | 0.0% |
