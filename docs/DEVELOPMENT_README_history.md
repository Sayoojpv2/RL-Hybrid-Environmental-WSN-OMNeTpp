# RLHybrid_Scalability_Experiment

> **Primary workflow: one environmental WSN, `[Config V2_200Node_Environmental]`, N = 200 (validated reference) or 500 nodes.**
> - N nodes that all sense and forward (no relay-only nodes), one BS at (600, 25) m, a 600 × 50 m area and 500 rounds (1 round = 1 h).
> - 2 J radio energy per node and the first-order radio model.
> - Variant C RL-Hybrid (energy guard 0.8, tabular Q-learning), no retransmission.
>
> Two parameters select an experiment: `N` = `200` | `500` and `scenario` = `water` | `effluent` | `air` | `soil` | `mixed`.
> The scenario selects the workload: the dataset `data/scenarios/<profile>_<N>/`, the sensor profile and fields, the reporting
> schedule, the per-report frame sizes and the sensing ledger.
>
> Data classes:
> - **Real measurements:** 10 KSPCB Periyar station streams (water, nodes 1–10) and 12 UCI Beijing station streams (air, nodes 1–12).
> - **Replayed measurements:** every other water and air node replays one of those streams. These are virtual sensors, not extra stations.
> - **Synthetic measurements:** effluent and soil, from deterministic generators.
>
> Energy:
> - **Radio battery:** 2 J per node. Transmission, reception and aggregation are charged to it.
> - **Sensing energy:** a separate estimate in `<prefix>-sensing_ledger.csv`, never charged to the battery, and mostly based on assumptions.
>   It includes the water DO probe, which every water node reads for the DO < 4 mg/L alarm but does not transmit. The analysis lists that
>   probe separately as local-only sensing energy.
>
> Set `OMNETPP_ROOT` once to your OMNeT++ 6.4.0 folder (for example `setx OMNETPP_ROOT "D:\omnetpp-6.4.0"`, then open a new prompt).
> The `.cmd` scripts stop with a message if it is missing.
>
> Run it:
> - `run.cmd V2_200Node_Environmental all 200` runs 25 runs (5 scenarios × seeds 42–46, 200 nodes).
> - `run.cmd V2_200Node_Environmental water 500` runs one scenario at 500 nodes (seeds 42–46).
> - `run.cmd V2_200Node_Environmental` alone runs every run of the config (both sizes, 50 runs).
>
> Results go to `results_environmental/` (200 nodes, seeds 42–46) and `results_environmental_500/` (500 nodes, seeds 42–46), with figures
> in their `figures/` folders. The 200-versus-500 table is `results_environmental_500/comparison_200_vs_500.csv`, with graphs
> `fig9_200_vs_500.png` and `fig10_200_vs_500_cost.png`. Analyse with `python -P tools/environmental_200node.py --nodes 200` (or `--nodes 500`).
> The full audit is `PROJECT_FINAL_AUDIT.md`, with the issue register `PROJECT_AUDIT_ISSUES.csv`.
>
> Each report is an IEEE 802.15.4 frame of its own sensor profile carrying only its present fields
> (dataset column `m2_frame_bits`). Energy, feasibility and airtime use the actual frame bits. The node-death threshold
> stays at the validated 200 µJ (E_elec × 4000 bit). Sensing energy is a separate ledger: the lifetimes reported are
> communication-network lifetimes, not physical battery lifetimes.
>
> The earlier multi-scenario configurations (M1, M2T, M2F and the five-seed `_5S` sets) are retired. Their ini and
> sources are in `archive/multi_scenario_2026-11-12/`, and their results remain in `results_multi_scenario/`.

> **v2 (25 Oct 2026): use `reports_v2/` for the scalability results.** The v1 design below used one seed for
> placement and run randomness together, and MATLAB's channel mapping overlaps between consecutive seeds.
> v2 instead uses:
> - a fixed, nested topology per node count;
> - independent run randomness (`Ctrl50/100/250/500`, run seeds 42–46);
> - a separate 250-node placement-sensitivity experiment (`Place250`);
> - corrected first-unavailability reporting and routing diagnostics.
>
> The 50-node MATLAB reproduction is unchanged (re-validated 112/112). The v1 results are kept unmodified in `results/`,
> and archived with an MD5 manifest in `archive/v1_2026-10-25/`.

**Relay-density scaling (50 → 500 nodes) of the validated RL-Hybrid WSN on the Periyar river.**
Native OMNeT++ 6.4.0 (no INET). This project is a copy of `RLHybrid_Periyar_OMNeT_Validation`
(which was not modified) with one extension: the number of battery nodes `N` is configurable.

* Fixed 600 m × 50 m river section, BS at (600, 25) m. **The area does not grow; only the relay density does.**
* Always the same 10 real Periyar station sources (nodes 4, 8, 12, …, 48) and the same real workload
  (10,000 scheduled slots, 9,825 with valid data). Added nodes are **relay-only**: they never create reports.
* Nodes 1..50 are exactly the MATLAB `generate_scenario(seed)` topology. Added relays have ids 51..N and
  come from a separate deterministic stream (see `docs/topology_and_sources.md`). **They are simulated
  positions, not real monitoring stations.**
* The RL-Hybrid algorithm is unchanged: 8 ternary features, 6561 states, α 0.1, γ 0.9, the ε schedule,
  the reward, qHat, the sinkward rule, cluster heads/aggregation, TTL 15, the 200 µJ rule and the energy model.
  The only generalisation is that the action index of the BS is `N + 1` instead of the constant 51.

