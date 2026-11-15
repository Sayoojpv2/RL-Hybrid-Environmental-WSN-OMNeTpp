# 7. Final report – strengthened scalability evaluation (v2)

Project: `<USER_HOME>\Documents\OMNeT_Projects\RLHybrid_Scalability_Experiment`. Date: 25 Oct 2026.
Nothing in the RL-Hybrid algorithm, reward, state features, radio-energy model, Periyar workload or frozen MATLAB
benchmark was changed. `SensorNode.*`, the algorithm code, is byte-identical to v1.

## What was run (all completed)
| Item | Runs | Status |
|---|---|---|
| 50-node MATLAB re-validation on the v2 build (separate output dir) | ReferenceCheck, SmokeSeed42, FiveSeeds | 112/112 checks; decision traces identical to MATLAB; 51/51 files byte-identical |
| MATLAB-mode plumbing check | N = 50/100/250/500, run seed 42 | byte-identical to v1 seed-42 runs |
| Channel-stream audit | 2 × 2 export-only runs | overlap measured (below) |
| **Controlled comparison** | Ctrl50/100/250/500 × run seeds 42–46, 1000 rounds | 20/20 completed |
| **Placement sensitivity** | Place250 × 5 relay placements, run seed 42, 1000 rounds | 5/5 completed (second attempt; the first attempt failed at start-up on an ini variable, see 06) |
| Verification | `verify_controlled.py` | 261/261 checks |

## A. Confirmed findings (measured)

1. **The 50-node MATLAB reproduction is intact.** 112/112 checks and byte identity with the archived baseline.
2. **The v1 design mixed placement and run randomness.** One seed set the layout of nodes 1..50, the added relays,
   the channel and the agent.
3. **MATLAB's channel mapping `rng(seed + r)` overlaps between consecutive seeds.** With a fixed topology, run 43 is
   run 42's channel shifted by one round (999 of 999 rounds identical). In the frozen MATLAB benchmark, consecutive
   seeds agree on 93.7 % of link outcomes at that shift (chance level is 65.3 %). The v2 controlled design uses an
   independent mapping. The frozen benchmark is unchanged; its five-seed sd probably understates channel variability.
4. **Controlled comparison (fixed nested topology, independent run randomness, mean ± sd over run seeds 42–46):**

   | | N = 50 | N = 100 | N = 250 | N = 500 |
   |---|---|---|---|---|
   | Scheduled-slot PDR | 38.64 ± 0.86 % | 35.84 ± 1.30 % | 34.12 ± 0.90 % | 31.64 ± 0.55 % |
   | Delivered / emitted | 41.99 ± 0.75 % | 37.60 ± 0.74 % | 35.48 ± 0.65 % | 32.96 ± 0.27 % |
   | Reports delivered / emitted | 3864 / 9205 | 3584 / 9529 | 3412 / 9617 | 3164 / 9597 |
   | Mean delivered hops | 4.31 ± 0.08 | 5.17 ± 0.11 | 5.50 ± 0.20 | 6.04 ± 0.17 |
   | Energy per delivered report | 11.8 ± 0.7 mJ | 14.7 ± 0.5 mJ | 18.4 ± 0.5 mJ | 21.4 ± 0.2 mJ |
   | Residual energy | 54.3 % | 73.7 % | 87.4 % | 93.2 % |
   | Operational nodes at end | 45.6 / 50 | 98.4 / 100 | 248.6 / 250 | 498.6 / 500 |
   | FND (all 5 runs observed at every N) | 581 ± 88 | 805 ± 102 | 815 ± 153 | 814 ± 101 |
   | Wall time / peak memory per run | 2.7 s / 23 MiB | 3.3 s / 23 MiB | 3.8 s / 25 MiB | 4.7 s / 29 MiB |

   * **PDR is lower with more relays at every size, and for every run seed** (paired 5/5 at 100, 250 and 500).
     Paired differences from N = 50: −2.80 ± 1.23 pp at 100 nodes, −4.52 ± 0.46 pp at 250, −7.00 ± 1.23 pp at 500.
   * More reports are *emitted* at larger N, because fewer sources run out of energy. The decline is in delivery,
     not in emission.
   * All losses are channel losses. No-candidate losses are 0; energy and TTL losses are under 2 per run.
   * The controlled 50-node row (38.64 %) differs from the frozen MATLAB five-seed mean (41.02 %) because the layout is
     fixed at MATLAB seed 42. That layout scored 38.77 % in MATLAB too. It is not a reproduction error.
