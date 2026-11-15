# Stage D – primary benchmark: 250 nodes, seeds 42–46, 1000 rounds

Config `Periyar250_RelayScaling`: 10 real Periyar sources, 240 relay-only nodes (40 original plus 200 added),
fixed 600 × 50 m area, the real workload (10,000 scheduled slots, 9,825 with data), and the unchanged RL-Hybrid.
All five seeds completed 1000 of 1000 rounds. `verify_scaling.py`: **50/50 checks**
(`logs/stageD_Periyar250_RelayScaling_checks.txt`). A seed-42 re-run with the channel export on was
byte-identical in all 10 output files. Its original 50×51 channel block matched MATLAB in all 2,550,000 bits
(`logs/stageDE_full1000_channel_block_checks.txt`).

The 100-node five-seed run (`Periyar100_RelayScaling`, 50/50 checks) and the single-seed 500-node run are
shown alongside for context. Values are mean ± sample sd (n − 1) over seeds. 500 nodes = seed 42 only.

## Definitions
* **PDR** = reports delivered to the BS / scheduled slots (10,000). It is the MATLAB definition.
* **Delivered / emitted**: conditional on the source being available to send.
* **Slots lost: source unavailable**: a valid-data slot whose source station node was already unavailable (energy rules).
* **FND**: first round with fewer than N operational nodes. A seed where no node became unavailable in
  1000 rounds is right-censored. It is excluded from the mean and its count is shown, so the reported
  mean **understates** FND at 100 and 250 nodes.
* **Mean path delay**: the MATLAB definition, Σ over hops of (k/Rbit + Tproc + d/c) for delivered reports.
  **Latency** is OMNeT++ simulated time from round start to arrival at the BS, including the controller's
  sequential phase schedule. It is not comparable with MATLAB.
* **Energy per delivered report** = network energy spent / delivered reports.

## Table
| Metric | Periyar50_Baseline | Periyar100_RelayScaling | Periyar250_RelayScaling | Periyar500_RelayScaling |
|---|---|---|---|---|
| Battery nodes N | 50 ± 0 | 100 ± 0 | 250 ± 0 | 500 |
| Seeds | 42, 43, 44, 45, 46 | 42, 43, 44, 45, 46 | 42, 43, 44, 45, 46 | 42 |
| Scheduled report slots | 10000 ± 0 | 10000 ± 0 | 10000 ± 0 | 10000 |
| Slots with valid data | 9825 ± 0 | 9825 ± 0 | 9825 ± 0 | 9825 |
| Slots lost: source unavailable | 550.0 ± 183.7 | 362.6 ± 268.6 | 218.2 ± 165.2 | 354.0 |
| Reports emitted | 9275.0 ± 183.7 | 9462.4 ± 268.6 | 9606.8 ± 165.2 | 9471.0 |
| Reports delivered | 4102.4 ± 316.9 | 3854.0 ± 414.7 | 3639.4 ± 280.8 | 3214.0 |
| PDR = delivered / scheduled (%) | 41.02 ± 3.17 | 38.54 ± 4.15 | 36.39 ± 2.81 | 32.14 |
| Delivered / emitted (%) | 44.21 ± 2.99 | 40.66 ± 3.26 | 37.85 ± 2.30 | 33.94 |
| Network losses (all causes) | 5172.6 ± 258.2 | 5608.4 ± 178.0 | 5967.4 ± 133.6 | 6257.0 |
|   - channel | 5163.4 ± 249.7 | 5607.6 ± 177.6 | 5966.4 ± 133.7 | 6256.0 |
|   - energy | 3.2 ± 2.4 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 |
|   - no feasible candidate | 5.4 ± 12.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 |
|   - TTL (15 hops) | 0.6 ± 1.3 | 0.8 ± 0.8 | 1.0 ± 0.7 | 1.0 |
| Unattempted reports | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 |
| FND, first round with < N operational | 428.0 ± 128.2 | 664.5 ± 103.0 (+1 seed(s) with none in 1000 rounds) | 787.8 ± 141.1 (+1 seed(s) with none in 1000 rounds) | 741.0 |
| Operational nodes at end | 44.40 ± 1.14 | 98.60 ± 0.89 | 248.40 ± 1.14 | 498.00 |
| Residual energy (J, of 2N J) | 55.55 ± 2.86 | 149.00 ± 3.65 | 438.57 ± 4.25 | 934.10 |
| Residual energy (% of initial) | 55.55 ± 2.86 | 74.50 ± 1.82 | 87.71 ± 0.85 | 93.41 |
| Energy spent (J) | 44.455 ± 2.860 | 51.004 ± 3.649 | 61.428 ± 4.247 | 65.895 |
| Energy per delivered report (J) | 0.01092 ± 0.00145 | 0.01342 ± 0.00220 | 0.01701 ± 0.00227 | 0.02050 |
| Mean delivered hops | 4.34 ± 0.23 | 4.73 ± 0.22 | 5.23 ± 0.18 | 5.87 |
| Mean path delay (s; Σ per hop k/Rbit + Tproc + d/c) | 0.0911 ± 0.0049 | 0.0993 ± 0.0045 | 0.1098 ± 0.0038 | 0.1233 |
| Mean latency round start → BS (s, OMNeT++ time) | 0.558 ± 0.031 | 0.500 ± 0.008 | 0.503 ± 0.009 | 0.532 |
| Q-table updates | 32837.8 ± 1539.7 | 34131.2 ± 819.9 | 35731.0 ± 427.9 | 36325.0 |
| Exploratory decisions | 4165.8 ± 169.2 | 4291.6 ± 93.5 | 4531.6 ± 49.0 | 4630.0 |
| Physical frames | 32421.2 ± 1539.3 | 34022.4 ± 809.0 | 35707.2 ± 426.9 | 36313.0 |

