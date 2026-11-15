# Experiment status (final snapshot v1.0.0, 15 Nov 2026)

Labels: **complete** (all planned seeds and rounds), **single seed** (complete run, no spread), **partial / interrupted**
(stopped before the last round, never used as a result), **failed** (stopped by an error, kept for diagnosis),
**smoke test** (a few rounds, checks only).

## Abstract model (native OMNeT++, MATLAB-equivalent channel)

| Experiment | Location | Status |
|---|---|---|
| 50-node MATLAB equivalence (112 checks) | `validation_v2` … `validation_v11`, `matlab_reference/`, `validate.cmd` | complete (112/112 pass in the final version) |
| 10-node V2 MATLAB reproduction and regressions | `results_v2_10node*` (one folder marked `_INVALID_attempt_carryover_bug` is kept as a documented bug) | complete |
| Relay-density scaling 50/100/250/500 nodes, 1,000 rounds | `results_v2_scaling`, `reports_v2/`, `docs/results_250_five_seeds.md` | complete (seeds 42-46; 500 nodes seed 42 only) |
| 250-node placement sensitivity | `results_v2_scalable`, `reports_v2/` | complete |
| v1 scaling results (superseded design) | `results/`, `archive/v1_2026-10-25/` | complete, superseded by v2 |
| Multi-scenario study (M1, M2T, M2F; retired) | `results_multi_scenario/`, `archive/multi_scenario_2026-11-12/` | complete, retired configurations |
| 200-node optimisation study | `results_200node_optimization/` | complete (development study) |
| Controlled experiments | `results_controlled/` | complete |
| Environmental, 200 nodes, 5 scenarios × seeds 42-46, 500 rounds | `results_environmental/` | complete |
| Environmental, 500 nodes, 5 scenarios × seeds 42-46, 500 rounds | `results_environmental_500/` | complete |

## IEEE 802.15.4 model (INET 4.7.0)

| Experiment | Location | Status |
|---|---|---|
| Pilot tests P1-P6 (two-node ACK, collisions, queue, ...) | `results_research_upgrade/pilot/`, `results_research_upgrade/link_check/`, `results_research_upgrade/w10/` | complete |
| 200 nodes, mixed, variant C, link-budget prior, 500 rounds | `results_research_upgrade/wireless_N200/` | **complete, seeds 42-46** |
| 200 nodes, mixed, event-aware option, 500 rounds | `results_research_upgrade/eventaware_N200/` (100-round run: `eventaware_N200_100rounds/`) | **single seed (42)**; seeds 43-46 were interrupted (`interrupted_runs/W_EventAware-*`) |
| 200 nodes, mixed, variant C, MATLAB link prior | `results_research_upgrade/sensitivity_matlab_prior_N200/` | single seed (42) |
| 200 nodes, water / effluent / air / soil on 802.15.4 | - | **not run** |
| 500 nodes, mixed, variant C, fixed area, 500 rounds | `results_research_upgrade/wireless_N500/` | **seed 42 complete; the five-seed experiment is incomplete** |
| 500 nodes, seeds 43-46 | `results_research_upgrade/interrupted_runs/N500-W_Environmental-mixed-seed4{3..6}-20261115-stopped-round96/` | **partial**: stopped deliberately at round 96 of 500 when the project was frozen |
| 500 nodes, seed 42, earlier attempt | `results_research_upgrade/interrupted_runs/N500-W_Environmental-mixed-seed42-*` | partial (47 rounds, session ended) |
| 200 nodes, seeds 43 and 45, before the MAC fault handling | `results_research_upgrade/failed_runs/` | failed (INET MAC fault, see PROJECT_REPORT.md section 6); rerun with the fix |
| 500 nodes, seed 42, on the binary without the fix | `results_research_upgrade/failed_runs/N500-stopped-oldbinary-*` | partial (stopped to switch binary) |
| 500 nodes fixed area / fixed density, 5 rounds | `results_research_upgrade/smoke_tests/` | smoke test |
| Event-aware, placement, range-filter checks (20 rounds) | `results_research_upgrade/smoke_tests/` | smoke test |
| 500 nodes fixed density, 5 s decision windows, `W_FeedbackAck` airtime run | - | configured, **not run** |

## 500-node 802.15.4 run, seed 42 (the only complete 500-node wireless run)

`W_Environmental` run #29, 15 Nov 2026 16:07-21:30, 500/500 rounds, exit 0, all accounting checks passed.
PDR 49.84 % (91,085 / 182,752) vs 44.54 % for the abstract run of the same seed; 500/500 nodes alive;
runtime 5.37 h; peak memory 168.7 MB. Details: `PROJECT_RESEARCH_UPGRADE_REPORT.md` section 11.

## Last progress of the stopped 500-node runs

| Seed | Run | Started | Stopped | Rounds completed | Note |
|---|---|---|---|---|---|
| 43 | #34 | 15 Nov 21:31:48 | 22:46 | 96 / 500 | stopped by decision (project freeze) |
| 44 | #39 | 15 Nov 21:31:51 | 22:46 | 96 / 500 | same |
| 45 | #44 | 15 Nov 21:31:54 | 22:46 | 96 / 500 | same |
| 46 | #49 | 15 Nov 21:31:57 | 22:46 | 96 / 500 | same |

The launcher recorded bash exit 127 for each because the simulator was terminated; no `.sca` or `metrics.csv`
was written. The per-round and per-report CSVs up to round 96 are kept.
