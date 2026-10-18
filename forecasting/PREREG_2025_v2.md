# Pre-registered test of the overnight candidate on 2025

Committed 18 October 2026, **before** any 2025 score for the candidate was computed.

**Disclosure:** 2025 is not untouched. On 18 Oct 2026 the original frozen models (A and E) were scored on it once (`PREREG_2025.md`, `outputs/EXTERNAL_TEST.md`). The candidate below was chosen on 2021–2022 validation only, without reference to any 2025 result. One more look at 2025 is therefore a test of a pre-specified model, but not a pristine blind test.

## Candidate (chosen on validation, `outputs/experiments.md`)

- **Name:** `E0+redflag`. Gradient boosting with season + location + climatology + fire history + Red Flag Warning / Fire Weather Watch features; no raw weather.
- **Settings:** the fixed configuration used for every overnight variant (`experiments.GBM`), random seed `models.SEED`.
- **Training:** 2015–2020 FPA-FOD labels only. Exactly the validation fit; no refit on 2021–2022.

## Comparators, all at the same budget

- **A:** the frozen climatology from 2015–2020. **This is the primary comparator.**
- **E0:** the matched control, the same settings and data without Red Flag features.
- **E:** the frozen original headline model from `models.pkl`.

## Labels and features for 2025

- **Labels:** the same as `PREREG_2025.md`: WFIGS `IncidentTypeCategory = 'WF'`, Pacific discovery date, the same dedup rules, Monday issue dates 2025-01-06 to 2025-12-22 (51 weeks).
- **Fire history:** from WFIGS.
- **Red Flag features:** built from the IEM archive by `fetch_redflag.py`, with the same rule: zone rows count only if `product_issued` ≤ Monday 06:00 America/Los_Angeles.
- **Weather:** used only by E, with the 7-day lag.

## Metric (primary, from the mission)

- **Alert hit rate:** across all 51 weeks, the share of the weekly top-8 alerts (408 alerts) followed by at least one reported wildfire in that cell within 7 days.
- **Primary comparison:** candidate vs A, with a calendar-month block-bootstrap 95% CI.
- **Secondary:**
  - candidate vs E0 and vs E;
  - share of fires captured;
  - recall of fire cell-weeks;
  - PR-AUC;
  - the confusion table.

## Interpretation, fixed now

- **The candidate beats the baseline** only if the 95% CI of the primary difference excludes zero. Otherwise the result is "no measurable advantage established".
- **The result is reported whatever it is.** No second 2025 variant will be tried.

## Outcome (run once, 18 Oct 2026)

`outputs/candidate_2025.json`. Weekly top-8 alerts, 51 weeks, 408 alerts per model:

| Model | Alerts followed by a fire | Hit rate |
|---|---|---|
| A climatology (primary comparator) | 223 / 408 | 54.7% |
| E0 matched control | 225 / 408 | 55.1% |
| **E0+redflag (candidate)** | **225 / 408** | **55.1%** |
| E original frozen model (secondary) | 235 / 408 | 57.6% |

- **Candidate vs A:** +0.5 pt, 95% CI [−2.5, +3.5]. **No measurable advantage established.**
- **Candidate vs E0:** +0.0 pt. The Red Flag features changed no alert outcome.
- **E vs A (secondary):** +2.9 pt [−0.5, +6.0], P(≤ 0) = 0.05. Suggestive, but the CI includes zero.