Paired difference Periyar100_RelayScaling − Periyar50_Baseline (seeds 42, 43, 44, 45, 46):
* PDR (pp): -2.48 ± 1.39  (per seed: -2.93, -2.96, -0.01, -3.32, -3.2)
* delivered: -248.40 ± 139.26  (per seed: -293, -296, -1, -332, -320)
* source-unavailable slots: -187.40 ± 251.93  (per seed: -182, -97, -614, -89, +45)
* channel losses: +444.20 ± 113.10  (per seed: +476, +399, +616, +420, +310)
* mean hops: +0.39 ± 0.12  (per seed: +0.3942, +0.4979, +0.3728, +0.4794, +0.2069)
* energy per delivered report (J): +0.0025 ± 0.0011  (per seed: +0.001933, +0.002596, +0.0009794, +0.003606, +0.003364)
* final operational nodes: +54.20 ± 0.84  (per seed: +53, +55, +54, +54, +55)

Paired difference Periyar250_RelayScaling − Periyar50_Baseline (seeds 42, 43, 44, 45, 46):
* PDR (pp): -4.63 ± 0.99  (per seed: -5.07, -6.14, -4.02, -3.65, -4.27)
* delivered: -463.00 ± 99.19  (per seed: -507, -614, -402, -365, -427)
* source-unavailable slots: -331.80 ± 188.25  (per seed: -199, -178, -614, -436, -232)
* channel losses: +803.00 ± 129.21  (per seed: +709, +797, +1017, +799, +693)
* mean hops: +0.89 ± 0.16  (per seed: +0.6785, +1.1, +0.8032, +0.9609, +0.9172)
* energy per delivered report (J): +0.0061 ± 0.0013  (per seed: +0.006372, +0.006347, +0.004154, +0.00591, +0.007681)
* final operational nodes: +204.00 ± 0.71  (per seed: +204, +203, +204, +204, +205)

Paired difference Periyar500_RelayScaling − Periyar50_Baseline (seeds 42):
* PDR (pp): -6.63  (per seed: -6.63)
* delivered: -663.00  (per seed: -663)
* source-unavailable slots: -251.00  (per seed: -251)
* channel losses: +916.00  (per seed: +916)
* mean hops: +1.23  (per seed: +1.227)
* energy per delivered report (J): +0.0082  (per seed: +0.008242)
* final operational nodes: +453.00  (per seed: +453)

