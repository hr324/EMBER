# Feature experiments (validation 2021-2022 only)

Train 2015-2020, compare on 2021-2022. Fixed gradient-boosting configuration for every variant. Primary metric: share of the weekly top-8 alerts followed by >= 1 reported fire. CIs: calendar-month block bootstrap. The used 2023-2024 holdout is not scored here.

## 1. Weather timing (diagnostic)

- **Hypothesis:** The 7-day weather lag hides near-term dry/windy conditions; weather ending the day before issue, or (diagnostic only) the actual target-week weather, should add skill if weather matters at all.
- **Source:** Open-Meteo historical reanalysis, same 20 points and variables as the current model.
- **Available at issue time:** lag1 = reanalysis ending issue-1 day: an UPPER BOUND, not operational (reanalysis is a later reconstruction). oracle = the actual weather of the forecast week: a LEAKING ceiling used only to decide whether issued forecasts are worth pursuing; never a candidate.
- **Coverage:** All 80 cells, 2015-2022, no missing values.

| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |
|---|---|---|---|---|---|
| A_climatology | 832 | 48.3% | 43.4% | 31.8% | 0.500 |
| E0_history_no_weather | 832 | 47.7% | 43.2% | 31.4% | 0.521 |
| E_weather_lag7 (current) | 832 | 47.5% | 44.1% | 31.2% | 0.521 |
| E_weather_lag1 (upper bound) | 832 | 46.9% | 43.5% | 30.9% | 0.518 |
| DIAG_oracle_target_week (leaks) | 832 | 48.9% | 44.3% | 32.2% | 0.531 |

| Comparison | Precision difference | 95% CI | P(<= 0) |
|---|---|---|---|
| E_weather_lag7 (current) vs E0_history_no_weather | -0.2 pt | [-2.1, +1.5] | 0.628 |
| E_weather_lag1 (upper bound) vs E0_history_no_weather | -0.8 pt | [-2.5, +0.8] | 0.863 |
| E_weather_lag1 (upper bound) vs E_weather_lag7 (current) | -0.6 pt | [-1.6, +0.4] | 0.9135 |
| DIAG_oracle_target_week (leaks) vs E0_history_no_weather | +1.2 pt | [-0.2, +2.7] | 0.0575 |
| E_weather_lag1 (upper bound) vs A_climatology | -1.4 pt | [-3.6, +0.6] | 0.9195 |

**Decision:** REJECT lag-1 weather (no gain even as an upper bound: -0.8 pt vs no weather). The leaking oracle ceiling is only +1.2 pt [-0.2, +2.7], so even perfect next-week weather at this scale adds little. Experiment 4 (issued forecasts, archive from ~2021 only) is therefore DEPRIORITISED: its maximum plausible gain is below what 2 validation years can detect.

## 2. Recent activity anomalies

- **Hypothesis:** Busy or quiet periods across the whole region (and in the last 7 days locally) shift next-week ignition risk beyond season and location.
- **Source:** FPA-FOD discoveries (live equivalent: WFIGS feed, reliable from 2020).
- **Available at issue time:** Counts of discoveries in [issue - N days, issue - 1 day]; known at issue in live use only if reporting is prompt (WFIGS discovery records are near-real-time).
- **Coverage:** All 80 cells, 2015-2022.

| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |
|---|---|---|---|---|---|
| A_climatology | 832 | 48.3% | 43.4% | 31.8% | 0.500 |
| E0_history_no_weather | 832 | 47.7% | 43.2% | 31.4% | 0.521 |
| E0+activity | 832 | 47.6% | 43.4% | 31.3% | 0.529 |
| E0+weather(lag7) | 832 | 47.5% | 44.1% | 31.2% | 0.521 |
| E0+weather(lag7)+activity | 832 | 47.7% | 44.4% | 31.4% | 0.529 |

