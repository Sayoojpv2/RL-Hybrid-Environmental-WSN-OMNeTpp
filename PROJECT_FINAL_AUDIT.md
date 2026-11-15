# Project final audit: RL-Hybrid environmental WSN (OMNeT++ 6.4.0)

Audit: 12 Nov 2026, followed by a final validation and cleanup the same day. Project: `RLHybrid_Scalability_Experiment` (OMNeT++ 6.4.0, Windows 11, MSYS2 clang64, no INET).
The issue register is `PROJECT_AUDIT_ISSUES.csv` (17 issues). Every test below was run in this audit or in the final validation.

**Readiness: Ready with limitations** (section 17).

## 1. Project overview

One configurable heterogeneous environmental WSN:

- 200 nodes (the validated reference) or 500 nodes (the expansion), both evaluated over five seeds (42–46).
- Five monitoring scenarios and one RL-Hybrid routing implementation (tabular Q-learning, Variant C energy guard 0.8), with no retransmission.
- One sensor-specific packet model and a separate sensing-energy ledger.

The original MATLAB-equivalent 10-node and 50-node models and the 50–500-node scalability studies are unchanged.

**Protection:**

- **SHA-256 snapshots:** `archive/audit_2026-11-12/SHA256_protected_before.txt` (audit, 2,865 files) and `archive/final_2026-11-12/SHA256_before.txt` (final validation, 3,440 files).
- **Backups of every modified file:** `archive/audit_2026-11-12/before/` and `archive/final_2026-11-12/before/`. They are stored as `*.bak`, so neither the NED loader nor the Makefile sees them.
- **Previous environmental results:** `archive/audit_2026-11-12/results_environmental_before_frame_fix/` (moved, all 340 checksums verified).

**After the final validation, unchanged:** the datasets, MATLAB, the KSPCB workbook (both copies, SHA-256 6100b728…), the sensor profiles, the validation reports and every historical result folder.

**Changed, all intentional:**

- the edited scripts and documents;
- the regenerated analysis tables and graphs;
- the appended 500-node runtimes;
- five soil `.sca` files rewritten by the `run.cmd` test (new run timestamps; their csv/txt outputs are byte-identical).

The project folder is not a git repository. Nothing was committed or pushed.

## 2. Final architecture

| Item | Implementation |
|---|---|
| Configuration | `[Config V2_200Node_Environmental]` (extends `V2_200Node_Common`). Iteration variables: `N` = 200, 500; `scenario` = water, effluent, air, soil, mixed; `seed` = 42..46 (50 runs). |
| Nodes | `node[N]` (`SensorNode`, node id = index + 1). Every node generates reports and every node can forward; there are no relay-only nodes. Checked: N of N nodes report and N of N relay in all 50 runs. |
| Base station | One `BaseStation` at (600, 25) m, id N + 1, area 600 × 50 m. |
| Topology | Nodes 1–10 are the MATLAB `generate_scenario(seed)` station positions; nodes 11..N come from stream 900000 + seed. The same seed gives the same topology in every scenario, and the first 200 nodes of N = 500 are the 200-node layout of that seed. Positions are unique, inside the area and never at the BS. |
| Rounds | 500 rounds = 500 h of environmental time. Each round occupies a 100 s OMNeT++ scheduling slot, and a slot overrun raises an error. |
| Radio battery | 2 J per node, first-order radio model, report-preserving aggregation, node-death rule E < E_elec × 4000 bit = 200 µJ (unchanged). |
| Sensing energy | A separate estimate (`<prefix>-sensing_ledger.csv`), never charged to the radio battery. |
| Routing | RL-Hybrid as validated, with Variant C (`energyGuard 0.8`) and no retransmission. |
| Workload | `data/scenarios/<profile>_<N>/observations.csv`, or `mixed_environment_<N>/node_map.csv`. |

## 3. Source-code audit