5. **Route behaviour** (`04_routing_diagnostics.md`):
   - Hops and transmissions per delivered report rise (8.2 → 11.8).
   - The **per-transmission success rate barely changes** (0.838 → 0.828), and neither does the mean true link
     quality of chosen hops (0.837 → 0.828). Mean hop distance also stays roughly level (73 m).
   - Loss per hop rises at the first route hop (16.6 % → 22.4 %) and falls on hops close to the BS, which become short
     and reliable (into the BS: 73 m → 21 m, success 0.873 → 0.915).
   - All added relays are selected by the algorithm (50/50, 200/200, 450/450). At N = 500, 83 % of transmissions go to added relays.
   - Feasible candidates per route decision grow roughly in proportion to N (10 → 111).
6. **Placement sensitivity at 250 nodes** (`05_placement_sensitivity.md`): PDR across five relay placements ranges from
   29.65 % to 34.40 % (sd 1.77 pp). This is **larger than the run-seed sd (0.90 pp)**. Of the topology statistics
   tested, only one follows the PDR rank order exactly: the mean distance from a station to its nearest node
   (5.19 m at the best placement, 7.57 m at the worst; Spearman ρ = −1 over 5 placements). With five points this is
   suggestive, not established. Nearest-neighbour distance, largest gap along the river and nodes near the BS do not
   line up. The best placement also had no node failure, so it emitted all 9825 reports.
7. **Corrected FND reporting** (`03_first_unavailability.md`): no controlled run was censored. The v1 100- and 250-node
   FND figures were conditional means over 4 of 5 runs; they are now labelled as such, with the censored runs listed.

## B. Plausible explanation (supported by measurements, not proven by intervention)

The PDR decline is best explained by **longer routes at unchanged per-hop reliability**. The routing mechanism
behind it is most consistent with **learning spread thin across a much larger action space**
(`04b_mechanism_probes.md`):

* **Greedy choices of untried actions.** Untried actions keep Q = 0, and a failed action falls below 0 (reward −1).
  After a failure, greedy selection therefore moves to untried candidates and breaks ties at random among them.
  The share of greedy route decisions that choose a never-tried (node, state, action) rises from **14 % (N = 50) to
  61 % (N = 500)**. Those hops make long jumps (≈ 95 m progress) at low link quality (true LQ ≈ 0.78, success ≈ 0.78).
* **Previously tried greedy hops are reliable but short.** True LQ is 0.85 → 0.90, but progress per hop shrinks from
  66 m to 23 m as N grows. The reward favours successful, reliable hops, and the progress term is small (0.15 ×
  distance/600), so the reinforced choices are short hops when many close neighbours exist.
* The two effects average to about the same per-hop success rate, but more hops per route. Every hop still loses
  about 17 % on average, so more hops means fewer deliveries.
* Minor contributor: cluster heads are chosen upstream of the source more often (32 % → 44 % of member hops). The route
  origin moves only slightly further from the BS (319 m → 325 m).

**Explanations the data do not support:**
- Worse link quality of the chosen hops in general: flat.
- Candidate filtering or a lack of neighbours: candidates grow, and no-candidate losses are 0.
- Energy depletion: fewer sources become unavailable, and energy losses are about 0.
- Added relays being ignored: all are used.

**Correction to v1:** the v1 report attributed the decline to "longer routes, each hop capped at link quality 0.95".
The cap exists, but chosen hops average LQ ≈ 0.83, far below it. The longer routes come from the selection behaviour above.

## C. Unresolved issues and limits
* **Causality is not established.** Confirming the learning-dilution mechanism needs an intervention, for example
  Q-initialisation or tie-breaking variants, or a longer learning horizon. That would change the algorithm, which this
  task forbids, or need a defined extension of the 1000-round Periyar workload. Not done.
* **One placement family.** The N trend comes from one nested placement (layout 42 + relays 900042). Placement
  sensitivity was measured only at N = 250 and only for run seed 42. At 250 nodes the placement spread (range
  4.75 pp) exceeds the 100 → 250 difference (1.7 pp), so that particular step is not robust to placement.
  The 50 → 500 difference (7.0 pp) is larger than the placement range seen at 250, but placement sensitivity at
  50, 100 and 500 was not measured.
* **Frozen benchmark channel coupling.** It is reported, not corrected, because the benchmark is frozen.
* **Coupling for run seed 42.** For run seed 42, the agent stream starts from the same state as the layout-42 topology
  stream, as in MATLAB. Not quantified.
* **Model abstractions.** These are unchanged from MATLAB: no MAC or contention, centralised sequencing, free control
  information, no radio-range limit beyond the qEst ≥ 0.5 candidate rule. Contention would grow with density in a real network.
* **Timing.** Wall times come from one Windows laptop and include writing large CSV traces.

## D. Next steps (none of them tune the algorithm)
1. Repeat the controlled comparison for 2–3 more placement families, nested per family, to test whether the
   monotonic trend holds across placements.
2. Placement sensitivity with several run seeds per placement, giving a two-factor variance decomposition.
3. If the project scope allows a *labelled* algorithm study later, test the mechanism directly, for example with
   optimistic Q-initialisation or a deterministic tie-break, and report it separately from RL-Hybrid.
