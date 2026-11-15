# RL-Hybrid adaptive routing for environmental WSNs: project report

Final snapshot v1.0.0, 15 November 2026. This report summarises the complete software simulation study and points to the
detailed reports and the result files in this repository. All numbers below come from result files in this repository;
the experiment labels (complete, single seed, partial, failed, smoke test) are defined in `docs/EXPERIMENT_STATUS.md`.

## 1. Summary

RL-Hybrid is a routing scheme for battery-powered environmental sensor networks. Each node uses tabular Q-learning
(8 ternary features, 6,561 states, α 0.1, γ 0.9, an ε-greedy schedule) together with a sinkward rule, cluster heads
and aggregation to choose its next hop towards a base station (BS). The project:

1. developed and studied the algorithm in MATLAB (stage 1);
2. reimplemented it in OMNeT++ 6.4.0, proved equivalence with the MATLAB reference, scaled it to 500 nodes, applied it
   to five environmental monitoring scenarios and moved it onto an IEEE 802.15.4 MAC/PHY with INET 4.7.0 (stage 2);
3. proposes a small air-quality sensor network as a hardware demonstration (stage 3, **not implemented**).

The main findings are:

* The OMNeT++ abstract model reproduces the MATLAB reference exactly (112/112 checks, 50 nodes).
* With the MATLAB channel (no retransmission, per-hop loss growing with distance), PDR is about 40-47 % for all five
  scenarios at 200 and 500 nodes, and no node fails within 500 one-hour rounds.
* On an IEEE 802.15.4 MAC/PHY (CSMA/CA, MAC ACK, 3 retries, CC2420 radio values), 200-node PDR rises to
  89.80 ± 0.34 % (5 seeds) because MAC retransmission recovers most single-hop losses.
* At 500 nodes in the same 600 × 50 m area, contention dominates: the one complete 802.15.4 seed reaches 49.84 % PDR.
  The five-seed 500-node wireless experiment is **incomplete** (seeds 43-46 stopped at round 96).
* An event-aware option delivers 94.17 % of critical reports within 2 s versus 0.11 % for the base variant
  (200 nodes, one seed).

These are simulation results under documented assumptions. They compare models and options of the same algorithm;
they do not establish that RL-Hybrid outperforms every existing routing protocol.

## 2. Stage 1: MATLAB algorithm development

RL-Hybrid was designed and studied in a separate MATLAB project (`RL_WSN_Periyar_V2_10Nodes`, not part of this
repository and not modified by it). That work compared RL-Hybrid with conventional routing schemes to understand its
behaviour, strengths and limitations on a Periyar river monitoring scenario. The MATLAB outputs needed to validate the
OMNeT++ port (topologies, workloads, random streams, per-round reference results) were exported into
`matlab_reference/` and the `validation_v*/matlab_reference/` folders.

## 3. Stage 2a: OMNeT++ abstract model and MATLAB equivalence

* Modules: `SensorNode` (RL-Hybrid agent, energy, queues), `BaseStation`, `Controller` (rounds, workload,
  accounting, invariants), `PeriyarModel` (MATLAB channel and energy model), `MatlabRng.h` (MATLAB-compatible random
  streams). Architecture: `docs/ARCHITECTURE.md`.
* Energy: first-order radio model, 2 J per node, node death at 200 µJ (E_elec × 4000 bit).
* Equivalence: the 50-node configuration equals the MATLAB experiment in topology, workload, decisions, deliveries and
  energy; `validate.cmd` runs 112 checks and all pass (`docs/baseline_verification.md`, `validation_v2` … `v11`).
* The 10-node V2 reproduction and its regression runs are in `results_v2_10node*`. One folder is kept with the suffix
  `_INVALID_attempt_carryover_bug` because it documents a bug that was found and fixed.

## 4. Stage 2b: scaling and environmental scenarios (abstract model)

**Relay-density scaling** (`reports_v2/`, `docs/results_250_five_seeds.md`; fixed 600 × 50 m river section, 10 real
sources, added nodes are relay-only; 1,000 rounds, seeds 42-46, mean ± SD):