- **Build:** `build.cmd` builds this project only (0 warnings, 0 errors). INET and the workspace were not touched.
- **NED and ini:** all 59 NED parameters are read by the C++ code, and every ini key is declared in NED. One NED file is loaded.
- **Indexing:** the node vector size, the BS id (n + 1) and the action count (n + 1) all come from `numNodes`. `MATLAB_NODES = 50` is used only to draw the MATLAB reference layout. The Q key is at most 6,561 × 501 for N = 500.
- **Code fixes during the audit:**
  - per-report frame bits from the dataset (AUD-02);
  - `scenarioDataset` accepts a dataset folder (AUD-03);
  - 500-node support (AUD-01).

  All three are inactive unless `scenarioDataset` and `scenarioFrameBits` are set.
- **Final validation:** no C++ change was made.
- **Scripts:**
  - `run.cmd`, `build.cmd`, `validate.cmd` and `ide_headless_build.cmd` require `OMNETPP_ROOT` and stop with a clear message if it is missing or wrong.
  - `tools/run_measured*.ps1` default to `$env:OMNETPP_ROOT`.
  - All of this was tested: unset gives exit 1, a wrong folder gives exit 1, and a valid folder lets `run.cmd … soil 200` reproduce its runs byte for byte.

## 4. RL-Hybrid and Q-learning audit

| Element | Finding |
|---|---|
| State | 8 ternary features (own energy, candidate energy, distance, candidate load, link quality, progress, past reliability, remaining hops), giving 3^8 = 6,561 states. The index is asserted to lie in 1..6561. |
| Actions | Nodes 1..n plus the BS (n + 1); the action space scales with N. |
| Q-table | Sparse `unordered_map`. Entries per node: 139–271 at 200 nodes and 182–385 at 500 nodes (five-seed means). |
| Learning | α = 0.10, γ = 0.90. ε starts at 0.25, is multiplied by 0.9985 each round and has a floor of 0.05. Initial Q is 0. |
| Update | After the ACK or feedback, using the next hop's max Q (BS terminal). Q updates = routing decisions in every run. |
| Candidates | Each candidate must be alive, unvisited, strictly closer to the BS and have link quality ≥ 0.5. Energy feasibility uses the actual frame. Variant C then drops candidates below 0.8 × the candidates' mean energy. |
| Loops and hops | The visited list plus the sinkward rule prevent loops. TTL is 15 hops. A safety check on the chosen next hop never fired. |
| Accounting | Per-round invariants, energy closure and slot accounting are enforced in every run, and all 50 runs pass. |

The learning equations, reward, Variant C rule and node-death threshold were not modified.

## 5. Five environmental scenarios

| Scenario | Transmitted fields | Read locally only | Schedule | Data (real / replayed / synthetic) |
|---|---|---|---|---|
| Water | temperature, pH, conductivity, TDS | DO (for the DO < 4 mg/L alarm) | report every 2 h; alarm reports hourly | real KSPCB Periyar, 10 station streams (nodes 1–10); replayed on the other 190 / 490 nodes |
| Effluent | temperature, pH, conductivity, TDS, DO and turbidity where valid, COD, BOD, NH3-N | – | hourly | synthetic (20 virtual outfalls) |
| Air | PM2.5, PM10, CO, NO2, SO2, O3, temperature, RH, wind speed | – | hourly | real UCI Beijing, 12 station streams (nodes 1–12); replayed on the other nodes |
| Soil | moisture, soil temperature, bulk EC; pH, N, P, K on chemistry rounds | – | every 4 h; chemistry every 24 h; alarm reports hourly | synthetic (10 virtual fields) |
| Mixed | each node keeps its own profile | water nodes: DO | each node keeps its own profile | 50 / 125 nodes per profile; nodes 1–10 are always the real water stations |

Replayed nodes are virtual sensors that repeat a real station stream. The network has 10 real water stations and 12 real air stations, not 200 or 500.

## 6. Dataset and provenance audit

**Validator:** `validate_scenarios.py` was run for N = 200 and N = 500, in the audit and again in the final validation. All 10 reports pass, including byte-identical regeneration of every dataset and of `SENSOR_PARAMETER_MATRIX.csv`. Its checks cover:

