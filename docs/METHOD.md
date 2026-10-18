# Technical inference design and limitations

## Independent data and space/time semantics

Satellite thermal detections are *positive evidence of fire* at a pixel's acquisition time. Hotspot centroid coordinates carry pixel-size uncertainty and cannot be treated as observed fire perimeters. Individual nearby pixels from the same overpass are spatially grouped, and separate passes get comparable aggregate weights. The earliest detection timestamp is **not** the ignition time.

Local graph distances are approximated with a tangent equirectangular projection around the early observed clusters (sub-100km incident scale). The observation search grid is built using only clusters and a fixed margin, never the withheld CAL FIRE origin. A cell is ~850m across by default; 8-connected neighbourhoods represent hypothetical routes of spread. A 2018-appropriate elevation or vegetation layer can be sampled separately; absent covariates are neutral and flagged.

Historical wind direction is meteorological **from** convention and is converted into a vector **to** which fire might spread. The MVP averages wind vectors across the early observation window. A temporally dynamic spread model and calibrated fuel propagation are future work.

## Directional, weighted graph

For candidate neighbour cells \(i,j\), let \(d_{ij}\) denote the metric centre separation, \(u_{ij}\) the unit direction vector, and \(\bar w\) the average wind vector (m/s). Let \(g_{ij}=(z_j-z_i)/d_{ij}\) be the uphill grade where elevation is known. With a supplied pre-validated multiplier \(f_{ij}\), relative propagation velocity is

\[
 v_{ij}=\mathrm{clip}\left(v_0\exp\!\left[\beta_w\frac{\bar w\cdot u_{ij}}{10} + \beta_z\mathrm{clip}(g_{ij},-.5,.5)\right]f_{ij},v_{\min},v_{\max}\right).
\]

The graph's directed edge cost is \(T_{ij}=d_{ij}/(3600v_{ij})\) hours. Default nominal hyperparameters are \(v_0=0.4\)m/s, \(\beta_w=0.9\), \(\beta_z=1.5\), with safety clipping at 0.04–3.5m/s. **These are illustrative physical assumptions, not learned, validated or tuned using official origin labels.**

Reverse Dijkstra on transposed edges runs once per observed cluster \(k\) to calculate \(\tau_{ik}\): shortest hypothetical travel time *from* candidate ignition cell \(i\) *to* observed cluster cell \(k\). These travel times are asymmetric in wind and slope.

## Inverse arrival-time objective

Denote earliest cluster observation as time zero. For each cluster \(k\), \(t_k\) is its UTC detection time relative to zero, \(s\le0\) is a candidate ignition time within a fixed 12h lookback, and \(\tau_{ik}\) is model travel time. The predicted arrival is \(\hat t_{ik}=s+\tau_{ik}\).

We minimise a softened one-sided squared hinge objective over admissible \(s\) in 30-minute steps:

\[
L(i,s)=\sum_k w_k\left[\max(0,\hat t_{ik}-t_k-\epsilon_{\mathrm{late}})^2
+\lambda\max(0,t_k-\hat t_{ik}-\epsilon_{\mathrm{early}})^2\right].
\]

Defaults: late grace 0.25h, early grace 2h, \(\lambda=0.08\). Strong penalty for predicted arrival *after* detection, weak penalty when fire might have arrived well before satellite observation. Any prior ignition timing could change these parameters but must be chosen independently of the reference point/time. Correlated satellite pixels are grouped by pass rather than counted as independent sensors.

The score for origin cell \(i\) is \(L_i=\min_s L(i,s)\). Within one parameter scenario we calculate non-calibrated normalised mass

\[
 q_i=\frac{\exp[-(L_i-\min_jL_j)/T]}{\sum_r\exp[-(L_r-\min_jL_j)/T]},
\]

with illustrative temperature \(T=0.9\). We average five scenarios varying base speed by ×0.72, ×1.35 and wind heading by ±20° (plus nominal). The result is a *ranking* and visual uncertainty aid, **not** a calibrated Bayesian posterior. A smallest top-K cell set containing 80 or 90% of score mass is a *support region*. There is no implied 80/90% frequentist true-origin coverage.

## Evaluation and falsifiability

1. Save a hash-identified inference artifact and parameters without ever loading `data/evaluation/camp_fire_reference.json`.
2. Keep all geographic bounds, processing decisions, thresholds and parameter choices unchanged.
3. Only then reveal the reference origin in the evaluation module and compute haversine distance from the highest-scoring cell and earliest observed centroid.
4. Use ablations: isotropic satellite-only graph, wind-aware graph, fusion including actual pre-fire covariates (if present). Report missing covariate coverage as zero. If the full model is worse, report it.
5. Repeat on an independently labelled second/third fire if feasible. One case study cannot show generalisation or provide statistically validated probabilities.
6. Perturb wind, speed and observation grace choices, and compare sensitivity of top-origin locations. The five-scenario ensemble provides a first sensitivity sweep, not a calibrated uncertainty model.

## Infrastructure and lightning: causal firewall

`NEAR_POWERLINE` and `NEAR_LIGHTNING` are optional context edges that connect entities to candidate cells for investigator review. Such evidence is not used as an origin prior because proximity doesn't show a line fault, outage, ignition or liability. Power lines should be dated to the event; current high-voltage data may omit distribution assets. Lightning footprint spatial uncertainty may be very coarse. Only across a large, independently labelled dataset and historical incident-matched infrastructure could we evaluate using those edges as supervised priors.

The CAL FIRE Camp Fire record gives an official 2018 origin and power-line cause. Neither should be used to construct the candidate search extent, model hyperparameters or weather sample location. Published second ignition events and incomplete early satellite overpasses are serious single-source-model limitations.

## Why no GNN, XGBoost, BERT or TuringDB on the inference critical path?

A single labelled wildfire cannot train an origin-localisation GNN or learn reliable XGBoost candidate priors. BERT doesn't match the core data modalities (geography, numerical weather, instrument observations), and pretence of pretrained encoders would degrade rigor. A heterogeneous GNN or temporal attention becomes reasonable after acquiring dozens/hundreds of matched historical fires and a strict by-incident training/validation/test split. The graph representation is *already* a genuine derived mathematical artefact, and reverse graph optimization is a substantive algorithm with a falsifiable baseline. TuringDB is optional for graph querying and provenance, not needed to rank candidates on IBM s390x.