| nodes | 50 | 100 | 250 | 500 (seed 42 only) |
|---|---|---|---|---|
| PDR | 41.02 ± 3.17 % | 38.54 ± 4.15 % | 36.39 ± 2.81 % | 32.14 % |
| mean delivered hops | 4.34 | 4.73 | 5.23 | 5.87 |
| energy per delivered report | 10.9 mJ | 13.4 mJ | 17.0 mJ | 20.5 mJ |

Adding relays made PDR worse: routes get longer and each hop is another chance of channel loss.

**Environmental scenarios** (`results_environmental/`, `results_environmental_500/`; all N nodes sense and forward,
500 one-hour rounds, seeds 42-46, mean ± SD). Water and air use real KSPCB and UCI Beijing measurements (replayed
for nodes beyond the real stations); effluent and soil are synthetic; mixed combines all four.

| scenario | PDR 200 nodes | PDR 500 nodes | energy / delivered report 200 → 500 |
|---|---|---|---|
| water | 45.26 ± 2.80 % | 43.83 ± 0.98 % | 0.74 → 0.84 mJ |
| industrial effluent | 46.74 ± 1.71 % | 44.71 ± 0.92 % | 0.90 → 1.03 mJ |
| air | 46.88 ± 1.65 % | 45.07 ± 1.12 % | 0.90 → 1.01 mJ |
| soil | 41.93 ± 1.93 % | 40.47 ± 0.50 % | 0.96 → 1.10 mJ |
| mixed | 45.08 ± 1.47 % | 43.45 ± 0.93 % | 0.89 → 1.01 mJ |

No node failed within 500 rounds in any scenario. Full audit: `PROJECT_FINAL_AUDIT.md`.

## 5. Stage 2c: IEEE 802.15.4 model (INET 4.7.0)

`communicationModel = "ieee802154"` runs the same nodes, workload and agent over INET's `Ieee802154NarrowbandMac`
(CSMA/CA, MAC ACK, 3 retries, 4 backoffs, queue of 100) and a scalar radio medium with path loss, noise and
interference. Radio values follow the CC2420 datasheet: 0 dBm TX, −95 dBm sensitivity, CCA −77 dBm, RX 62.04 mW,
TX 57.42 mW, power-down 0.066 mW. One 100 s simulated round represents a 1 h environmental round; identical behaviour
with 3,600 s rounds was verified. Details: `PROJECT_RESEARCH_UPGRADE_REPORT.md`.

**200 nodes, mixed, variant C, 500 rounds, seeds 42-46 (complete):**

| metric | abstract | IEEE 802.15.4 | paired difference [95 % CI] |
|---|---|---|---|
| PDR | 45.08 ± 1.47 % | **89.80 ± 0.34 %** | +44.72 [+42.74, +46.70] points |
| mean delivered hops | 5.41 ± 0.22 | 7.66 ± 0.12 | +2.25 [+1.86, +2.64] |
| 2 J ledger spent (of 400 J) | 29.35 ± 1.11 J | 24.29 ± 0.23 J | −5.06 [−6.41, −3.71] J |
| energy per delivered report (ledger) | 0.888 ± 0.032 mJ | 0.369 ± 0.004 mJ | −0.519 [−0.558, −0.481] mJ |
| end-to-end delay mean / p95 | not modelled | 3.058 s / 3.965 s | - |
| first node failure | none | none | - |

Why the models differ: the abstract (MATLAB) channel draws each hop outcome from a distance-based link quality with no
retransmission, so a 5-hop route loses about half its reports. On 802.15.4 a hop within the ~102 m radio range
succeeds 98-100 % of the time thanks to CSMA/CA, MAC ACK and retries; a hop beyond it always fails.

**Options and sensitivity (200 nodes, seed 42 only):**

* Event-aware option: critical reports delivered within 2 s rose from 0.11 % to 94.17 %; PDR 94.30 %.
* MATLAB link prior instead of the link-budget prior: PDR 78.71 % vs 89.51 %. The agent first tries links that do not
  exist on 802.15.4.