- row counts, node ids, unique sample ids, no duplicate (node, round) rows, rows ordered by round;
- units, valid ranges and 16-bit encodability;
- missing values as empty cells explained by `quality_flag`, never 0;
- real / replayed / synthetic labels and the station mapping;
- replay nodes identical to their station node;
- water rows identical to the validated 200-node workload;
- alarm flags, the reporting schedule (periodic, alarm, chemistry) and every `m2_sensing_mJ` value recomputed from `sensor_profiles.json`;
- payload and frame formulas, and the mixed manifest (50 or 125 per profile).

**Water DO, resolved (AUD-04):** the water profile intentionally measures DO locally.

- Evidence:
  - `sensor_profiles.json` defines DO as a water extension field with the CPCB alarm DO < 4 mg/L.
  - The generator computes the water alarm flags from DO.
  - At 200 nodes, the DO alarm alone raises 3,060 alarm rows and 1,560 of the 68,700 water reports.
- DO is not transmitted, for two reasons:
  - The water payload keeps the MATLAB V2 four-field workload (temperature, pH, conductivity, TDS).
  - The KSPCB loader's DO column needs a preprocessing review: 328 of 1,273 records are above 20 mg/L, a unit or extraction error.
- The DO probe's energy therefore stays in the sensing ledger and is reported separately as local-only sensing energy. The original DO data, the datasets and the historical results are unchanged.
- One limitation remains: an alarm raised by DO does not carry the DO value.

**Turbidity:** the KSPCB workbook's Turbidity rows hold 1,654 `*` cells and 35 `A` cells, and no numeric value. Water turbidity therefore stays excluded and nothing is fabricated (AUD-07).

## 7. Sensor-energy audit

**Formula:** V × mA × ms = µJ.

- Per-sample loads are multiplied by `samples_per_round`.
- Continuous loads (ms ≥ 1 h) are counted once per 1 h round.
- Chemistry loads are counted only on chemistry rounds.
- The MCU costs 3.3 V × 5 mA × 10 ms per sample.

The ledger is counted per operational node-round (all node-rounds were operational in every run) and is never charged to the 2 J radio battery.

| Profile | Per node per round | Dominant terms (class) | Per node, 500 h |
|---|---|---|---|
| Water | 609.5 mJ = 411.5 transmitted-field sensors + 198.0 local DO probe | pH and EC interfaces at 198 mJ each and the DO probe at 198 mJ (ASSUMPTION, 15 mA × 1 s × 4); DS18B20 14.9 mJ (VERIFIED) | 304.8 J (DO probe 99.0 J) |
| Effluent | 241.8 J | COD/BOD UV-Vis probe 240 J (ASSUMPTION, 99.3 %) | 120.9 kJ |
| Air | 107.6 J | PMS5003 60 J (VERIFIED active current); 4 gas-sensor ISB boards 47.5 J (1 mA continuous each, ASSUMPTION) | 53.8 kJ |
| Soil | 15.3 mJ (chemistry rounds 1.01 J) | moisture/temperature/EC probe (ASSUMPTION); chemistry pH and NPK every 24 h (ASSUMPTION) | 28.6 J |

**Network ledger** (five-seed means, kJ):

| | Water | Effluent | Air | Soil | Mixed |
|---|---|---|---|---|---|
| 200 nodes: total | 60.95 | 24,180.55 | 10,763.95 | 5.72 | 8,752.79 |
| 200 nodes: local DO probe | 19.80 | 0 | 0 | 0 | 4.95 |
| 500 nodes: total | 152.38 | 60,451.38 | 26,909.87 | 14.31 | 21,881.98 |
| 500 nodes: local DO probe | 49.50 | 0 | 0 | 0 | 12.38 |

**Remaining energy limitations:**

- No standby or sleep current is modelled (AUD-05).
- The dominant terms are assumptions (AUD-06).
- A node's hourly sensing energy (up to 241.8 J for effluent) exceeds its whole 2 J radio battery.

