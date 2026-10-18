# EMBER — Wildfire Occurrence Forecasting

> **Execution specification for Claude Code or another repository coding agent.**
> **Project:** IBM Z Datathon 2026 · EMBER wildfire intelligence
> **Branch:** `feature/ember-occurrence` (or another conflict-free feature branch)
> **Delivery:** Work as quickly as correctness allows; ideally finish within a couple of hours. No fixed phase durations or waiting between phases. The team needs a usable handover **before 07:00 Europe/London, 18 October 2026**. If done sooner, hand off immediately. Do not expand scope merely to fill time.

## 0. HARD RULE: ZERO ADDITIONAL SPEND

**The user will not pay for any extra usage. This is an absolute constraint, not a preference.**

- Use **only a verified included coding-agent allowance**. Do **not** use a metered model/API key, pay-as-you-go usage, extra-usage credits, automatic top-ups, paid model upgrades, paid cloud compute, or billable third-party APIs. Do not buy credits or request billing details.
- **Claude Code:** use login tied to an existing subscription **only after confirming that the session is using its included allowance**. Do not use an `ANTHROPIC_API_KEY`-authenticated Console/API session; an environment key can override subscription authentication. Check `/status` where available. Decline any “extra usage”, API-credit, Console-switch, or paid continuation prompt. If an included usage limit is reached, **stop and preserve your work**; do not bypass the limit.
- **Codex:** sign in with the existing **ChatGPT account**, not an OpenAI API key or a credit-billed API/project account. Inspect usage/status and decline additional credits, purchases, or paid continuation.
- Never assume a free-looking command is non-billable: **if the billing route is unclear, stop and ask the user to verify it before calling the service**. The repository cannot enforce the vendor's billing settings.
- Data access, compute and training must use free public endpoints, local CPU execution, and already-available approved infrastructure. No external LLM inference calls.
- Do not spawn paid subagents or parallel paid coding-agent sessions. Minimise context burn by reading relevant files only, using compact command outputs, and summarising long logs rather than pasting them into chat.
- Under no circumstances sacrifice this cost rule to meet the deadline. **If work cannot continue for free, hand over what exists.**

## 1. Purpose and boundaries

Build a **real-data, retrospective backtest of a prospective wildfire occurrence forecast**. For each geographic cell and forecast issue date, rank the likelihood of **at least one newly recorded wildfire during the following seven days**, based only on information available before issue time.

**What we are building:** historical spatiotemporal wildfire occurrence-risk forecasting and a holdout demonstration with observed subsequent events.

**What we are not building:** reverse propagation to locate the origin of an already observed fire, wildfire spread modelling, ignition cause attribution, a forecast of the precise ignition time/point, or a production emergency warning service.

Another EMBER branch already implements **retrospective origin reconstruction**, based on VIIRS observations, a directed spread graph and reverse-Dijkstra reasoning. Keep this code intact. Build an independent, modular occurrence-forecasting feature and integrate only through a small export/API interface.

### Required outputs

1. Real and auditable labelled cell-week training data.
2. A simple **season/location baseline** and a **weather-fusion model**, trained and tested on actual historical observations.
3. A saved holdout-period forecast and **measured baseline comparison**.
4. A dated **risk-map GeoJSON** plus observed ignition locations shown only as the *subsequent outcome*.
5. Reproducible code, tests for leakage, a short README, data citations and a precise handover of measured results and limitations.
6. If the existing frontend is stable and integration is straightforward: an embedded map/API; otherwise use a standalone HTML/GeoJSON export. A defensible standalone result is preferred to fragile integration.

**Minimum successful delivery:** one real historical forecast, an honest seasonal benchmark, a working environmental model, a comparative metric and visual map. **Stretch goal:** statistically credible evidence that adding environmental signals improves predictions. Never claim an improvement that was not measured.

## 2. Scope — reduce scope when it speeds up honest delivery

| Setting | Initial value |
| --- | --- |
| Study region | Northern California; bounding box approx. latitude 39.0–41.0 N and longitude −122.8 to −120.8 (includes Butte County) |
| Spatial indexing | Square cells of ~25 km, created in **EPSG:3310** / California Albers (not fixed longitude-degree squares) |
| Observation | Each **real geographic cell × actual historical week** |
| Issue date | Weekly, beginning of a seven-day future window |
| Label | 1 if at least one wildfire was *recorded as discovered* within that cell and next 7 calendar days; otherwise 0 = **no reported ignition**, not proof no fire happened |
| Coverage | 2015–2024, if source and weather availability permit |
| Training | 2015–2020 |
| Model selection / validation | 2021–2022 |
| **Frozen final holdout** | 2023–2024 |
| Initial models | Smoothed seasonal baseline, logistic regression; then CPU gradient-boosted trees if justified |
| Initial context features | Historical seasonality/geography and **lagged real-world weather observations** |