**500 nodes, mixed, variant C, fixed area (incomplete experiment):** seed 42 ran all 500 rounds (5.37 h, 168.7 MB
peak) and passed every accounting check. PDR was 49.84 % vs 44.54 % for the abstract run of the same seed. 2.5 times
more nodes contend in the same decision windows: 36.5 % of transmissions got no MAC ACK, 34,398 frames hit the retry
limit, 38,565 failed channel access, routes grew to 7.05 hops and 8,505 reports exceeded the TTL. Seeds 43-46 were
stopped at round 96 of 500 when the project was frozen; they are kept as partial runs and are not used. With one seed
there is no spread or confidence interval.

## 6. MAC fault handling (workaround and limits)

INET 4.7.0's 802.15.4 MAC can silently drop a frame: a frame arriving while the receiver's MAC is transmitting is
discarded after its sequence number is recorded, and the sender's retransmission is then ACKed as a duplicate but never
delivered. The sender's routing layer therefore never learnt the outcome, and the original code stopped the run.
Seeds 43 and 45 (200 nodes) failed this way; the fault was reproduced deterministically at the same event.

The workaround, in `SensorNode.cc`: when no routing answer arrives within `wirelessAckTimeout` (1 s), the hop is
counted as lost (`framesLostNoOutcome`), and routing answers are matched to their frame by `txSeq` so late answers are
ignored (`staleLinkAcks`). INET itself is unchanged. The failed runs are kept in `results_research_upgrade/failed_runs/`;
the reruns equal them up to the fault. The event is rare (2 hops in 5 runs of 200 nodes, 0 in the 500-node run), but it
is a model limitation: a real receiver would deliver such a frame or the sender would see a failure.

## 7. Energy accounting: four separate quantities

These are never added together:

1. **Abstract-model energy:** the MATLAB first-order radio model charged in the abstract configurations.
2. **2 J reference ledger (802.15.4 runs):** the same first-order model, charged once per MAC transmission that actually
   starts (retries included; refunded if the frame never reached the air) and once per accepted frame. It is used for
   node death and comparability with the abstract model.
3. **CC2420 radio-state energy:** measured from INET radio states (RX, TX, idle listening, power-down), reported per
   node-round, with duty-cycled and always-listening extrapolations to the 1 h round. Not charged to the 2 J ledger.
4. **Sensing energy:** a separate estimate from sensor profiles (`*-sensing_ledger.csv`), largely assumption-based,
   never charged to the radio battery.

Reported lifetimes are therefore communication-network lifetimes, not physical battery lifetimes.

## 8. Limitations

* All results are from simulation; no hardware was built or measured.
* 500-node 802.15.4: one complete seed only; the fixed-density layout and longer decision windows were not run at
  500 rounds.
* 802.15.4 was run only for the mixed scenario; water, effluent, air and soil were not run on it.
* The event-aware option and the MATLAB-prior sensitivity have one seed each.
* Routing feedback (receiver answer, energy, next-hop value) reaches the sender out of band rather than as airtime; a
  feedback-airtime configuration (`W_FeedbackAck`) exists but was not run.
* Replayed water and air nodes are virtual sensors repeating real station streams; effluent and soil data are synthetic.
* The INET MAC fault is handled by a timeout rather than fixed inside INET.

## 9. Conclusion

The project delivers a working, validated OMNeT++ implementation of RL-Hybrid. It is exactly equivalent to the MATLAB
reference in the abstract configuration, scales to 500 nodes and runs five environmental workloads. A wireless
extension shows that realistic MAC behaviour changes the picture substantially: retransmissions lift 200-node delivery
to about 90 %, and contention pulls a dense 500-node network back to about 50 %. The remaining wireless experiments
and the hardware demonstration are listed in `docs/RESEARCH_ROADMAP.md`.

## 10. Detailed documents

| Document | Content |
|---|---|
| `PROJECT_RESEARCH_UPGRADE_REPORT.md` | IEEE 802.15.4 implementation, configuration, results, bugs, limitations |
| `PROJECT_FINAL_AUDIT.md`, `PROJECT_AUDIT_ISSUES.csv` | audit of the abstract environmental study |
| `scenario_study/` | scenario catalogue, dataset provenance, sensor profiles, feasibility |
| `docs/final_report.md`, `docs/results_250_five_seeds.md`, `docs/performance_scalability.md` | scaling study |
| `docs/DEVELOPMENT_README_history.md` | the development README before this release |