The lifetimes reported are therefore communication-network lifetimes, not physical battery lifetimes.

## 8. Radio and packet-model audit

| Profile | Application payload | Complete frame | Actual frames per report, 200-node data |
|---|---|---|---|
| Water | 144 bit | 280 bit | 280: 68,700 |
| Effluent | 224 bit | 360 bit | 360: 97,489; 344: 1,802; 328: 15 |
| Air | 224 bit | 360 bit | 360: 97,356; 344: 2,356; 328: 170; 312: 17; 296: 17; 264: 84 |
| Soil | 128 bit | 264 bit | 264: 20,969 |
| Soil chemistry | 192 bit | 328 bit | 328: 4,166 |

**Frame structure:**

- Frame = 17 B IEEE 802.15.4 MAC/PHY + payload, where the payload is a 10 B header plus 2 B per present field.
- Payload and frame are kept distinct (payload = frame − 136 bit). The largest frame is 45 B, below the 127 B maximum PSDU.

**Actual sizes everywhere:**

- Each report is charged its own dataset frame (`scenarioFrameBits = "dataset"`).
- TX, RX and aggregation energy, energy feasibility, airtime (Σ bits / 250 kbit/s) and the ACK timeout all use the actual bits of the reports carried.
- No average or minimum size is used; the 4000-bit value appears only in the node-death rule.

**Approximation (AUD-13):** an aggregated route frame is sent as back-to-back 802.15.4 frames with one ACK. There is no CSMA/CA, inter-frame spacing, per-frame ACK, collision or queue, and loss does not depend on frame length.

## 9. 200-node validation

**Protected regressions:**

| Test | Audit | Final validation |
|---|---|---|
| MATLAB V2 10-node, seeds 42–46 (`compare_v2.py`) | 95/95 | **95/95**. 60/60 csv/txt byte-identical; 133/133 scalars per seed identical (module `n<k>` → `node[k-1]`). |
| MATLAB 50-node (`validate_v2.sh`; `VALDIR` = `validation_v9` in the audit, `validation_v10` in the final validation) | 112/112 | **112/112** (22 + 11 + 4 + 20 + 55). 51/51 baseline files byte-identical. |
| 200-node Variant C final, seed 47 | 10/10 identical | not rerun (no C++ change since the audit) |
| 250-node controlled scalability (`Ctrl250`), seed 42 | 12/12 identical | not rerun (no C++ change since the audit) |
| 200-node environmental results | 25 runs rerun after the frame fix | seed 42, all 5 scenarios: **55/55 files byte-identical**; soil seeds 42–46 reproduced byte for byte through `run.cmd` |

**200-node results** (five seeds 42–46, mean ± sample SD): see section 10.

## 10. 500-node validation and 200-versus-500 comparison

**500 nodes:**

- Smoke tests: all five scenarios at 20 rounds passed.
- Five seeds × five scenarios = 25 full runs.
- Seed 42 was reused after its configuration was verified (parameter check of every run, plus a byte-identical repeat of water seed 42).
- Seeds 43–46 are new.

All analysis checks pass:

- exactly 500 node modules and one BS;
- all nodes report and relay; mixed has 125 per profile;
- same topology per seed across scenarios, with the first 200 nodes equal to the 200-node layout;
- same schedule in every seed;
- every frame equals its dataset row;
- energy closure.

**Reproducibility:** both repeated 500-node runs (mixed seed 42 in the audit, water seed 42 in the final validation) are byte-identical, csv/txt and scalars.

**Five-seed means ± sample SD** (200 nodes: seeds 42–46; 500 nodes: seeds 42–46). This table is `results_environmental_500/comparison_200_vs_500.csv`.