| Comparison | Precision difference | 95% CI | P(<= 0) |
|---|---|---|---|
| E0+activity vs E0_history_no_weather | -0.1 pt | [-1.0, +0.8] | 0.6485 |
| E0+weather(lag7)+activity vs E0+weather(lag7) | +0.2 pt | [-0.6, +1.1] | 0.355 |
| E0+activity vs A_climatology | -0.7 pt | [-3.1, +1.8] | 0.7265 |

**Decision:** REJECT for the alert budget: -0.1 pt [-1.0, +0.8] vs matched control. Small PR-AUC/capture gain (0.521 -> 0.529) noted; kept only inside the offset-model test.

## 3. Holiday weeks

- **Hypothesis:** Fireworks and holiday travel raise ignitions in holiday weeks beyond the smooth seasonal curve (cf. doi:10.1371/journal.pone.0291026).
- **Source:** Deterministic US federal holiday rules (no external data).
- **Available at issue time:** Known years ahead.
- **Coverage:** All rows; July-4 weeks in train+validation: 8 (base rate 0.331 vs overall 0.160). No historically valid exposure layer (roads/campgrounds) was available, so no interaction term.

| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |
|---|---|---|---|---|---|
| A_climatology | 832 | 48.3% | 43.4% | 31.8% | 0.500 |
| E0_history_no_weather | 832 | 47.7% | 43.2% | 31.4% | 0.521 |
| E0+holidays | 832 | 47.8% | 43.2% | 31.5% | 0.521 |

| Comparison | Precision difference | 95% CI | P(<= 0) |
|---|---|---|---|
| E0+holidays vs E0_history_no_weather | +0.1 pt | [-0.6, +0.7] | 0.416 |
| E0+holidays vs A_climatology | -0.5 pt | [-3.3, +2.4] | 0.637 |

**Decision:** REJECT: +0.1 pt [-0.6, +0.7]. Only ~8 July-4 weeks in train+validation; too rare to learn from at this scale.

## 4. Climatology-offset model (dynamic departures only)

- **Hypothesis:** Holding climatology fixed as an offset, a small penalised adjustment from dynamic departures (weather, activity, holidays, Red Flag) improves the weekly alerts.
- **Source:** Same sources as families 1-3, plus IEM Red Flag Warnings / Fire Weather Watches if built.
- **Available at issue time:** Weather lag 7 days; activity and history before issue; Red Flag as published by Monday 06:00 PT.
- **Coverage:** All 80 cells, 2015-2022. Families: weather, activity, holidays, redflag, gridmet. Anomalies = value minus training-years mean for the same cell and month. L2 penalty chosen on validation from 1, 10, 100.

| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |
|---|---|---|---|---|---|
| A_climatology | 832 | 48.3% | 43.4% | 31.8% | 0.500 |
| A+weather | 832 | 47.4% | 42.7% | 31.2% | 0.502 |
| A+activity | 832 | 48.1% | 44.3% | 31.6% | 0.533 |
| A+holidays | 832 | 48.3% | 43.4% | 31.8% | 0.501 |
| A+redflag | 832 | 48.1% | 43.5% | 31.6% | 0.500 |
| A+gridmet | 832 | 48.0% | 43.2% | 31.6% | 0.500 |
| A+all_dynamic | 832 | 48.3% | 44.2% | 31.8% | 0.525 |

| Comparison | Precision difference | 95% CI | P(<= 0) |
|---|---|---|---|
| A+weather vs A_climatology | -1.0 pt | [-2.0, +0.1] | 0.972 |
| A+activity vs A_climatology | -0.2 pt | [-2.5, +2.3] | 0.6005 |
| A+holidays vs A_climatology | +0.0 pt | [+0.0, +0.0] | 1.0 |
| A+redflag vs A_climatology | -0.2 pt | [-0.7, +0.2] | 0.9125 |
| A+gridmet vs A_climatology | -0.4 pt | [-1.5, +0.8] | 0.774 |
| A+all_dynamic vs A_climatology | +0.0 pt | [-2.3, +2.6] | 0.525 |

**Decision:** REJECT: no family moves the weekly top-8 relative to climatology (all-dynamic +0.0 pt [-2.3, +2.6]). Coefficients have sensible signs (drier 1000-h fuel and recent activity raise risk), but the shifts rarely change which 8 cells rank highest.