Treat fire `discovery_date` as a calendar-date label, not an exact ignition time. Check the ArcGIS date representation and document any time-zone convention. Use consistent local calendar weeks for labels; do not inadvertently shift date-only values through timezone conversion.

**Do not choose “predict one wildfire” as the training task.** A single fire has no useful negative examples or adequate independent training signal. Once trained on multiple years/fires, it is fine to make **one held-out historical week/fire** the headline demo, provided that event was never used in training or tuning.

If positives are scarce, expand California coverage or aggregate to 40–50 km grid cells. If weather ingestion is slow, use a smaller sample of **real geographic cells/years**, keeping enough positive events for evaluation; document reductions. Do not manufacture observations.

## 3. Data: authoritative sources, access, and strict provenance

### A. Real wildfire occurrence labels — REQUIRED

- **USFS FPA-FOD 7th Edition**, complete layer (fires 1992–2024, ~2.66 million nationwide):
  - Metadata / service: https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_FireOccurrenceCurrentEdition_01/MapServer
  - Actual fire layer: https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_FireOccurrenceCurrentEdition_01/MapServer/0
  - Immutable-edition archive citation: https://doi.org/10.2737/RDS-2013-0009.7
- Query layer `/0/query` with `where`, `outFields`, `returnGeometry`, `outSR`, `f=json`. The service currently supports pagination and has **max record count 2,000** per response. Filter state/year/spatial extent server-side if possible. Paginate safely using `resultOffset` / `resultRecordCount`, or first retrieve object IDs and batch them.
- Retrieve real field names from layer metadata **before coding**. These include `discovery_date`, `fire_year`, `latitude`, `longitude`, `state`, `nwcg_general_cause`, `fire_size`, `fpa_id`; verify the stable identifier/OBJECTID actually returned. Do not assume a `fod_id` field exists in this current service.
- Fire size and discovered cause are **not predictors** (post-event information). Keep them only for audits / optional separate descriptive analysis. Deduplicate, check implausible coordinates, duplicate positions and discovery dates. Note known reporting/coordinate imprecision.
- Persist small source extracts verbatim (or hashed source URLs + file hashes) and cleaned data separately. Do not commit huge datasets.

### B. Real historical meteorological data — REQUIRED for fusion

- **Open-Meteo Historical Weather (ERA5 / ERA5-Land as supported)**:
  - Docs: https://open-meteo.com/en/docs/historical-weather-api
  - Endpoint: https://archive-api.open-meteo.com/v1/archive
- Pull consistent weather source data at grid centroids (or a clearly documented representative sampling). Begin with historical daily temperature, precipitation, humidity and wind; add VPD/soil moisture only when endpoint supports it. Inspect actual variable names and units before writing calls. Where a daily variable is unavailable, derive it from observed/reanalysis hourly data.
- Important: reanalysis represents historical estimated environmental conditions, **not a versioned forecast that existed on that day**. To reduce look-ahead from ordinary observation latency, apply a **conservative 7-day lag** between the latest weather input and forecast issue date. This still does not solve retrospective reanalysis revision bias; explicitly note the limitation. **Never use weather from the predicted seven days**.
- Cache API responses; batch where supported, retry politely, limit requests, and never require a paid API plan.

### C. Optional environmental sources — NOT on critical path

- **gridMET** (1979–, daily climate and fire-weather variables such as ERC): https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_GRIDMET — add only with a free accessible ingestion route; do not block on Earth Engine setup.
- **LANDFIRE** vegetation/fuels: https://www.landfire.gov/data — only if year-appropriate historical layers can be acquired without major GIS work; beware using present-day fuel maps for past forecasts.
- **OSM / Geofabrik California** roads and infrastructure: https://download.geofabrik.de/north-america/us/california.html — optional only; modern network geometry is not a valid 2015 historical snapshot. Prefer versioned historical data if included.
- **FPA-FOD Attributes** enriched at-fire-location dataset: https://zenodo.org/records/8381129 — useful as research and schema inspiration, but **positives-only features cannot produce an occurrence model** without matched recorded non-event area-weeks. Large download, not a critical path dependency.
- **NASA FIRMS**: https://firms.modaps.eosdis.nasa.gov/download/ — for the existing reconstruction branch or post-hoc visual context, **not as a feature for forecasting a fire before it occurs**.

### Provenance artifact

Save `provenance.json` containing source URLs, dataset edition, query parameters, download dates, date range, geographical coverage, source files/hashes where practical, feature units, known time availability limitations, and missing-data policy.

## 4. Real cell-week labels; avoid fabricated examples