| Scenario | N | Delivery ratio % (= source-packet PDR) | Delivered | Residual radio J | Residual % of initial | mJ per delivered | Delay ms | Transmitted Mbit | Runtime s | Peak MB |
|---|---|---|---|---|---|---|---|---|---|---|
| Water | 200 | 45.26 ± 2.80 | 31,096 ± 1,925 | 377.2 ± 0.6 | 94.30 ± 0.16 | 0.736 ± 0.055 | 35.53 ± 1.68 | 79.1 ± 2.3 | 4.4 ± 0.2 | 62 |
| Water | 500 | 43.83 ± 0.98 | 75,273 ± 1,690 | 936.5 ± 1.0 | 93.65 ± 0.10 | 0.844 ± 0.023 | 41.11 ± 1.28 | 207.9 ± 3.3 | 25.7 ± 2.4 | 116 |
| Effluent | 200 | 46.74 ± 1.71 | 46,416 ± 1,700 | 358.1 ± 1.2 | 89.52 ± 0.30 | 0.904 ± 0.046 | 41.01 ± 1.18 | 154.2 ± 3.7 | 6.7 ± 0.4 | 71 |
| Effluent | 500 | 44.71 ± 0.92 | 110,914 ± 2,278 | 885.5 ± 2.0 | 88.55 ± 0.20 | 1.033 ± 0.026 | 48.79 ± 1.46 | 416.1 ± 7.1 | 39.6 ± 4.1 | 148 |
| Air | 200 | 46.88 ± 1.65 | 46,875 ± 1,646 | 358.0 ± 0.7 | 89.51 ± 0.17 | 0.896 ± 0.034 | 40.41 ± 1.87 | 153.7 ± 4.4 | 6.4 ± 0.2 | 63 |
| Air | 500 | 45.07 ± 1.12 | 112,684 ± 2,810 | 885.8 ± 1.3 | 88.58 ± 0.13 | 1.014 ± 0.027 | 47.80 ± 1.61 | 413.6 ± 6.5 | 37.4 ± 3.8 | 128 |
| Soil | 200 | 41.93 ± 1.93 | 10,539 ± 485 | 389.9 ± 0.2 | 97.48 ± 0.04 | 0.959 ± 0.055 | 33.76 ± 0.84 | 25.2 ± 0.3 | 1.8 ± 0.1 | 49 |
| Soil | 500 | 40.47 ± 0.50 | 25,487 ± 313 | 971.8 ± 0.6 | 97.18 ± 0.06 | 1.105 ± 0.025 | 38.90 ± 1.77 | 66.0 ± 1.6 | 7.3 ± 0.4 | 92 |
| Mixed | 200 | 45.08 ± 1.47 | 33,046 ± 1,078 | 370.7 ± 1.1 | 92.66 ± 0.28 | 0.888 ± 0.032 | 38.68 ± 1.41 | 103.9 ± 3.3 | 5.5 ± 0.1 | 65 |
| Mixed | 500 | 43.45 ± 0.93 | 79,408 ± 1,706 | 920.1 ± 1.2 | 92.01 ± 0.12 | 1.007 ± 0.028 | 43.12 ± 1.23 | 266.1 ± 3.5 | 30.1 ± 3.9 | 123 |

**Generated reports** (identical in every seed):

| | Water | Effluent | Air | Soil | Mixed |
|---|---|---|---|---|---|
| 200 nodes | 68,700 | 99,306 | 100,000 | 25,135 | 73,306 |
| 500 nodes | 171,750 | 248,086 | 250,000 | 62,984 | 182,752 |

**Lifetime metrics** at both sizes, in every scenario and seed:

- Operational nodes at round 500 = N.
- Cumulative operational node-rounds = N × 500 (100,000 or 250,000).
- First-node and half-node failure are not reached.

**Effect of going from 200 to 500 nodes** (same area, BS, radio, routing and per-node workload):

- Delivery falls by 1.4–2.0 points.
- Paths grow by 0.6–1.0 hop, so delay rises by 4–8 ms and energy per delivered report by 13–15 %.
- Residual energy as a share of the initial energy falls by 0.3–1.0 point.

The runtimes and peak memory for 200 and 500 nodes were measured in different sessions, so compare them only roughly.

## 11. Scalability and runtime audit

