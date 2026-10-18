# Pre-registered independent test: 2025 (and 2026 to date)

Committed 18 October 2026, **before** any 2025 or 2026 label, feature or score was computed.
The only 2025 fact seen beforehand was the total count of WFIGS wildfire records in the study
box (1,244), seen while checking the source exists. If any rule below changes after scoring,
the change and its reason will be recorded here, and the original result reported alongside.

## Frozen models

- **Exactly the models in `forecasting/outputs/models.pkl`.** They were trained on 2015–2020 FPA-FOD labels, with settings chosen on 2021–2022. No retraining, refitting, recalibration or setting changes.
- **Climatology (model A):** the frozen 2015–2020 table, as used for the 2023–2024 holdout.
- **Comparison:** headline model **E_gbm_history_weather** against baseline **A_climatology**. All seven models are reported.

## Labels (new source)

- **Source:** NIFC WFIGS Incident Locations, `IncidentTypeCategory = 'WF'` only.
- **Discovery date:** `FireDiscoveryDateTime` (UTC), converted to the **America/Los_Angeles calendar date**.
- **Location:** `InitialLatitude`/`InitialLongitude`; if missing, the point geometry. Records are assigned to the same 80 EPSG:3310 cells.
- **Deduplication:** by `UniqueFireIdentifier`, then by `IrwinID`.
- **Label:** a cell-week is 1 if at least one record falls in [Monday, Monday + 6].

## Issue dates

- **Primary test, 2025:** Mondays 2025-01-06 to 2025-12-22 (51 weeks).
- **Secondary test, 2026 to date:** Mondays 2026-01-05 to 2026-09-28. The last window ends 2026-10-04, two weeks before this note, to allow for late reporting. Reported separately, and only if the weather archive covers it.

## Features (same definitions as before)

- **Season and location:** unchanged.
- **Weather:** Open-Meteo archive, the same 20 points and variables, the same 7-day lag.
- **Fire history:** from WFIGS for every window. This matches live use, where FPA-FOD isn't available.

## Metrics

- **Primary:** share of each week's fires in each model's top 10% of cells (8 cells), E against A. 95% CI from a calendar-month block bootstrap.
- **Secondary:**
  - equal-budget hit rate at 5.4% of cell-weeks;
  - season split;
  - top 5% and top 20%, PR-AUC, ROC-AUC;
  - confusion matrices at the same three rules as `AUDIT.md`.

## Data-quality checks (run on 2015–2024 before scoring 2025; not used to choose anything)

1. **Label agreement:** WFIGS vs FPA-FOD cell-week labels, 2015–2024.
   - Overall agreement
   - Agreement on fire cell-weeks
   - Cohen's kappa
   - Yearly record counts
2. **Effect of the source change:** model E and A on 2023–2024, scored with WFIGS labels and WFIGS history instead of FPA-FOD.
   - This shows how much the score moves just from the source change.
   - The 2025 result is read against that shift.

## Interpretation

- **E beats A** only if the 95% CI of the primary difference excludes zero.
- **A null or negative result** is reported as such.
- **The absolute capture level** is compared with the 2023–2024 holdout only after allowing for the source-change effect in check 2.