Per seed:
* Periyar50_Baseline: seed 42: PDR 38.77 %, delivered 3877, FND 450, final 45; seed 43: PDR 44.84 %, delivered 4484, FND 591, final 44; seed 44: PDR 44.09 %, delivered 4409, FND 386, final 46; seed 45: PDR 38.25 %, delivered 3825, FND 472, final 44; seed 46: PDR 39.17 %, delivered 3917, FND 241, final 43
* Periyar100_RelayScaling: seed 42: PDR 35.84 %, delivered 3584, FND 653, final 98; seed 43: PDR 41.88 %, delivered 4188, FND 799, final 99; seed 44: PDR 44.08 %, delivered 4408, FND -1, final 100; seed 45: PDR 34.93 %, delivered 3493, FND 548, final 98; seed 46: PDR 35.97 %, delivered 3597, FND 658, final 98
* Periyar250_RelayScaling: seed 42: PDR 33.70 %, delivered 3370, FND 594, final 249; seed 43: PDR 38.70 %, delivered 3870, FND 932, final 247; seed 44: PDR 40.07 %, delivered 4007, FND -1, final 250; seed 45: PDR 34.60 %, delivered 3460, FND 804, final 248; seed 46: PDR 34.90 %, delivered 3490, FND 821, final 248
* Periyar500_RelayScaling: seed 42: PDR 32.14 %, delivered 3214, FND 741, final 498

## Runtime and memory (Cmdenv, release build, all seeds of the config in one process; `logs/performance.txt`)

| Config | Seeds | Wall time | ≈ per seed | Peak working set |
|---|---|---|---|---|
| Periyar50_Baseline | 5 | 9.8 s | 2.0 s | 23.4 MiB |
| Periyar100_RelayScaling | 5 | 11.4 s | 2.3 s | 23.8 MiB |
| **Periyar250_RelayScaling** | 5 | **15.1 s** | **3.0 s** | **24.9 MiB** |
| Periyar500_RelayScaling | 1 | 4.2 s | 4.2 s | 28.6 MiB |

About 140–146 thousand events per 1000-round run at every N. The event count barely depends on N,
because traffic is set by the 10 sources, not by the number of relays.

## Differences from the 50-node baseline (paired by seed, 250 − 50)
* PDR: **−4.63 ± 0.99 percentage points**. It is lower for every seed (−3.65 to −6.14 pp).
* Delivered reports: −463 ± 99. Channel losses: +803 ± 129.
* Mean delivered hops: +0.89 ± 0.16 (4.34 → 5.23). Mean path delay: 0.091 → 0.110 s.
* Energy per delivered report: +6.1 ± 1.3 mJ (10.9 → 17.0 mJ).
* Source-unavailable slots: −332 ± 188. Final operational nodes: 44.4 of 50 → 248.4 of 250.
  The first-node-unavailable round moves later (one seed with none in 1000 rounds).
* Q-updates +2,893, exploratory decisions +366. Q-entries are much sparser: see `performance_scalability.md`.

## Interpretation (stated cautiously)
Adding relays gave the agent more candidates strictly closer to the BS, and it built longer routes.
The model caps every link at lq ≤ 0.95, so even very short hops lose at least about 5 % of frames, and every extra
hop is another loss opportunity. This is consistent with channel losses rising with N. Energy per node
falls (the load is shared), so batteries last longer. Fewer sources become unavailable, but that does not
make up for the extra loss per route. The learning signal is also spread over more (state, action)
pairs: at seed 42, the number of distinct pairs tried grows from 5,666 (N = 50) to 16,893 (N = 250).
We have not tested whether that dilution is a cause. **These numbers describe this abstract model under
the fixed Periyar workload; nothing was tuned, and they are not a claim about real deployments.**
