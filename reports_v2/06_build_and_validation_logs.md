# 6. Build and validation logs (v2, 25 Oct 2026)

All copies are in `reports_v2/logs/`. The originals are in `logs_v2/` and `validation_v2/logs/`.

| Step | Command | Outcome | Log |
|---|---|---|---|
| Preserve v1 | copied results/, logs/, docs/, sources and tools to `archive/v1_2026-10-25/` with an MD5 manifest; recorded the MD5 of every file in `results/` | 450 archived files verified afterwards; `PeriyarValidation.ned` renamed `.archived` (same MD5) so OMNeT++ does not load a duplicate NED type | `archive/v1_2026-10-25/MANIFEST.md5`, `MANIFEST_NOTE.txt` |
| Build (only this project) | `build.sh` → `make MODE=release` | exit 0, **0 warnings, 0 errors**. No INET; Ctrl+B not used; no IDE build | `build_v2.log` |
| 50-node baseline first | `validate_v2.sh`: ReferenceCheck, SmokeSeed42, FiveSeeds with `--result-dir=validation_v2/results`, unchanged comparison scripts | **ALL STAGES PASSED**: 22 + 4 + 11 + 20 + 55 = 112 checks; 51/51 files byte-identical to the archived baseline | `validate_v2.log`, `stageB_reference_check.txt`, `stageC_*.txt`, `stageD_five_seeds_vs_matlab.txt`, `stageE_internal_checks.txt`, `byte_identity_vs_unmodified_copy.txt` |
| Plumbing check | `Check_MatlabModeSeed42` (N = 50/100/250/500) | 36/36 output files byte-identical to the v1 seed-42 runs | `check_matlab_mode_reproduces_v1.txt` |
| Channel audit | `Audit_ChannelMatlabMapping`, `Audit_ChannelIndependent` (channel export only) | overlap confirmed for the MATLAB mapping; none for the independent mapping | `audit_channel_stream_overlap.txt`, `audit_matlab_benchmark_channel_coupling.txt` |
| Controlled runs | `tools/run_measured_v2.ps1 -Config Ctrl{50,100,250,500} -Run 0..4` (one process per run) | 20/20 exit 0; 1000/1000 rounds each | `performance_v2.csv` |
| Placement runs, attempt 1 | `Place250` runs 0–4 | **failed** at start-up (exit 1): `No such variable: ${seed}`. The general output prefix uses `${seed}`, and Place250 had set the seed as a plain value. Nothing was simulated and no result files were written | `failed_Place250_attempt1.csv`, `failed_Place250_attempt1_r0.err` |
| Fix and placement runs, attempt 2 | `scenarioSeed = ${seed=42}` (a single-value iteration variable; same value) | 5/5 exit 0 | `performance_v2.csv` |
| Verification | `tools/verify_controlled.py` | **261/261 checks passed**: 10 per run × 25 runs, plus cross-run X1–X5 | `verify_controlled.txt` |
| Analysis | `tools/analyze_controlled.py`, `tools/diagnose_mechanism.py` | tables 02–05 and 04b | `analyze_controlled_console.txt`, `diagnose_mechanism_console.txt` |
| v1 results untouched | MD5 of all 317 files in `results/` before and after | identical, nothing added | `v1_results_untouched.txt` |
| Other projects / MATLAB | timestamp scan | no file changed in RLHybrid_OMNeT_Demo, RLHybrid_Periyar_OMNeT_Validation, RLHybrid_AllNodeSensing_Experiment or RL_WSN_Periyar | (this table) |

Runtime and memory per run (Cmdenv, release build, Windows 11 laptop, one process per run):

| N | wall time per run (s) | peak working set (MiB) |
|---|---|---|
| 50 | 2.74 ± 0.06 | 22.8 ± 0.1 |
| 100 | 3.28 ± 0.10 | 22.8 ± 0.1 |
| 250 | 3.79 ± 0.09 | 24.5 ± 0.1 |
| 500 | 4.66 ± 0.11 | 28.8 ± 0.0 |

The v2 runs write an extra diagnostics file (`-hops.csv`). Times include all file output.
