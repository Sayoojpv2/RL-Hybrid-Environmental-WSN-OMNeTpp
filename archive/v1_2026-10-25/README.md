# RLHybrid_Scalability_Experiment

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