## Build (build only this project)

* Command line: double-click / run `build.cmd` (runs `build.sh` in the OMNeT++ 6.4.0 MSYS2 shell; `make MODE=release`).
* IDE: right-click the project → **Build Project**. **Never press Ctrl+B** (= Build All, which rebuilds INET).
* Last clean build: 0 errors, 0 warnings (`logs/build_final_clean.log`).

## Configurations (`omnetpp.ini`)

| Config | N | Seeds | Rounds | Purpose |
|---|---|---|---|---|
| `ReferenceCheck`, `SmokeSeed42`, `FiveSeeds`, `GuiDemo20Rounds`, `Seed42FullGui` | 50 | – | – | unchanged configs of the validated project |
| `Periyar50_Baseline` | 50 | 42–46 | 1000 | the MATLAB experiment (byte-identical to `FiveSeeds`) |
| `Periyar100_Smoke`, `Periyar250_Smoke`, `Periyar500_Smoke` | 100/250/500 | 42 | 20 | smoke tests (channel export on) |
| `Periyar100_RelayScaling` | 100 | 42–46 | 1000 | supplementary scaling point |
| `Periyar250_RelayScaling` | 250 | 42–46 | 1000 | **primary benchmark** |
| `Periyar500_RelayScaling` | 500 | 42 | 1000 | 500-node single-seed run |
| `Periyar250_GuiPreview` | 250 | 42 | 20 | Qtenv preview only – not a result |

Run in Cmdenv, e.g. from PowerShell (also records wall time and peak memory into `logs/performance.txt`):

```
tools\run_measured.ps1 -Config Periyar250_RelayScaling
```

or `run.cmd` / the IDE (*Run As → OMNeT++ Simulation*, choose the config). Outputs go to `results/`.

## Verification

* `validate.cmd` – the full 50-node MATLAB validation (expect `ALL STAGES PASSED`, 112 checks).
* `python3 tools/verify_scaling.py <Config> <N> <seeds…>` – 11 checks per seed for N > 50 (module count,
  coordinates, workload, relay-only, action range, channel block, energy closure, accounting, availability/TTL, timing).
* `python3 tools/scaling_table.py Periyar50_Baseline Periyar100_RelayScaling Periyar250_RelayScaling Periyar500_RelayScaling`
  – the comparison table (`logs/stageD_scaling_table.md`).

## Headline result (seeds 42–46, 1000 rounds, mean ± sample sd)

| | 50 (MATLAB baseline) | 100 | **250** | 500 (seed 42 only) |
|---|---|---|---|---|
| PDR = delivered / scheduled | 41.02 ± 3.17 % | 38.54 ± 4.15 % | **36.39 ± 2.81 %** | 32.14 % |
| Mean delivered hops | 4.34 ± 0.23 | 4.73 ± 0.22 | 5.23 ± 0.18 | 5.87 |
| Energy per delivered report | 10.9 mJ | 13.4 mJ | 17.0 mJ | 20.5 mJ |

**Adding relays made PDR worse, not better**, with the algorithm unchanged: routes get longer and each extra
hop is another chance of channel loss. Details and caveats: `docs/results_250_five_seeds.md`, `docs/final_report.md`.

## Documents

| File | Content |
|---|---|
| `docs/topology_and_sources.md` | topology generation, node ids, source mapping, channel for added links |
| `docs/baseline_verification.md` | Stage A: the 50-node configuration equals the MATLAB experiment |
| `docs/smoke_tests.md` | Stages B/C: 100/250/500-node smoke tests |
| `docs/results_250_five_seeds.md` | Stage D: primary 250-node five-seed table and the difference from 50 nodes |
| `docs/report_500_nodes.md` | Stage E: what was (and was not) run at 500 nodes |
| `docs/performance_scalability.md` | runtime, memory, action space, data structures, limitations |
| `docs/final_report.md` | summary of everything, MATLAB differences, next steps |

## IEEE 802.15.4 research upgrade (INET 4.7.0) - details in `PROJECT_RESEARCH_UPGRADE_REPORT.md`

`communicationModel = "abstract"` (default) is the validated model above and is unchanged. `communicationModel = "ieee802154"`
runs the same nodes, workload and RL-Hybrid / variant C decisions over INET's IEEE 802.15.4 narrowband MAC/PHY (CSMA/CA,
MAC ACK and retries, interface queue, path loss, noise and interference) with CC2420 datasheet radio values.

* Build once: INET 4.7.0 release build in `<OMNETPP_ROOT>/samples/inet-4.7.0`, then `build_wireless.cmd` (plugin
  `wireless/libRLHybridWireless.dll`; the main simulator stays INET-free).
* Run (OMNeT++ shell): `./run_wireless.sh -c W_Environmental -r '"$scenario"=="mixed" && $N==200 && $seed==42'`
* Configs: `W_Environmental` (variant C), `W_EventAware` (event-aware option), `W_ScenarioPlacement`, `W_FixedDensity`,
  `W10_Smoke`; pilot tests `./run_wireless.sh -f wireless/pilot.ini -c P1_TwoNodeAck` ... `P6_Queue`.
* Checks and analysis: `python -P tools/check_wireless_pilot.py`, `python -P tools/build_event_annotations.py`,
  `python -P tools/research_upgrade.py`. All output goes to `results_research_upgrade/`.
