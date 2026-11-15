# matlab_reference

Reference data exported **read-only** from the frozen MATLAB project
`<USER_HOME>\Documents\MATLAB\RL_WSN_Periyar` (MATLAB R2026a, batch mode, 2026-10-25).

* `scripts/probe_rng.m`: records MATLAB `rand`/`randi` values used to verify `MatlabRng.h`.
* `scripts/export_reference.m`: calls the frozen `load_water_quality_data`,
  `create_periyar_workload_continuous(wq,1000,'uniform')` and `generate_scenario(seed)`, and reads
  `results/five_seed_rl_hybrid_corrected_authoritative.mat`. It writes **only** into `data/` here.
* `data/provenance.txt`: MD5 of every source file used. `RL_Hybrid.m` equals the MD5 stored in the
  authoritative result.
* `data/workload_matlab.csv`, `workload_summary_matlab.txt`: the 9,825-report workload.
* `data/nodes_seed*.csv`, `success_seed*.bin`: topology and all channel outcomes (uint8, MATLAB
  column-major order i, j, round).
* `data/decisions_matlab_seed*.csv`, `per_round_matlab_seed*.csv`, `unavailability_matlab_seed*.csv`,
  `reference_metrics_matlab.csv`: the frozen RL-Hybrid results (decision logs, per-round series,
  metrics).

A file-timestamp snapshot taken before and after the export confirmed that the MATLAB workspace was
not modified (40 files, identical timestamps and sizes). The OMNeT++ model does **not** need MATLAB
or these files to build or run; they are used only by the validation scripts in `tools/`.