| | 200 nodes (5 seeds) | 500 nodes (5 seeds) |
|---|---|---|
| Runtime per run | 1.8–6.7 s | 7.3–39.6 s (seed means per scenario) |
| Peak memory | 49–71 MB | 92–148 MB |
| Output per run | 5.5–25.7 MB | 13.7–64.5 MB |
| Routing decisions = Q updates | 70 k – 319 k | 184 k – 856 k |
| Q-table entries | 28 k – 54 k | 91 k – 192 k |
| Longest round (of 100 s) | 6.0 s | 15.4 s |

**Efficiency checks:**

- Decision and channel logs are off.
- Each dataset is read once per run, and node lookup is O(1).
- There are no MAC queues; candidate search is O(n) per decision.
- Peak memory scales with N and offered load. Only the peak working set was measured; no leak checker was run.

The 25-run 500-node batch needs about 12 minutes of run time (700 s in total). Contention, collisions and queues are not modelled, and no claim to the contrary is made.

## 12. Results and graph audit

**Final graph sets:**

- `results_environmental/figures/` (200 nodes, five seeds): eight graphs.
- `results_environmental_500/figures/` (500 nodes, five seeds): the same eight, plus two comparison graphs:
  - `fig9_200_vs_500.png`: delivery ratio, residual %, energy per delivered report, delay;
  - `fig10_200_vs_500_cost.png`: transmitted bits, runtime, peak memory.

  Both show mean ± sample SD over five seeds for each size.

**Checks on the analysis script (`tools/environmental_200node.py --nodes 200|500`):**

- It reads only run outputs and the datasets, and verifies every run's parameters.
- Denominators: delivery ratio = delivered / generated (= scheduled = valid reports); source-packet PDR = delivered / reports emitted by operational sources.
- For 200 versus 500 it reports residual energy both in J and as a share of 2 J × N.
- Real, replayed and synthetic data are separated in `fig8` and in the data-class tables.
- Bars start at zero, different units use separate panels, and there are no dual axes.

**Retired material:** the M1 / M2T / M2F graphs in `results_multi_scenario/` and the pre-fix 200-node set in the archive are records, not final results.

## 13. Documentation and privacy audit

**Documents updated:**

- `README.md`: data classes, radio battery versus separate sensing estimate, the DO local-only probe, `OMNETPP_ROOT`, the 200- and 500-node five-seed results and the comparison files.
- `scenario_study/SCENARIO_CATALOG.md`: DO local alarm and its separately identified energy; node counts; turbidity.
- Earlier in the audit: `DATASET_PROVENANCE.md`, `SENSOR_PROFILE_DESIGN.md`, `OMNET_FEASIBILITY.md`.

**Agreement with the data:**

- The dataset metadata agree with the implementation: the water payload has 4 fields, DO is listed as a field with its hardware, and missing values are never 0.
- The energy figures in `SENSOR_PROFILE_DESIGN.md` §4 match the validator's recomputation.

**Privacy:**

- No personal path remains in any `.cmd`, `.bat`, `.ps1`, `.py`, `.ini`, `.sh`, `.json`, `.ned` or Makefile.
- No credentials or tokens were found.
- The KSPCB workbook is not inside the project.
- The username remains only in historical reports (`docs/final_report.md`, `reports_v2/07_final_report.md`), `matlab_reference/README.md` and its two MATLAB export scripts (which name the MATLAB source folder), and the archived and validation copies.
- There is no `.gitignore`. Exclude `results*/`, `logs*/`, `out/`, `validation_v*/` and `archive/` before any publication.

## 14. Fixed issues

| ID | Severity | Fix |
|---|---|---|
| AUD-01 | High | 500-node support (datasets, generator and validator `--nodes`, config `N`, `run.cmd` scenario and nodes arguments, analysis). Five seeds completed at both sizes. |
| AUD-02 | Medium | Per-report frame bits from the dataset (only present fields). |
| AUD-03 | Medium | OMNeT++ parallel-iteration quirk: dataset-folder path with one parallel variable. |
| AUD-04 | Low | Water DO resolved as an intentional local alarm measurement; its energy is kept and reported separately. |
| AUD-07 | Low | Turbidity statement corrected. |
| AUD-09 | Low | Documentation updated. |
| AUD-10 | Low | Archived sources kept out of the NED and build scope. |
| AUD-11 | Low | Hard-coded user-profile fallback paths removed; `OMNETPP_ROOT` is required, with clear errors. |