1. Read actual fire records; place observed coordinates into projected grid cells.
2. Generate the calendar lattice of **real places and historical weeks** (this is enumeration of actual no-reported-fire intervals, **not synthetic simulated data**).
3. Label cell-week 1 if >=1 fire discovery within its forecast interval, otherwise 0, explicitly defining 0 as **zero reported fire incidents**.
4. Join meteorology based on cell geometry and timestamps strictly before the prediction issue date and weather availability lag.
5. Store `(cell_id, forecast_date, date_cutoff, label, feature columns, event_count)` and optional geometry, with a reproducible build script.
6. Keep all cell-weeks in final evaluation. Negative sampling in training is not preferred; if unavoidable, document sampling design and do not advertise naïve output scores as population probabilities.

Audit and report: event count, cell count, number of labelled weeks, positive rate, positives in each chronological split, missingness, grid coverage, and duplicated / suspicious fire positions. **Do not proceed into heavy modelling until the label table has been inspected.**

## 5. Features: small, ex ante, interpretable

**Baseline (required):** calendar week-of-year, circular sine/cosine season, cell/region/location context. Train-smoothed fire frequency by week/region is acceptable if computed exclusively within training history; do not compute climatology from all years.

**Weather (required):** trailing 7/14/30-day *past* means, maxima and totals for temperature, precipitation, humidity and wind. Example: 14-day average humidity ending at the last permitted weather observation date. Keep window boundaries explicit and testable.

**Optional:** 30/90-day preceding fire counts in a cell and adjacent cells; lagged drying / vapor pressure deficit; historical vegetation; road density — only once the first model runs and these are correctly timestamped. No final burned area, known cause, suppression records, future FIRMS detections or target-week observations.

## 6. Models, baselines and scientific test

Implement in this order, moving to the next item immediately when the preceding one works:

1. **Seasonal climatology:** smoothed historical weekly ignition rate using training years only. This sets a meaningful no-environment baseline.
2. **Logistic regression:** season + location. Use appropriate numeric preprocessing and a sensible regularisation strength.
3. **Logistic regression + lagged weather:** same location/season features plus environmental information.
4. **HistGradientBoostingClassifier** or existing installed CPU gradient-boosted library: same features, few configurations. Only keep if testable benefit over simple models.

**What success means:** high-ranked cells contain disproportionately many future observed ignitions, and the fused model improves against a fair baseline on unseen future years. The final narrative must report negative or null findings accurately.

**Validation:** train 2015–2020; choose features/hyperparameters on 2021–2022; freeze; evaluate once on 2023–2024. All feature transformers and imputers fit on training only. Do not repeatedly tune on test. Temporal-only split is a minimum: if feasible, add a spatial holdout / robustness experiment, since neighbouring cells share climate and fire occurrence patterns.

**Primary task metric:** weekly **top-10%-of-cells event capture** (fraction of all recorded ignitions in cells the model ranked in the top 10% that week). Compare to baselines at identical cell coverage. For interpretable lift, divide capture fraction by 0.10 but note equal-area and uneven regional eligibility. Also show top-5% and top-20% if easy.

**Secondary metrics:** PR-AUC, prevalence, Brier score (only interpret as calibration evidence after checking actual reliability), ROC-AUC as context; uncertainty via temporal-block bootstrap if time. Count total events, weeks and positives. If probabilities are uncalibrated (likely), label output **risk score**, not “XX% chance”.

**Ablation table:** (A) seasonal, (B) season+location, (C) +weather linear, (D) +weather nonlinear, (E) additional features only if available. Provide exact train/test dates and result files.

**No leakage:** calculate feature timestamps relative to prediction issue, and assert `feature_latest_available_date <= issue_date - 7 days` for reanalysis-based weather. Historical fire counts can include only fire discoveries before issue date. Do not evaluate Camp Fire 2018 as independent held-out evidence when using a model trained on 2018 observations; a special Camp Fire demo would need a separate pre-November-2018 training cutoff and independent validation.

## 7. Output contracts and demo

**Required artifacts:**

- `forecasting/outputs/metrics.json` — each baseline/model, split, numeric results, prevalence, sample counts and explicit limitations.
- `forecasting/outputs/holdout_predictions.csv` or `.parquet` — `forecast_date`, `horizon_days`, `cell_id`, `centroid_lat`, `centroid_lon`, `risk_score`, `observed_fire`, `model_name`, `model_version`; include event count where appropriate.
- `forecasting/outputs/forecast_map.geojson` — cell polygons and risk scores for **one held-out historical week**, with CRS and dates documented.
- `forecasting/outputs/observed_events.geojson` — subsequent real reported fire locations, drawn **only in the demo reveal / evaluation layer**.
- `forecasting/outputs/provenance.json` — sources, queries, hashes if practical, date cutoffs and assumptions.
- An embeddable HTML map or lightweight existing-frontend page showing **before** (forecast risk) then **after** (observed future ignitions), optionally baseline vs fusion. No fabricated hotspots or unearned accuracy badges.
- `forecasting/README.md` — one-command reproduction from cached samples, full data acquisition procedure, environment/dependencies, and honest limitations.

