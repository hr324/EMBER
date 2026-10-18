# EMBER forecast expansion: research brief

As of 18 October 2026 · branch `rayan` · code in `forecasting/`

**For the team:** add data-source ideas to [section 7](#7-candidate-data-sources-screened) using the template at its end, and check each idea against the five tests in [section 5](#5-source-screening-tests). Nothing new gets built until the guardrails in [section 6](#6-guardrails-addendum-draft-for-claudemd) are agreed.

---

## 1. Summary

EMBER has a working weekly wildfire-ignition forecast, tested on real data.

- **Headline:** on 2023–2024, which the model never saw in training, the 10% of cells it ranked highest each week held **46.8% of the next week's reported fires**, 4.7× better than random.
- **Confidence:** when the model was highly confident (risk score ≥ 0.7), a fire was reported in that cell within the week **83% of the time**.
- **The catch:** nearly all of that skill comes from *where and when fires usually happen*. Adding weather gave **+1.1 points** over a simple seasonal baseline, **95% CI −0.4 to +3.0**. That is not a measurable improvement.
- **Biggest finding for the expansion:** **0.5% of fires (62 of 11,384) caused 98% of the area burned** in the region from 2015 to 2024. Predicting *which* fires blow up is a different problem from predicting *where* fires start, and it is probably where weather matters.
- **Proposal:** two tracks. Track 1 sharpens ignition prediction with inputs available in real time: same-day weather and Red Flag Warnings, lightning, human activity. Track 2 builds a large-fire ("freak event") model.

---

## 2. What the current model is

| | |
|---|---|
| Question | Will at least one new wildfire be reported in this 25 km cell in the next 7 days? |
| Region | Northern California, 39–41°N, 122.8–120.8°W (includes Butte County). 80 cells of 25 km, 8 × 10, in EPSG:3310 |
| Forecast | Issued every Monday for the next 7 days (Mon–Sun) |
| Label | 1 if ≥ 1 fire in the USFS FPA-FOD database was discovered in the cell that week. 0 means **no fire reported**, not proof that none occurred |
| Inputs | Season (day of year); cell location; fires reported **before** the Monday (30/90/365 days, cell + 8 neighbours); weather windows ending **7 days before** the Monday |
| Never used as inputs | Fire size, cause, containment, anything from the forecast week |
| Training / tuning / test | 2015–2020 / 2021–2022 / **2023–2024, scored once** |
| Output | A risk score per cell per week, used to rank cells. Reasonably calibrated in the upper ranges, but not presented as a probability |

**Data**

- **USFS FPA-FOD 7th edition:** 12,555 fires, 2014–2024 (2014 is used only as history for early-2015 features). All 13,957 records downloaded cleanly, and every discovery date matched its day-of-year field.
- **Open-Meteo historical weather** (ERA5 / ERA5-Land reanalysis): 20 points, one per 2 × 2 block of cells (~50 km), daily from 2014 to 2024, with no missing values. Variables: max/mean temperature, precipitation, mean/min humidity, max wind, max vapour-pressure deficit, evapotranspiration, topsoil moisture.
- **Labels:** 41,680 cell-weeks, 16.1% with at least one reported fire (train 16.3%, validation 15.2%, holdout 16.5%).

**Models compared** (each learned model was tuned on 2021–2022 only)

| ID | Model | Inputs |
|---|---|---|
| A | Seasonal climatology | Each cell's historical fire rate for that time of year (training years only) |
| B | Logistic regression | Season + cell |
| C | Logistic regression | B + weather |
| D0 | Gradient-boosted trees | Season + location + climatology (no weather) |
| D | Gradient-boosted trees | D0 + weather |
| E0 | Gradient-boosted trees | D0 + recent fire history (no weather) |
| E ★ | Gradient-boosted trees | E0 + weather. Headline model: best weather model on 2021–2022 |

---

## 3. Results (2023–2024 holdout)

The holdout covers 104 weeks, 8,320 cell-weeks and 2,569 reported fires.

### 3.1 Headline numbers

| Measure | Weather model (E) | Seasonal baseline (A) | Random |
|---|---|---|---|
| **Share of next week's fires in the top 10% of cells** | **46.8%** | 45.6% | ~10% |
| Share in the top 5% / top 20% of cells | 29.0% / 66.0% | 29.6% / 65.7% | 5% / 20% |
| **Hit rate when highly confident** (score ≥ 0.7) | **83.3%** (449 calls) | 88.0% (276 calls) | 16.5% |
| Share of fire cell-weeks caught by those confident calls | 27.3% | 17.8% | — |
| Hit rate, score ≥ 0.5 | 71.9% (786 calls) | 75.9% (648 calls) | 16.5% |
| Hit rate of each week's top 8 cells, all weeks | 52.4% | 50.8% | 16.5% |
| Same, June–September only | 85.4% | 83.9% | — |
| Same, December–February only | 13.0% | 9.6% | — |
| ROC-AUC / PR-AUC | 0.862 / 0.616 | 0.857 / 0.615 | 0.5 / 0.165 |

**Reading it:** watching the top 10% of the map each week covers about half of new fires, and the top 20% covers about two-thirds. When the model is sure, it is usually right, but it is sure mainly in summer, about places that burn every summer.

### 3.2 All models

| Model | Top 5% | **Top 10%** | Top 20% | PR-AUC | ROC-AUC | Brier |
|---|---|---|---|---|---|---|
| A climatology | 0.296 | **0.456** | 0.657 | 0.615 | 0.857 | 0.0946 |
| B logistic, season + cell | 0.299 | **0.464** | 0.673 | 0.619 | 0.864 | 0.0943 |
| C logistic + weather | 0.299 | **0.463** | 0.668 | 0.616 | 0.864 | 0.0944 |
| D0 trees, season + location | 0.301 | **0.450** | 0.655 | 0.593 | 0.849 | 0.0972 |
| D trees + weather | 0.288 | **0.445** | 0.655 | 0.593 | 0.851 | 0.0972 |
| E0 trees + fire history | 0.296 | **0.462** | 0.656 | 0.615 | 0.861 | 0.0939 |
| E trees + history + weather ★ | 0.290 | **0.468** | 0.660 | 0.616 | 0.862 | 0.0935 |

### 3.3 Did weather help? Matched comparisons

Each row compares two models on exactly the same 104 weeks. The confidence intervals come from resampling whole calendar months, because neighbouring weeks are correlated.

| Comparison | Change in top-10% share | 95% CI | Verdict |
|---|---|---|---|
| C − B (add weather, linear) | −0.1 pt | [−0.4, +0.1] | No gain |
| D − D0 (add weather, trees) | −0.6 pt | [−2.5, +1.1] | No gain |
| E − E0 (add weather on top of fire history) | +0.5 pt | [−0.5, +1.3] | No measurable gain |
| E − A (headline vs baseline) | +1.1 pt | [−0.4, +3.0] | No measurable gain |
| B − A (regression vs climatology) | +0.8 pt | [−0.3, +2.2] | No measurable gain |

### 3.4 Calibration

In the top tenth of cell-weeks by score, model E averaged 0.72 and 70% of those cell-weeks had a reported fire. The climatology averaged 0.65 there, with 69% having a fire. The scores are roughly honest at the top end. They are still labelled as risk scores.

### 3.5 Demo week: 22–28 July 2024 (the Park Fire week)

- The week was chosen by a fixed rule before any score for it was looked at: the holdout week containing the Park Fire's discovery (24 July 2024, Butte County, cell `c04_03`).
- 55 fires were reported that week. The weather model's top 8 cells caught 18 of them; the baseline's caught 19.
- **The Park Fire's own cell ranked 62nd of 80 in the weather model and 50th in the baseline. Neither model flagged it.**
- Use it as an honest example of the limits: the forecast narrows where fires start, but it doesn't anticipate a single ignition that grows to 429,603 acres.

### 3.6 Process note

- During a pipeline test run, before the weather download finished, the four no-weather models (A, B, D0, E0) were scored on the holdout once.
- No setting was changed afterwards. Model choices were made only on 2021–2022.
- **The 2023–2024 holdout should now be treated as used** (see the holdout rules in section 6).

---

## 4. What the results tell us

1. **Where and when explains most of it.** Fire frequency varies about 15-fold across the year (2% of cell-weeks in January vs 32% in July) and from 0.8% to 62% of weeks across cells. A model that knows only the place and the date captures 45.6% of fires in 10% of cells.
2. **Weather lagged by a week adds nothing measurable to ignition prediction.** These are untested explanations, in rough order of likelihood:
   - **The 7-day gap.** The model sees weather that ended a week before the forecast starts. The dry, windy days that matter fall in that gap or inside the forecast week.
   - **People drive ignitions.** Only 43% of fires have a recorded cause. As shares of *all* fires: debris burning 12%, equipment 8%, arson 6%, recreation 2%, power lines 1.5%, lightning 10%. Human activity tracks location and season, which the baseline already knows.
   - **Coarse weather.** One weather point per ~50 km blurs valley vs mountain differences.
   - **Reporting.** Small fires are reported unevenly; label noise caps measurable skill.
3. **Damage comes from very few fires.** 2015–2024 in the region (fire size is used here only to describe the data, never as a model input):

   | Fire size | Fires | Share of fires | Share of area burned |
   |---|---|---|---|
   | ≥ 100 acres | 179 | 1.6% | 99.4% |
   | ≥ 1,000 acres | 62 | 0.5% | 98.3% |
   | ≥ 10,000 acres | 23 | 0.2% | 94.1% |
   | ≥ 100,000 acres | 6 | 0.05% | 76.9% |

   The largest were Dixie (2021, 963k ac), Doe (2020, 589k, lightning), Park (2024, 430k), Claremont (2020, 319k, lightning), Carr (2018, 230k, vehicle), Camp (2018, 153k, power lines), Mosquito (2022, 77k, power lines) and Zogg (2020, 56k, power lines). Causes are as recorded in FPA-FOD; Dixie and Park are listed as undetermined there.
4. **Implication:** "will a fire start here?" is mostly about people and the calendar. "Will it become a disaster?" is mostly about wind, fuel dryness and terrain. They need different models and different data.

---

## 5. Source screening tests

Every candidate data source must pass all five tests.

| # | Test | Why it matters |
|---|---|---|
| 1 | **Available live.** Could we get it on the day we issue a forecast, and how late does it arrive? | The model must work in real time. A source only available weeks later is useless live, and backtesting with it would overstate skill |
| 2 | **Has history,** ideally back to 2015, at least to 2019 | We can only test what we can backtest. Shorter history means a shorter training window |
| 3 | **Free:** no paid plan, licence or API credits | Zero-spend rule |
| 4 | **Local enough:** about 25 km or finer, or can be mapped onto our cells | Coarser data can't separate cells |
| 5 | **Not caused by the fire.** It must exist independently of whether a fire started | Otherwise it leaks the answer (firefighting aircraft, fire hotspots, incident reports) |

Also note for each source:

- **Which track it serves:** Track 1 (will a fire start?) or Track 2 (will it get big?).
- **The lag rule:** how many days to hold it back so the backtest matches what live use would have had.

---

## 6. Guardrails addendum (draft for CLAUDE.md)

All existing CLAUDE.md rules still apply. These are added for the expansion.

**6.1 Available in real time (new)**

- Every input must be obtainable at the forecast's issue time in live operation, with its real delay.
- In backtests, each source is lagged by at least its documented delay. If the delay is unknown, use a conservative lag and document it.
- Each source records `latest_available_date ≤ issue_date − lag` per row, and tests assert it, as now.
- **Fire history in live use needs a live fire feed.** FPA-FOD is compiled once a year, so it can't supply "fires in the last 30 days" live. The candidate is NIFC's WFIGS incident feed (section 7). Its timing and coverage must be checked against FPA-FOD before swapping.

**6.2 Forbidden inputs (anything caused by a fire)**

- Firefighting aircraft tracks and air-tanker activity.
- Satellite fire hotspots (FIRMS/VIIRS/MODIS/GOES fire detections) inside or after the issue time for the fire being predicted. Past hotspots ending before issue time are allowed, with the lag rule.
- Incident reports, evacuation orders, perimeters, final size, cause, containment, and suppression cost for the event being predicted.
- Any "fire weather" product computed *after* the issue date for that date, such as reanalysis reprocessed later. Use it only with the lag rule and say so.

**6.3 Holdout rules**

- **2023–2024 is now a used holdout.** It can be reported for continuity, but not used to choose between new variants.
- **New untouched test year: 2025,** using the WFIGS feed (1,244 wildfire records in our area in 2025). Freeze it now. Nobody looks at 2025 results until a variant is final.
- Variants are chosen on 2021–2022, or by rolling-origin validation within 2015–2022.
- Each new source is a single, pre-declared experiment: state the expected effect, run once, report the result even if it's null.
- Keep a results log in `forecasting/outputs/experiments.md` with one row per experiment: date, variant, validation result, decision.

**6.4 Same yardstick**

- **Track 1 primary metric:** the top-10% share as now, plus the hit rate of high-confidence calls (score ≥ 0.7) and their coverage.
- **Track 1 success bar:** beat the seasonal baseline (45.6%) with a 95% CI excluding zero on the new test year. A gain without that is reported as "no measurable gain".
- **Track 2** gets its own metric (see 8.2), declared before building.

**6.5 Zero spend (unchanged)**

- Free public endpoints only.
- Respect rate limits, cache everything, never upgrade a plan.
- If a source needs a free account or approval, a human applies. The agent never signs up or accepts terms on anyone's behalf.

---

## 7. Candidate data sources, screened

**Status key:**
- ✅ **verified:** a live request on 18 Oct 2026 returned real data.
- 🟡 **partly verified:** reachable, but a key fact (history depth, delay) is still unconfirmed.
- ❓ **unverified:** from memory or from your ideas, needs checking.

### 7.1 Summary table

| Source | What it gives | Live? | History | Free? | Track | Status |
|---|---|---|---|---|---|---|
| **Open-Meteo Historical Forecast API** | Archived weather forecasts as they were issued (short-lead) | Yes | **Values from 2018, not 2017** (bisected: null on 2017-06-01, values on 2018-06-01) | Yes | 1, 2 | ✅ |
| **Open-Meteo Previous Runs API** | The forecast for a day as issued 1–7 days earlier (e.g. `previous_day7`) | Yes | **Values from 2021, not 2019** (null on 2019-06-01, full on 2021-06-01) | Yes | 1, 2 | ✅ |
| **NWS Red Flag Warnings** (Iowa Environmental Mesonet archive) | Official fire-weather warnings: issue/expiry times per forecast office | Yes, as issued | 2015 onward confirmed (Sacramento office: 33 events in 2015, 42 in 2024) | Yes | 1, 2 | ✅ |
| **NIFC WFIGS incident locations** | Near-real-time wildfire incident points, discovery date and time | Yes, updated today (latest 18 Oct 2026, 02:14 UTC) | 2004 onward (107,372 California wildfire records). Our area: 1,011 in 2024, 1,244 in 2025 | Yes | Live fire history; 2025 test labels | ✅ |
| **GOES GLM lightning** (NOAA open data on AWS) | Lightning flashes every 20 seconds, whole Americas | Yes, minutes | GOES-18 files confirmed for July 2024. Earlier years (GOES-16/17, ~2018+) **not yet confirmed** | Yes | 1, 2 | 🟡 |
| **gridMET** (U. Idaho THREDDS) | 4 km daily weather + fire-danger indices (energy release component, burning index, 100/1000-hour fuel moisture) | ~1–2 day delay (to confirm) | 1979 onward | Yes | 1, 2 | 🟡 server reachable; variables and delay unchecked |
| **Calendar: weekends, US holidays, 4 July** | Human activity spikes | Yes | Any | Yes | 1 | ✅ (computable) |
| **OpenStreetMap roads, power lines, campgrounds** (Geofabrik) | Infrastructure exposure per cell | Yes | **Only today's map.** Historical snapshots need the full OSM history | Yes | 1, 2 | ❓ |
| **HIFLD electric transmission lines** | Transmission line routes | Static | Current only | Yes | 1, 2 | ❓ |
| **Utility power shut-offs (PSPS)** | When utilities cut power for fire weather | Announced 1–2 days ahead | ~2019 onward | Probably free (utility/CPUC reports) | 2 | ❓ |
| **Recreation.gov (RIDB) reservations** | Campsite bookings: a visitor-traffic signal | Bookings known in advance | Annual historical files (to confirm) | Free; API key needed | 1 | ❓ |
| **Caltrans traffic counts (PeMS / AADT)** | Road traffic volumes | PeMS live; AADT annual | Years | Free account | 1 | ❓; mostly freeways, thin in rural cells |
| **Flight / visitor traffic** (OpenSky Network) | Aircraft movements as a busyness signal | Live feed free | History needs research approval | Free for research | 1 | ❓ weak signal; regional airports only |
| **MTBS burn perimeters** | Final fire perimeters ≥ 1,000 acres (West) | **No.** Published ~1–2 years later | 1984 onward | Yes | Track 2 **labels only** | ❓ |
| **FIRMS / VIIRS hotspots** | Satellite fire detections | Yes, ~3 hours | 2012 onward (VIIRS) | Yes | Early detection; spread. **Not** an ignition input | Known; see 6.2 |
| **LANDFIRE fuels / vegetation** | Fuel type and load | Updated every few years | Versioned releases | Yes | 2 | ❓ year-matching needed |
| **Terrain (USGS 3DEP DEM)** | Slope, aspect, elevation | Static | n/a | Yes | 2 | ❓ |
| **Population / housing (Census)** | Exposure and ignition pressure | Annual estimates | Yes | Yes | 1, 2 | ❓ |
| **Vaisala NLDN lightning** | Ground-strike lightning, very accurate | Yes | Long | **Paid.** Fails test 3 | — | Rejected |

### 7.2 Notes on the most promising sources

**Weather that was known on the day.** This directly tests our best explanation for the null result.
- **Previous Runs API:** the cleanest option, "what the forecast said N days ahead", but it only starts by 2021. Experiments with it can train on 2021–2022 and test on 2025, which is short.
- **Historical Forecast API:** goes back to 2018. It stores short-lead forecasts (close to what forecasters saw on the day), which supports a "forecast issued Monday for the coming week" design from 2018 onward.
- **Cheap first experiment:** cut the reanalysis lag from 7 days to 1–2 days. Live, near-real-time weather analyses (e.g. NOAA's) exist, so this approximates what an operational version would see. It isn't fully honest for a backtest, because the reanalysis is a later reconstruction. Label it an *upper bound*, not a result.

**Red Flag Warnings.** These are the National Weather Service's own fire-weather judgement, issued ahead of time and archived since at least 2015. Each warning has an issue time, so the lag rule is simple. The region spans several forecast offices (Sacramento confirmed; probably also Eureka, Medford and Reno), and warning zones must be mapped to our cells. This is probably the highest-value Track 2 input.

**Lightning (GOES GLM).**
- **Free and live.** The same files serve the backtest and real-time tracking.
- **Fair input.** Lightning fires often smoulder for days before being reported ("holdover" fires), so strikes from the past few days predict next week's ignitions.
- **Coverage:** Northern California is seen by GOES-West (GOES-17 2019–2022, GOES-18 from 2023) and GOES-East (GOES-16).
- **To do:**
  - confirm archive start dates
  - write a reader for the NetCDF files (flash lat/lon/time → counts per cell per day)
  - check detection quality over Northern California
- **Real-time tracking:** the same pipeline polled every few minutes gives live lightning counts per cell.

**Live fire feed (WFIGS).**
- **Needed for live use regardless.** It provides fire history in real time and gives us an untouched 2025 test year.
- **To do:**
  - match WFIGS against FPA-FOD for 2015–2024 to measure missed or duplicated records and discovery-date differences
  - decide whether to train on FPA-FOD and run live on WFIGS, or switch entirely
- The feed includes cause and size fields. Those are forbidden as inputs (6.2).

**Human activity / visitor traffic** (your idea).
- **Legitimate if known ahead of time:** holidays, weekends, campsite bookings, traffic counts.
- **Flight data is weak:** only regional airports, and it measures arrivals, not where people go.
- **Better proxies:** campsite bookings near cells, traffic on mountain highways, a holiday calendar. The calendar is free and instant and should go first.

### 7.3 Template for new ideas

Copy this block for each idea:

```
### <Source name>
- Link:
- What it measures:
- Live? (how fast after the fact):
- History (from year):
- Free? (account/approval needed?):
- Resolution (spatial / time):
- Could it be caused by a fire? (Y/N, why):
- Track: 1 (ignition) / 2 (big fire) / both
- Why it might help:
```

---

## 8. Two-track plan

```
                    ┌────────────────────────────────────────┐
  inputs known  ──▶ │ Track 1: will a fire START in cell c    │ ──▶ P(ignition)
  at issue time     │ this week?  (people, season, lightning, │
                    │ same-day weather)                       │
                    └────────────────────────────────────────┘
                                                                  ╲
                                                                   ▶  where fires are likely
                                                                  ╱   × how bad they'd get
                    ┌────────────────────────────────────────┐
  inputs known  ──▶ │ Track 2: IF a fire starts in c, will it │ ──▶ P(large | ignition)
  at issue time     │ become LARGE?  (wind, Red Flag, fuel    │
                    │ dryness, terrain, power lines)          │
                    └────────────────────────────────────────┘
```

### 8.1 Track 1: ignition (improve the 46.8%)

Run in order, one experiment each, pre-declared, logged:

| # | Experiment | Data | Expected | Effort |
|---|---|---|---|---|
| 1.1 | Calendar features (weekend count, holidays, 4 July) | none new | Small gain in summer | Hours |
| 1.2 | Red Flag Warnings active or issued for the week | IEM archive | Gain in fire-weather weeks | ~1 day |
| 1.3 | Lightning in the past 1/3/7 days per cell | GOES GLM | Gain on lightning-siege weeks (e.g. Aug 2020) | 2–3 days |
| 1.4 | Same-day forecast weather for the coming week | Open-Meteo Historical Forecast (2018+) | Tests the "7-day gap" explanation | 1–2 days |
| 1.5 | gridMET fire-danger indices (fuel moisture, energy release) | gridMET | Gain where fuel dryness matters | 1–2 days |
| 1.6 | Infrastructure density (roads, power lines) per cell | OSM / HIFLD | Mostly absorbed by location; check | ~1 day |
| 1.7 | Switch live fire history to WFIGS; score 2025 | WFIGS | Needed for real-time use | ~1 day |

**Success bar:** beat 45.6% on 2025 with a CI excluding zero. Report every experiment, including nulls.

### 8.2 Track 2: large fires ("freak events")

- **Question:** given a fire is discovered in cell *c* in week *w*, what is the chance it exceeds 1,000 acres? 10,000 is an alternative to decide.
- **Labels:** FPA-FOD fire size, MTBS perimeters. Size is the outcome here, so it's a legitimate label.
- **Sample size is the main constraint:** 62 fires ≥ 1,000 acres in our region over 2015–2024. That's too few, so **Track 2 must expand to all of California**, and possibly Oregon/Nevada.
- **Inputs:** Red Flag Warnings, wind and humidity forecasts, fuel dryness (gridMET), vapour-pressure deficit, terrain, power-line exposure, PSPS events, lightning, time of year.
- **Metric:** ranking quality among ignitions (PR-AUC for "became large" and the share of large fires among the top-ranked 10% of ignitions), plus area-burned capture, the share of acres from fires the model ranked high.
- **Combined product:** ignition risk × large-fire risk per cell-week, which is roughly expected large-fire risk. The Park Fire becomes a test case: was the conditional risk high that week, even though the ignition wasn't predicted?
- **Honest framing:** with few large fires, Track 2 is about recognising dangerous conditions, not predicting specific disasters.

### 8.3 Real-time pipeline (what live use would look like)

1. **Every few minutes:** pull GOES GLM flashes and add them to per-cell lightning counts.
2. **Daily:** pull WFIGS incidents (fire history), Red Flag Warnings, the weather forecast and gridMET indices.
3. **Monday 06:00 Pacific:** build features with each source's lag rule, score both tracks, and publish the map and API (`/api/forecast`, already built, currently serving backtest predictions).
4. **Logging:** store every live forecast with its inputs so it can be scored later, building a true out-of-sample record.

---

## 9. Open questions and research tasks

**For the team (ideation and access):**
- [ ] Add source ideas to section 7 using the template.
- [ ] Decide the Track 2 threshold: 1,000 or 10,000 acres?
- [ ] Decide the Track 2 region: all of California, or wider?
- [ ] Apply for any free accounts or approvals needed (Recreation.gov API key, PeMS, OpenSky research access). A human must do this.
- [ ] Agree the guardrails in section 6 and copy them into CLAUDE.md.

**For me (verification, before building):**
- [ ] Confirm GOES GLM archive start dates and detection quality over Northern California.
- [ ] Confirm gridMET variables and how quickly new days appear.
- [ ] Match WFIGS vs FPA-FOD for 2015–2024: missed records, duplicates, date differences.
- [ ] Map Red Flag Warning zones to our 80 cells; list every forecast office covering the region.
- [ ] Find exactly where the Historical Forecast and Previous Runs archives start, and which models they use.
- [ ] Check whether historical OpenStreetMap snapshots are practical, or accept today's map with a caveat.

**Open scientific questions:**
- Is the 7-day gap the reason weather didn't help? Experiment 1.4 tests this directly.
- How much of the remaining error is reporting noise? A WFIGS vs FPA-FOD comparison gives a rough ceiling.
- Should forecasts be issued daily instead of weekly for real-time use?

---

## 10. Sources

Checked by live request on 18 October 2026 unless marked.

| Source | Link | Checked |
|---|---|---|
| USFS FPA-FOD 7th edition (MapServer layer 0) | https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_FireOccurrenceCurrentEdition_01/MapServer/0 | ✅ Used for the current model |
| FPA-FOD archive citation | https://doi.org/10.2737/RDS-2013-0009.7 | From CLAUDE.md |
| Open-Meteo Historical Weather API | https://open-meteo.com/en/docs/historical-weather-api | ✅ Used for the current model |
| Open-Meteo Historical Forecast API | https://historical-forecast-api.open-meteo.com/v1/forecast | ✅ Values from 2018 |
| Open-Meteo Previous Runs API | https://previous-runs-api.open-meteo.com/v1/forecast | ✅ Values from 2021 |
| NIFC WFIGS Incident Locations | https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0 | ✅ 107,372 CA wildfire records, 2004–today |
| IEM NWS warnings archive (Red Flag, Sacramento) | https://mesonet.agron.iastate.edu/json/vtec_events_bywfo.py?wfo=STO&year=2024&phenomena=FW&significance=W | ✅ 2015 and 2024 |
| NOAA GOES-18 GLM on AWS | https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=GLM-L2-LCFA/ | ✅ July 2024 files |
| gridMET THREDDS server | http://thredds.northwestknowledge.net:8080/thredds/catalog.html | 🟡 Server reachable only |
| All others in section 7.1 marked ❓ | — | Not yet checked |
