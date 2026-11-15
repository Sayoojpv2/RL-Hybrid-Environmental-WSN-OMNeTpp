# Stage A – the 50-node configuration equals the MATLAB experiment

Tests run on 25 Oct 2026.

| # | Test | Result | Evidence |
|---|---|---|---|
| A1 | Unmodified copy of `RLHybrid_Periyar_OMNeT_Validation` built and validated in the new folder before any change | 112/112 | outputs saved to `logs/baseline_unmodified_copy/` (51 files) |
| A2 | Final (scalable) code, `validate.cmd`: workload (22), topology (4), channel (11), decision trace vs MATLAB seeds 42–46 (20), internal checks (55) | **112/112, ALL STAGES PASSED** | `logs/validate_final.log` |
| A3 | Final code: the 51 reference/smoke/five-seed output files compared with the unmodified copy | 51 byte-identical, 0 different | `logs/stageA_baseline_identity.txt`, `logs/final_baseline_identity.txt` (re-run after the final clean rebuild) |
| A4 | `Periyar50_Baseline` vs `FiveSeeds` | 30/30 files identical | `logs/stageA_periyar50_equals_fiveseeds.txt` |
| A5 | After the display-only legend edit in the NED file: `Periyar50_Baseline` metrics/decisions/reports vs the unmodified copy | 15/15 identical | `logs/final_baseline_identity.txt` |
| A6 | Frozen MATLAB `RL_Hybrid.m` MD5 | 407788e6…, unchanged | – |

Because the decision trace (every cluster-head and next-hop choice, with its state, ε draw, outcome and
Q-update) is identical to MATLAB for all five seeds, the 50-node configuration **is** the MATLAB experiment:
PDR 41.02 ± 3.17 %, FND 428.0 ± 128.2, 44.4 ± 1.14 operational nodes at the end.

What changed in the code (and why the 50-node path is unaffected):
* `BS_ID`/`NUM_ACTIONS` changed from the constant 51 to a member set to N+1. With N = 50 it is still 51.
* `Scenario::generate` appends relays only when N > 50. The extra stream is never touched at N = 50.
* `Controller::decoded(i, j)` uses the MATLAB success bits for i, j ≤ 50 (and BS). The hash path is never
  reached at N = 50.
* NED: `relay[numNodes − 50]` is an empty vector at N = 50. The legend text is display-only.
