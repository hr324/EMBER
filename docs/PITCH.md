# Three-minute team demo script

**0:00 – 0:25 · Crisis and question**

A wildfire is discovered from orbit, but the first observation may come long after ignition. Where did it begin? Standard fire maps show where it burned, not necessarily where it started. Our goal is to reconstruct a plausible **origin region**, not assign blame.

**0:25 – 0:55 · The data**

Show real timestamped satellite detections and hourly historical wind. State the exact chosen incident, data products and overpass limitations. Before any real-data acquisition, demonstrate in explicitly labelled SYNTHETIC mode only.

**0:55 – 1:35 · Graph innovation**

Each spatial cell is a node. Directional edge weights represent candidate travel times, conditioned on wind and optionally pre-fire terrain and vegetation. We **reverse** shortest-path calculations from detections to candidate origins and search possible ignition times. This produces a ranked surface rather than a fictitious precise point.

**1:35 – 2:00 · Visual detective work**

Slide thermal replay time; switch satellite-only to wind-aware. Wind vector and candidate region shift if supported by actual inputs. Click RUN to demonstrate that inference is actually computed by the backend. Display model-relative support area warning.

**2:00 – 2:25 · Power lines and lightning**

Show separate typed `NEAR_POWERLINE` and `NEAR_LIGHTNING` graph relationships. They are hypotheses, not propagation edges, and they never influence the retrospective candidate ranking in this MVP. The graph can be exported to TuringDB for investigations.

**2:25 – 2:50 · Evaluation and IBM Z**

Reveal withheld label only **after** ranking. Compare top candidate versus earliest-hotspot centroid in km; show ablations and whether the reference falls in predeclared top-score region. Run `uname -m`, Python version, and live `/api/infer` on the actual LinuxONE VM. Do not use synthetic scores as historical results.

**2:50 – 3:00 · Honest closing**

Conclude with caveats: first-pass observation gaps, spread-model assumptions, coarse spatial evidence, and one-fire generalisation. This is transparent retrospective decision support, not proof of who caused a fire.

## Final-hour evidence to record

1. Real dataset filenames, archive dates and downloadable legal sources.
2. Independent satellite passes before modelling; screenshots of map + gate.
3. Predeclared candidate grid and infer artifact SHA256 before reading official label.
4. KM errors, run latency, four-type graph edge count, source versions.
5. Live LinuxONE architecture proof and copy of result.
6. Backup synthetic demo explicitly marked as such.
