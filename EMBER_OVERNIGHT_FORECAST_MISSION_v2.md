# EMBER — Overnight forecasting mission

**For:** Claude Code / Codex, working on the `rayan` branch in `forecasting/` (or a new safe child branch/worktree).  
**Date:** 18 October 2026 · IBM Z Datathon.  
**Mode:** Work autonomously on the accessible repository. Deliver a functioning, reproducible result **as soon as it is ready**, preferably before the team's next morning check-in. No fixed work intervals, no artificial waiting, no expansion just to consume the remaining night.

> **MISSION IN ONE SENTENCE:** Improve EMBER's ability to predict **which real geographical cells will experience a newly reported wildfire in the following seven days**, by detecting **changes in actual ignition risk that location and season alone cannot explain**, using the strongest feasible real-world predictors (near-term weather, ignition mechanisms, human activity, lightning, fuel conditions, and their interactions). The team cares about measurable holdout performance, **not** which category supplies the improvement.

## AUTONOMY UPDATE — choose the best feasible improvements, not a fixed feature checklist

**This mission is deliberately broader than human activity.** You are authorised to investigate **any additional real, free, historically defensible source or derived signal** that could improve the real-world seven-day ignition forecast before the user wakes. The experiments below are **candidate opportunities, not a mandatory order or exhaustive list**. Your success criterion is an honest improvement over the same-budget season/location baseline on time-respecting evaluation. **Do not spend the night merely implementing holiday features if a stronger weather/ignition opportunity is feasible.**

Within 20–30 minutes of starting (or as soon as repository audit makes it possible), rank candidate avenues by **expected incremental predictive information × ease of acquisition × historical/live availability × probability of delivering a reproducible result tonight**. Use that ranked plan autonomously. An acceptable default shortlist is:

1. **Issued weather actually available on the forecast date**, especially upcoming dry-windy periods, low precipitation, vapour-pressure deficit and gusts. The old 7-day weather lag is a known limitation. Be strict about original issue times and temporal leakage.
2. **NWS Red Flag Warnings / Fire Weather Watches** issued before forecast time, with archived issue timestamps and geographic coverage; test whether they add useful information over season/location and the weather features already included.
3. **Human-driven ignition opportunity**: holidays, July 4 fireworks window, recreation exposure and traffic *only when authentic historical data are accessible*. Useful novel features may be interactions such as holiday × campground/road density; do not assume a holiday indicator alone materially helps.
4. **Lagged lightning with rainfall**, including delayed discoveries, if archived GLM data can be ingested cheaply and correctly.
5. **Dynamic fuel dryness and changes**: a small targeted experiment with gridMET fire-danger indices / moisture, lagged VPD or soil-moisture anomaly **only if historically available by Monday**. Prefer a few scientifically motivated anomalies/interactions over dozens of correlated weather columns.
6. **Other credible dynamic interactions**: wind × power-line exposure, dry conditions × recreation pressure, rapid departure from local climatology, or a discovered free source that passes the same timing, quality and privacy checks.

**Execution rule:** validate one scientifically motivated feature family at a time against an exactly matched baseline, log null and negative results, then combine only families showing genuine validation benefit. Stop searching once the remaining time makes a clean evaluation, saved scoring interface, and readable handover unlikely. Do not collect identifiable individuals' location traces or scrape social media. Do not alter the label definition or narrow the test to fire-positive examples to improve the headline metric. Independent 2025 evaluation stays once-only and frozen.

## 0. Non-negotiable: £0 extra spend, no overnight human dependency