## 15. Unresolved issues

| ID | Severity | Limitation and reason |
|---|---|---|
| AUD-05 | Medium | No standby or sleep energy in the sensing ledger; adding it needs verified values and dataset regeneration. |
| AUD-06 | Medium | The dominant sensing terms are assumptions (COD probe, gas-sensor boards, interfaces, NPK); they need datasheets. |
| AUD-08 | Low | `sensor_profiles.json` describes both a presence bitmap and a fixed-length sentinel; the protected file was not edited, and the model follows the dataset. |
| AUD-13 | Info | No MAC contention, collisions or queues; loss does not depend on frame length. |
| AUD-14 | Info | No node fails within 500 rounds, so first- and half-node failure cannot rank scenarios. |
| AUD-12 / 15 / 16 / 17 | Info | Old `.sca` module names in the stored 10-node results; retired `m1_report` exists only for nodes 1–200; "51 actions" comments; the tool name. |

DO alarm reports do not carry the DO value (AUD-04 remainder).

## 16. Commands

Set the OMNeT++ location once per machine, then open a new prompt:

```bat
setx OMNETPP_ROOT "C:\path\to\omnetpp-6.4.0"
```

Build this project only (never Ctrl+B):

```bat
build.cmd
```

Run the experiments:

```bat
run.cmd V2_200Node_Environmental all 200
```

```bat
run.cmd V2_200Node_Environmental all 500
```

One scenario at one size, seeds 42–46:

```bat
run.cmd V2_200Node_Environmental mixed 500
```

One scenario, size and seed (OMNeT++ MSYS2 shell):

```bash
./RLHybrid_Scalability_Experiment -u Cmdenv -c V2_200Node_Environmental -r '"$scenario"=="mixed" && $N==500 && $seed==42'
```

Analyse and draw the graphs (`--nodes 500` also writes the 200-versus-500 table and graphs):

```bash
python -P tools/environmental_200node.py --nodes 200
```

```bash
python -P tools/environmental_200node.py --nodes 500
```

Regenerate and validate the datasets:

```bash
python -P scenario_study/generators/generate_scenarios.py --nodes 500 --matrix ""
```

```bash
python -P scenario_study/generators/validate_scenarios.py --nodes 500 --regen-dir <empty temp dir>
```

Use `--nodes 200` for the 200-node datasets.

**Regressions (OMNeT++ shell):**

- **10-node:** run `V2_10Node` with `--result-dir=<folder>`, then:
  ```bash
  V2_RES=<folder> python3 tools/compare_v2.py V2_10Node 42 43 44 45 46
  ```
- **50-node:** prepare a folder with copies of `tools/`, `matlab_reference/` and the loader data, then:
  ```bash
  VALDIR=<folder> ./validate_v2.sh
  ```
  Never run `validate.sh` or `validate.cmd`: they write into the protected v1 `results/`.

## 17. Final readiness assessment

**Ready with limitations.**

**What holds:**

- The project builds cleanly.
- The MATLAB 10-node (95/95) and 50-node (112/112) validations pass, and the 200-node environmental results reproduce byte for byte.
- All five scenarios run at 200 and 500 nodes with five seeds each, from one configuration and one routing implementation, and every consistency check passes. The 500-node runs reproduce exactly.
- The datasets validate and regenerate byte-identical.
- No personal paths or secrets remain in executable files.

**Limits on interpretation:**

- The sensing ledger is an estimate: largely assumptions, no standby terms, and the DO probe identified separately.
- The radio model has no MAC contention.
- No node fails within 500 rounds, so lifetime cannot be ranked by node failures.