## 5. gridMET fuel dryness and fire danger

- **Hypothesis:** Fuel dryness and fire danger at 4 km (ERC, burning index, 100/1000-hour fuel moisture) distinguish dangerous weeks and cells better than 50 km raw weather.
- **Source:** gridMET via Northwest Knowledge Network THREDDS (free), sampled at the 80 cell centroids.
- **Available at issue time:** Latest gridMET day = issue - 3 (observed archive latency ~2 days on 18 Oct 2026). Archive values are final versions; provisional real-time values may have differed.
- **Coverage:** All 80 cells, 2015-2022; rows with any missing gridMET value: 0.

| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |
|---|---|---|---|---|---|
| A_climatology | 832 | 48.3% | 43.4% | 31.8% | 0.500 |
| E0_history_no_weather | 832 | 47.7% | 43.2% | 31.4% | 0.521 |
| E0+gridmet | 832 | 47.2% | 42.8% | 31.1% | 0.513 |
| E0+weather(lag7) | 832 | 47.5% | 44.1% | 31.2% | 0.521 |
| E0+weather(lag7)+gridmet | 832 | 45.8% | 42.6% | 30.1% | 0.516 |

| Comparison | Precision difference | 95% CI | P(<= 0) |
|---|---|---|---|
| E0+gridmet vs E0_history_no_weather | -0.5 pt | [-2.0, +0.9] | 0.764 |
| E0+weather(lag7)+gridmet vs E0+weather(lag7) | -1.7 pt | [-3.0, -0.4] | 0.9955 |
| E0+gridmet vs A_climatology | -1.1 pt | [-3.3, +1.2] | 0.8275 |

**Decision:** REJECT: -0.5 pt alone; -1.7 pt [-3.0, -0.4] when added to lag-7 weather (significantly worse: redundant correlated inputs overfit).

## 6. Red Flag Warnings / Fire Weather Watches

- **Hypothesis:** Red Flag Warnings and Fire Weather Watches already published by Monday 06:00 Pacific (forecaster-identified critical fire weather) mark weeks and cells of elevated ignition risk.
- **Source:** IEM NWS VTEC archive (FW.W, FW.A) for offices STO, EKA, REV, MFR, MTR; zone polygons per event.
- **Available at issue time:** Zone rows count only if product_issued <= Monday 06:00 America/Los_Angeles; valid window = issue..init_expired (expiry as first issued; later extensions ignored).
- **Coverage:** 1986 (event, zone) rows touch the lattice; 17 zones; cell-weeks with a warning for the coming week 4.1%, watch 4.5%, warning in past 7 days 12.4%.

| Variant | Alerts | Precision (top-8/week) | Fire capture | Fire cell-week recall | PR-AUC |
|---|---|---|---|---|---|
| A_climatology | 832 | 48.3% | 43.4% | 31.8% | 0.500 |
| E0_history_no_weather | 832 | 47.7% | 43.2% | 31.4% | 0.521 |
| E0+redflag | 832 | 48.4% | 44.1% | 31.9% | 0.519 |
| E0+weather(lag7) | 832 | 47.5% | 44.1% | 31.2% | 0.521 |
| E0+weather(lag7)+redflag | 832 | 47.5% | 43.8% | 31.2% | 0.520 |

| Comparison | Precision difference | 95% CI | P(<= 0) |
|---|---|---|---|
| E0+redflag vs E0_history_no_weather | +0.7 pt | [-0.2, +1.6] | 0.07 |
| E0+weather(lag7)+redflag vs E0+weather(lag7) | +0.0 pt | [-1.1, +1.2] | 0.559 |
| E0+redflag vs A_climatology | +0.1 pt | [-2.2, +2.5] | 0.491 |

**Decision:** CARRY FORWARD as the single candidate: best validation precision of any new variant (48.4%), +0.7 pt [-0.2, +1.6] vs matched control (P<=0 = 0.07). Not significant; tested once on 2025 per PREREG_2025_v2.md.