**API if easily compatible with repo:** a read-only endpoint such as `GET /api/forecast?date=YYYY-MM-DD` serving precomputed historical predictions; do not require runtime model training on every request. Preserve the original EMBER reconstruction API and UI.

**IBM LinuxONE:** Python CPU compatibility preferred. Do not assert genuine s390x execution without captured `uname -m` plus a real inference/API response. If binary ML libraries are missing on s390x, export fitted logistic coefficients + preprocessing and run a small pure-Python inference wrapper. No paid hosted deployment.

## 8. Repo procedure, tests and branches

At the start:

1. Inspect `git status`, project structure, existing APIs, environment and installed packages; read relevant README/config. **Never touch teammates' uncommitted files.**
2. Confirm the coding-agent session has **no incremental billing exposure** before substantial operation. If uncertain, ask the user rather than gamble.
3. Create a safe feature branch. If an existing branch/worktree is in use, avoid destructive checkout; use a separate worktree if possible.
4. Implement independently under `forecasting/` (adapt layout to repo conventions), using small functions and few dependencies.
5. Do not force-push, merge to main, change another branch or delete files without approval. Commit only code and small provenance, no huge data blobs/secrets.

Tests should use **small cached extracts of authentic source records**, not simulated fires or synthetic meteorology. Test cell assignment, split boundaries, time availability, no target leakage, model serialization and reproduction of metrics. Basic mathematical invariants can be asserted without inventing training observations.

## 9. Work strategy — deliver FAST, not by a stopwatch

**No fixed phase time budgets.** Complete each dependency as soon as possible and immediately proceed; don't wait for allotted time. If the MVP is complete early, hand it over rather than polishing irrelevant extras. Aim to get the whole thing working in a couple of hours if data acquisition cooperates. Respect the **07:00 UK handover deadline**.

Critical path, strict priority:

1. **Data viability:** real FPA-FOD subset; real weather sample; confirm correct fields, units and coverage.
2. **Labels:** real cell-week lattice, positive/zero-reported labels, strict date join, data audit.
3. **Baseline:** season/location model, holdout split, defensible metrics and saved predictions.
4. **Fusion:** add lagged weather, measure lift and verify no leakage.
5. **Visual:** export real historical map and after-the-fact observed event reveal.
6. **Integration:** connect to EMBER UI / IBM Z only if stable and not blocking the above.
7. **Extensions:** nonlinear model, vegetation, infrastructure and richer graphs only with ample remaining time and validated progress.

**Failure and fallback rules:**

- FPA-FOD service unavailable → try the immutable USFS Research Data Archive export or another authentic public state-level wildfire occurrence dataset; report exact replacement.
- Weather blocked/slow → reduce cell count or year range, reusing real data. Preserve a working seasonal baseline and show exactly what remains incomplete. Never simulate missing weather.
- Too few positives → expand region, historical years or cell size; don't fabricate class balance.
- Fusion worse than baseline → show it, retain the valid model and stop tuning the holdout.
- Frontend integration unstable → ship ready-to-open GeoJSON/HTML map plus scripts.
- Agent included usage reached or any possible paid service required → **stop**, commit/hand off work, leave an actionable resume note. Zero additional spend outranks all deliverables and deadlines.

At each major checkpoint give the user a **short** progress summary: real rows downloaded, positives, model status, holdout metrics, remaining obstacle. Do not dump entire files/logs and waste context.

## 10. Finish conditions and team handover

Stop when the required outputs work, have been validated and are usable in the pitch. Do **not** expand scope because the deadline has not arrived.

Provide a concise final handover with:

- Branch name, commit hash, directory and exact run instructions.
- Actual sources, years, geography, positive/negative rows and acquisition status.
- Precise prediction target and temporal weather cutoff.
- Baseline vs fusion results on chronological holdout (with counts and limitations).
- Screenshot/HTML map path and artifacts to give the slide/pitch owner.
- Which features are real/implemented vs exploratory/not yet integrated.
- Remaining scientific caveats: incomplete fire records, imprecise discovery dates, reanalysis availability, imperfect operational interpretation.
- Exact evidence (or explicit non-verification) for any IBM LinuxONE runtime claim.
- Any unresolved block; never claim that blocked tasks succeeded.

**Central thesis:** EMBER uses real historical fire observations and lagged environmental evidence to infer which places face elevated *new ignition occurrence* risk. Our benchmark must test whether the connected signals reveal something that historical geography and seasonality cannot.