1. **No extra paid tokens, model calls, top-ups, metered Anthropic/OpenAI API usage, external LLM APIs, cloud compute, paid subscriptions, paid data licences, billing registration or purchases.** The user explicitly refuses any additional spend. Use only an **already-included, verified coding-agent allowance**, free public data endpoints and existing local or already-authorised compute. Never silently switch from a subscription login to an API key, prepaid credits or an overage plan.
2. Check any available agent usage/auth status at the beginning. This document **cannot guarantee account-level billing protection**. If you cannot establish that continuation is within an existing allowance, or a tool presents paid continuation, **stop** after saving/committing available work. Do not initiate billable calls to check billing. Do not spawn extra agents or background model tasks that might cost credits.
3. Work while the user is asleep: **do not block on questions or new approvals**. Make conservative decisions, leave a clear log of choices, and skip optional sources requiring manual access. Do not create third-party accounts, accept new terms or request credentials on the user's behalf.
4. **Only real data.** Do not synthesize fires, fire-free events, lightning observations, visitor numbers, weather or prediction outcomes. A full grid of *real places and real historical weeks* with a label derived from recorded fire occurrence is valid; a random fake wildfire is not. Derived lagged statistics and deterministic calendar features are valid. Small hand-constructed test fixtures for software invariants may be used only if clearly separated from all modelling and evaluation datasets; prefer existing authentic-record fixtures.
5. Never modify another teammate's origin-reconstruction/spread model, delete their assets, force-push, or merge to the shared branch. Inspect status first, isolate all work, commit a readable handover. Do not change existing `CLAUDE.md` without team approval. **This is a mission addendum, not a replacement for the current project rules.**
6. **Finish early if done early.** No rigid phase timers. Stop after genuinely useful deliverables are validated. If a source is difficult, fall back quickly rather than spending the night on one API.

## 1. Baseline: what already exists — preserve it

Read `EXPANSION_RESEARCH.md` and the current code, configs, outputs and tests before making changes. The following are **claims from the team's research brief, not independently reverified here**:

- Target: northern California (39–41° N, 122.8–120.8° W), **80 approximately 25-km cells**, Monday-issued seven-day forecasts.
- Label = 1 when **at least one newly recorded fire** has a discovery date in a given cell in the coming Monday–Sunday week. Label 0 means **no fire recorded**, not certainty that none happened.
- Training 2015–2020; model tuning 2021–2022; original 2023–2024 test **has already been used**. 41,680 cell-weeks; original test has 8,320 cell-weeks, ~16.5% with ≥1 recorded ignition.
- Highest-ranked eight cells (~10% of geography) each week contained **46.8% of individual new recorded fires**, versus **45.6%** for the season/location baseline. The difference is **not statistically established** (reported 95% CI −0.4 to +3.0 percentage points).
- When full-model risk score ≥0.7: **83.3%** of 449 alerts were followed by ≥1 reported fire in that cell-week, but the seasonal baseline was **88.0%** on 276 alerts. These are **different alert volumes** and cannot be interpreted as a clean model victory.
- At the same top-eight-cells-per-week alert budget: existing brief reports **52.4%** of the full model's flagged cell-weeks positive versus **50.8%** for the baseline. This is a much more comparable operational success measure.
- Inputs already include season, location, past reported fires and historical reanalysis **ending seven days before forecast issue**; no claimed measurable weather gain.
- The original 2023–2024 results, including the 2024 Park Fire miss, must be retained unchanged and never silently overwritten. No hyperparameter tuning against them.

**Scientific goal:** obtain predictive gain that **cannot already be explained by location + season**. More features are not the goal. Improved out-of-time predictions are.

## 2. Human-readable success metric — what the team actually wants

The user wants **one understandable number: when we predict a fire starting, how often are we right?** Define and report that honestly:

**PRIMARY HEADLINE: precision at a fixed, predeclared alert budget**. Every Monday, EMBER marks the **top 8 of the 80 cells** as “fire expected here within 7 days.” Across the entire untouched test period:

\[
\text{Fire-alert success rate} = \frac{\#\{\text{flagged cell-weeks with at least one newly reported fire}\}}{\#\{\text{flagged cell-weeks}\}}\times100\%.
\]

Say it like: **“Of the eight areas EMBER warned about each week, X% saw at least one reported fire within seven days.”** Compare with **the seasonal baseline at the exact same eight-cell-per-week budget**, plus the number of true fire-positive weeks missed and total number of alarms. Only report X when measured on new independent holdout data.

Why this is necessary: since only 16.5% of original cell-weeks were positive, a trivial “no fire anywhere” classifier would achieve ~83.5% conventional *accuracy* yet never forecast a fire. **Never headline overall accuracy** or call this exact-coordinate ignition prediction. Also never headline 83.3% without saying **449 selected alarms**, what share of weeks/cells it represents, and the baseline comparator.

Also report, clearly but secondarily:
- **Event capture:** fraction of all actual *reported ignition events* lying in the alerted eight cells (a cell can contain several fires).
- **Positive cell-week recall:** fraction of positive cell-weeks covered by alerts.
- **Threshold precision/alert volume:** at ≥0.7 risk score, if meaningful; always give number of calls, base rate, and threshold chosen on validation only. Compare baselines at **equal alert counts**, not at unmatched confidence thresholds.
- PR-AUC and Brier score; uncertainty for the gain relative to the baseline with block bootstrap over months/weeks (do not treat adjacent cells as independent).
- One-sentence qualifier: 25-km area, next week, *reported* fire, not exact ignition location/time.

**Set alert budget and metric before evaluating new untouched data; do not tune them against new test results.** A high precision achieved by flagging one obvious summer hotspot is not the same as broad forecasting ability.

## 3. Data acquisition and experiments — prioritise genuine ignition triggers

All sources must pass: **(i)** free without new payment, **(ii)** available by the forecast issue time, **(iii)** enough historical data to train and validate, **(iv)** usable roughly at the spatial scale of 25 km cells, **(v)** not caused by the fire being predicted. Check and record each source's temporal publication lag, location precision, licences/attribution and archive gaps. Do not assume successful API access means the data was available historically in real time.

### Experiment 1 — Real human-activity calendar signals [QUICK CANDIDATE; NOT MANDATORY FIRST]

**Hypothesis:** ignition opportunities change around known public holidays and recreation periods, beyond normal seasonality.

Implement **deterministic, historically correct** US/California calendar indicators known ahead of Monday: seven-day horizon overlaps **4 July**, observed Independence Day, Memorial Day, Labor Day and other major travel/holiday periods, plus days before/after July 4 where justified. Include pre-specified interactions with existing cell-level recreation / road exposure **only if already available without historical leakage**.

**DO NOT add `weekend_days_in_week` as a feature:** every Monday–Sunday week contains exactly two weekend days; it is constant and cannot help. A pre-specified holiday-week or long-weekend flag can vary. If a library is needed, prefer built-in Python date rules / already-installed `holidays`; do not require paid data.

A published 2023 study directly documents increased Fourth of July fireworks ignitions and a temporal association with the placement of holidays/weekends, but those findings are **not proof our region's all-cause model will benefit**: https://doi.org/10.1371/journal.pone.0291026

Start with all-cause fire labels. If reliable known-cause records are sufficient, perform **exploratory stratified analysis** of human-caused vs lightning fires and document the major missing-cause bias. **Do not infer the cause of unknown-labelled fires and treat it as truth.** Do not filter to only human-caused fires and report the resulting precision as though it applies to all fires.

### Experiment 2 — Fire-weather warnings issued BEFORE prediction [HIGH PRIORITY IF ARCHIVE USABLE]

**Hypothesis:** a Red Flag Warning or Fire Weather Watch issued before Monday provides dynamic context beyond monthly fire climatology. This is an operational decision signal from human fire-weather forecasters and may be predictive without expensive model retraining.

**Archive:** Iowa Environmental Mesonet (IEM) NWS VTEC data: https://mesonet.agron.iastate.edu/api/ and https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml ; project has previously used e.g. `https://mesonet.agron.iastate.edu/json/vtec_events_bywfo.py?wfo=STO&year=2024&phenomena=FW&significance=W`.

- Confirm all National Weather Service forecast offices and warning zones overlapping the region, not just Sacramento.
- Retain **issue timestamps**. At each Monday 06:00 Pacific forecast issue, use only warnings **already issued by that instant**. It is valid to flag that an earlier-issued warning covers a period within the coming week; it is invalid to use a warning issued Tuesday to predict Monday's week.
- Map warning coverage to actual cell geometry; deduplicate repeat updates; choose simple counts/flags and a pre-declared coverage proportion when reliable.
- Document what warning issuance/expiration times represent; avoid using later corrected archive metadata as if it existed Monday.

Red Flag Warnings concern conditions associated with extreme fire danger, **not a guarantee an ignition will occur**: https://forecast.weather.gov/glossary.php?word=red+flag+warning

If historic warning geometry or issue times are too difficult to reconstruct confidently, **skip and log**, do not silently replace with an after-the-fact flag.

### Experiment 3 — Better-timed weather [HIGHEST SCIENTIFIC PRIORITY; NO FUTURE LEAKAGE]

**Hypothesis:** the present seven-day feature lag hides near-term wind/dryness or ignition-relevant weather. Test information that really would have been available at issue time.

Sources:
- Open-Meteo Historical Forecast: https://open-meteo.com/en/docs/historical-forecast-api and `https://historical-forecast-api.open-meteo.com/v1/forecast`
- Previous Runs API and **Single Runs API** docs, accessible through Open-Meteo's documentation. Existing brief reports some historical forecast data from 2018, although the current general provider documentation often describes availability as starting around 2021/2022, depending on model. **Verify exact requested model, variable and date coverage with a small real request.**
- Existing reanalysis: https://open-meteo.com/en/docs/historical-weather-api

**CRITICAL:** A Historical Forecast API timeseries built by stitching **the first hours of successive model runs** is *not* necessarily a seven-day-ahead forecast available on a previous Monday. Never use actual target-week values from that archive as if they were known seven days ahead. For a genuine seven-day evaluation use a dated **issued forecast** (e.g. Single Runs) or explicitly identified lead-time archived Previous Runs values; confirm forecast issue time and spatial/temporal coverage for each row.

Allowed pilot: add better-lagged past conditions (e.g. trailing observations that ended one or two days before Monday) if there was an operationally plausible publication delay, labelled clearly as a **reanalysis approximation / upper bound** rather than strict real-time skill. Do not mix that result with the fully operational headline metric without a caveat.

Useful variables: projected humidity, wind gusts, dry lightning conditions, forecast precipitation, vapour-pressure deficit; test one compact set instead of an unbounded feature search.

### Experiment 4 — Lightning BEFORE prediction [HIGH VALUE IF TRACTABLE]

**Hypothesis:** recent lightning bursts, possibly followed by low precipitation, signal near-term ignitions including holdover fires.

Source: NOAA GOES Geostationary Lightning Mapper (GLM), GLM-L2-LCFA NetCDF files, e.g. https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=GLM-L2-LCFA/ . See https://data.noaa.gov/onestop/collections/details/f028f0b7-d9c6-4c1c-865a-ae88e129d000 and https://goes-r.noaa.gov/spacesegment/glm.html .

- Query a **small, bounded set of actual archived intervals**, not all years or millions of short files.
- Count distinct **flashes**, not events+groups+flashes as separate lightning strikes. Spatially join flash centroids with grid cells; use 1/3/7-day pre-issue counts and nearby-cell counts.
- GLM detects **total lightning**, much of which is cloud lightning and not a verified cloud-to-ground strike. Do **not** claim every flash could ignite vegetation.
- Pre-specified rainfall interaction may distinguish storms accompanying rain from relatively dry conditions.
- If the archive/sample is too large or processing fragile, document the bottleneck and **defer rather than corrupting other deliverables**.

### Experiment 5 — Human physical activity proxies [RESEARCH ONLY UNLESS EASY]

Potentially test **traffic on mountain routes, campground/park visitors or bookings, power-infrastructure exposure** if and only if comparable *historically issued* data are free, granular and practical. One example: Caltrans PeMS archived traffic: https://dot.ca.gov/programs/traffic-operations/mpr/pems-source ; official site says account approval typically takes 1–2 business days, so **do not block unattended progress on it**.

Static present-day road, campsite or power-line maps may leak current infrastructure into older years. Avoid pretending a contemporary OSM map was the state in 2015. If used as an exploratory approximation, disclose this and compare interaction terms against season/location baseline.

The user mentioned geotagged Instagram posts as a *future idea*: **do not scrape Instagram, collect personal posts, circumvent terms, or use identifiable location traces tonight**. It requires separate assessment of access, privacy, representativeness and licensing.

### WFIGS — real-time incident-history source and future test labels

Source: https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0

WFIGS/IRWIN incident records can be updated frequently and are **operational snapshots, not a final QA-corrected copy of FPA-FOD**. Read metadata: https://www.arcgis.com/home/item.html?id=b4402f7887ca4ea9a6189443f220ef28

Before replacing historical FPA-FOD labels/features with WFIGS:
1. Compare overlap years 2015–2024 using matching dates/coordinates/IDs; report duplicates, omissions, late updates, spatial mismatches and changed classifications.
2. Confirm whether incident publication/creation timestamp permits replay of **what was actually known Monday**. A current WFIGS record describing a 2018 fire does not prove it was present in the live feed at the time.
3. For a **new test in 2025**, lock WFIGS label rules beforehand (e.g. `IncidentTypeCategory=WF`, acceptable report states, discovery date conventions); do not include prescribed burns or incident complexes as new wildfires unless justified. Freeze duplicates and match criteria.
4. Do not use the fresh 2025 outcomes to tune or choose features and then report those same outcomes as blind evaluation.

The `EXPANSION_RESEARCH.md` notes ~1,244 wildfire records for 2025 in the original region. This is a **preliminary count, not a verified positive cell-week count**; check original query criteria.

## 4. Experiment plan — autonomous and rigorous

**Do not start by blindly fitting another expensive model.** Work in this order, advancing instantly after each valid checkpoint:

**A. Audit current model and reproducibility**
- Inspect Git branch/status, read existing source and `EXPANSION_RESEARCH.md`, cached original datasets, training scripts, predictions and model outputs.
- Reproduce reported original 2023–24 metrics *from frozen saved predictions only*; log exact counts for ≥0.7 and fixed eight-cell-per-week alerts. Do not retrain or reselect on this used holdout.
- Check time alignment (Monday 06:00 Pacific; local dates versus UTC), whether any target-week data is in features, and whether the positive label includes one or more recorded fires. Check no duplicate incident IDs.
- Produce an audit note explaining what “83.3%” means and a confusion table for the fixed-budget alert rule.

**B. Freeze experiments before reading new held-out scores**
- Preserve original 2015–2020 training and 2021–2022 validation; if features have later start dates, restrict the *training/validation years consistently* and report reduced support.
- Treat 2023–2024 as **used**; don't use it to optimise expanded variants. Use 2021–2022 for comparison/feature selection, or time-respecting rolling validation within the pre-2023 period.
- Declare a **single new final 2025 test** only after source-matching, feature-definition, alert budget and model choices are frozen. Consider leaving 2025 untouched if 2025 weather archives cannot be assembled honestly; a rigorous validation-only result is preferable to contaminated testing.
- For each experiment record `hypothesis → source → time availability → rows/coverage → validation score vs matched baseline → keep/reject`, even if the result is null.

**C. Implement the strongest tractable dynamic predictors first (agent selects and records order)**
1. Audit feasibility quickly and choose **2–4 source families** most likely to finish end-to-end tonight. Do **not** equate more features with better modelling.
2. Strong candidates: issued/past weather that was truly available by Monday; preissued Red Flag Warnings; holiday × human-exposure interactions; preissue GLM lightning + recent rainfall; lagged gridMET fuel moisture / energy-release indices where the release delay can be substantiated.
3. Test each addition with identical splits, geographic coverage, alert budget and feature-availability timestamps. Skip an inaccessible or intractable source promptly; log why.
4. If validation favours new sources, evaluate a small combined model without retrospective cherry-picking. Keep both the best validated candidate and the original baseline reproducible.
5. Cause-specific analyses are optional and exploratory; the main headline still evaluates all reported new ignitions on a complete grid of fire and non-fire weeks.

**D. Train comparable models, avoiding feature sprawl**
- Baseline A = existing season/location model. Preserve a fixed comparable configuration.
- New variants use the same 25-km grid and following-seven-days outcome. Start with existing logistic/gradient boosting, controlled random seeds, identical tuning protocol and same training split.
- Compare **incremental changes one source at a time**, then (if helpful) a combined model selected on validation only.
- Track missingness and the number of cells/dates available for each source; report both full-coverage and restricted matched-subset baseline comparisons when needed. Never make an improvement by quietly dropping hard examples.
- For causes: records with unknown cause are **not negatives** for either cause. Optional exploratory cause-specific models must be evaluated only on correctly labelled subsets with explicit selection caveats; **all-cause test performance remains mandatory**.

**E. Make the next independent test meaningful**
- After freezing one selected candidate from validation, evaluate it exactly once on a 2025 WFIGS-labeled cohort if label coverage and matching are defensible.
- Report number of weeks, eligible cells, positive/negative cell-weeks, actual ignition events, duplicate/unknown handling, any drift between FPA-FOD and WFIGS, and **the same fixed-budget precision for baseline and EMBER**.
- Estimate paired improvement uncertainty by resampling temporal blocks. If interval spans zero, say **“no measurable advantage established”**. Do not try several 2025 tweaks until one looks impressive.

**F. Deliver accessible results to the main EMBER project**
- A robust `forecasting/outputs/` report with `headline_metrics.json`, human-readable `OVERNIGHT_RESULTS.md`, `experiments.md`, saved per-cell/per-week predictions, baseline-versus-model comparison and a static GeoJSON/HTML map.
- Save the fitted model + preprocessing (or reproducible scoring code), provenance manifest, feature schemas and a re-runnable `predict` interface accepting **unseen location/date/input features**.
- For a test-week map, overlay actual ignition events *only after scoring*. Include a clear legend that risk means **at least one reported ignition in a ~25-km cell in the next seven days**.
- Keep code isolated and provide a clean branch/commit + instructions for integration; **do not force merge into main**. If no gain, ship the best honest reproducible model and explain the failed incremental hypotheses.
- Produce one short handover for the pitch writer: **one headline success rate, number of alerts, baseline at the same budget, incremental gain and caveat**; distinct from the retrospective origin-reconstruction model.

## 5. Fail-safe stops and fallback modes

- **Do not spend money even to complete a valuable experiment.** Stop if billing ambiguity, extra-usage notices, account keys, additional credits, external paid tools or new approvals are required. Save and report partial state.
- Source blocked, requires a new account/approval, huge download or unstable API → skip after documenting failure, proceed with next source. Never make fake replacement data.
- New feature improves validation but not independent test → report non-generalisation, don't relabel it a success.
- New model worse than baseline → keep reproducible models/results and report honest negative finding.
- 2025 WFIGS data not comparable with FPA-FOD → **do not report a blind 2025 accuracy number**; deliver validation results and an explicit cross-dataset reconciliation plan instead.
- Depleted included agent allowance → preserve changes, commit if safe, write `RESUME.md` and stop without purchasing tokens.
- No need to use the entire night. When tests are complete, exports are reproducible and results are honest, **finish and hand over immediately**.

## 6. Final response template for the user (plain English)

Give the following at the end, using actual measured values only:

> **What EMBER predicted:** At the start of each week, EMBER selected the 8 of 80 Northern California areas where it expected a new fire within seven days.  
> **Success rate:** X of Y alerts were followed by at least one newly reported wildfire — **Z% correct fire alerts**.  
> **Fair baseline:** With the same eight alerts each week, a simple location/season model was **B% correct**. EMBER's difference was **D percentage points** (95% interval [...]).  
> **How many actual fires it caught:** EMBER's eight areas contained Q of N subsequently reported ignitions (R%).  
> **Validation:** Training years [...], tuning years [...], truly untouched test [...].  
> **What's new:** [named added data source and measured effect]; or **no measurable improvement found**.  
> **Limits:** ~25-km areas / one-week horizon / records can miss fires / no exact-coordinate prediction / historical feature availability caveats.  
> **Where to run it:** branch, commit hash, one-line run command, and output paths.  
> **Spend:** No new paid services, licences or usage were knowingly enabled; if account-level billing cannot be verified, explicitly state so rather than claiming a guaranteed £0 charge.

**Do not report generic “accuracy” as the headline.** A model which predicted no wildfire in every area would score ~83.5% on the original test distribution. The team cares about correctly predicting **fires that happen**, not being rewarded for saying nothing happens.

## 7. Source register

- Existing engineering handover: repository `EXPANSION_RESEARCH.md` (as of 18 Oct 2026, `rayan` branch).
- USFS FPA-FOD: https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_FireOccurrenceCurrentEdition_01/MapServer/0
- NIFC WFIGS incidents: https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0
- IEM NWS warning API: https://mesonet.agron.iastate.edu/api/
- IEM warnings GIS/archive download: https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml
- Open-Meteo Historical Forecast: https://open-meteo.com/en/docs/historical-forecast-api
- Open-Meteo Historical Weather: https://open-meteo.com/en/docs/historical-weather-api
- NOAA GLM metadata: https://data.noaa.gov/onestop/collections/details/f028f0b7-d9c6-4c1c-865a-ae88e129d000
- GOES GLM technical overview: https://goes-r.noaa.gov/spacesegment/glm.html
- Caltrans PeMS access requirements: https://dot.ca.gov/programs/traffic-operations/mpr/pems-source
- Independence Day fireworks-ignition research: https://doi.org/10.1371/journal.pone.0291026

**End-state:** A real-data, operationally interpretable ignition predictor, improved where evidence supports improvement, transparently compared with a seasonal baseline, tested with no target leakage and no additional paid usage. The best result is a **credible result**, not a manufactured percentage.
