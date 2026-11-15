# reports_v2 – strengthened scalability evaluation (25 Oct 2026)

| File | Content |
|---|---|
| `01_seed_topology_design_audit.md` | every random stream; problems in the v1 design; the v2 controlled design and evidence for it |
| `02_controlled_results.md` | controlled 50/100/250/500-node table (run seeds 42–46), paired differences, per-seed values |
| `03_first_unavailability.md` | FND per seed with censoring stated; v1 numbers re-reported correctly |
| `04_routing_diagnostics.md` | hops, transmissions, true link quality, loss by hop index, candidates, energy by role, added-relay use |
| `04b_mechanism_probes.md` | probes of why routes get longer (cluster-head direction, untried greedy choices, first hop) |
| `05_placement_sensitivity.md` | 250 nodes, run seed 42, five relay placements, with topology characteristics |
| `06_build_and_validation_logs.md` | build, validation, verification and the failed-then-fixed placement attempt; logs in `logs/` |
| `07_final_report.md` | confirmed findings / plausible explanations / unresolved issues / next steps |
| `data/` | per-seed CSVs behind every table |

Reproduce, from the project folder:
1. Build: `build.cmd`.
2. Baseline: `validate_v2.sh` (in the OMNeT++ shell).
3. Runs: `tools\run_measured_v2.ps1 -Config Ctrl250 -Run 0` (runs 0–4 = seeds 42–46; configs Ctrl50/100/250/500 and Place250).
4. Checks: `python3 tools/verify_controlled.py`.
5. Tables: `python3 tools/analyze_controlled.py` and `python3 tools/diagnose_mechanism.py`.

Output directories: `results_controlled/`, `results_placement/`, `results_checks/` and `validation_v2/`. The v1 `results/`
directory was not written (MD5-verified). The v1 state is archived in `archive/v1_2026-10-25/`.
