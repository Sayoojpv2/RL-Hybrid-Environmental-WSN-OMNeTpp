# Final report – scalable 50–500-node RL-Hybrid WSN (OMNeT++ 6.4.0)

**Project:** `<USER_HOME>\Documents\OMNeT_Projects\RLHybrid_Scalability_Experiment`
(a copy of `RLHybrid_Periyar_OMNeT_Validation`; the source projects, the MATLAB code and data, the frozen benchmark and
all earlier results were not modified). Date: 25 Oct 2026.

## Tests performed
| Stage | What | Result |
|---|---|---|
| A | 50-node MATLAB reproduction on the final code (`validate.cmd`) | 112/112, decision trace identical to MATLAB, seeds 42–46 |
| A | Output identity vs the unmodified copy (after the final clean rebuild) | 51/51 files byte-identical. `Periyar50_Baseline` = `FiveSeeds` (30/30) |
| B/C | Smoke tests, 100/250/500 nodes, 20 rounds | 11/11 checks each; original channel block = MATLAB |
| D | **250 nodes, seeds 42–46, 1000 rounds** | completed, 50/50 checks |
| D (extra) | 100 nodes, seeds 42–46, 1000 rounds | completed, 50/50 checks |
| E | 500 nodes, seed 42, 1000 rounds | completed, 10/10 checks (+ full-length channel-block check 11/11) |
| – | Reproducibility: re-run of 250-node seed 42 | 10/10 output files byte-identical |
| – | Clean rebuild of this project only (`build.sh`) | 0 errors, 0 warnings; INET not built; Ctrl+B not used |
| – | Qtenv: `Periyar250_GuiPreview` set up (not run) | 502 modules created, screenshot `docs/qtenv_250_preview_loaded.png`; Qtenv preferences restored |
| – | Imported into the IDE `samples` workspace (File → Import → Existing Projects, **not copied**) | `.location` points to this folder; no build triggered (exe and Makefile timestamps unchanged) |

**Failures:** none of the checks failed. One tooling defect was found and fixed: `run_measured.ps1` printed an
empty exit code in the smoke-test runs (it needed `$p.Handle` held before exit). The smoke-test rows in
`logs/performance.txt` therefore show "exit ," with no code; those runs were verified by their check scripts.

## Main result (mean ± sample sd, 1000 rounds)
| | 50 (= MATLAB) | 100 (5 seeds) | 250 (5 seeds) | 500 (seed 42) |
|---|---|---|---|---|
| PDR (delivered / 10,000 scheduled) | 41.02 ± 3.17 % | 38.54 ± 4.15 % | 36.39 ± 2.81 % | 32.14 % |
| Delivered / emitted | 44.21 ± 2.99 % | 40.66 ± 3.26 % | 37.85 ± 2.30 % | 33.94 % |
| Channel losses | 5163 ± 250 | 5608 ± 178 | 5966 ± 134 | 6256 |
| Mean delivered hops | 4.34 ± 0.23 | 4.73 ± 0.22 | 5.23 ± 0.18 | 5.87 |
| Energy per delivered report | 10.9 ± 1.5 mJ | 13.4 ± 2.2 mJ | 17.0 ± 2.3 mJ | 20.5 mJ |
| Operational nodes at end | 44.4 / 50 | 98.6 / 100 | 248.4 / 250 | 498 / 500 |
| Runtime per seed / peak memory | 2.0 s / 23 MiB | 2.3 s / 24 MiB | 3.0 s / 25 MiB | 4.2 s / 29 MiB |

**Honest reading:** with the algorithm, reward and state features unchanged, **denser relays reduced PDR**
(250 − 50: −4.63 ± 0.99 pp, lower for every seed). Routes got longer. Each hop is capped at link quality 0.95
in this channel model, so every extra hop adds loss. Batteries last longer because the load is spread over
more nodes. The same 10-source real workload was used at every N, so this is a controlled comparison of
network density only. Full tables: `docs/results_250_five_seeds.md`, `logs/stageD_scaling_table.md`.

## Differences from the MATLAB experiment (for N > 50 only; N = 50 is identical)
1. MATLAB has no N > 50 model. Nodes 51..N come from a dedicated MT19937 stream (seed 900000 + seed),
   uniform over the same area, unsorted, appended after the 50 MATLAB nodes.
2. Links involving an added relay use MATLAB's clipped distance law, but their random draws come from a
   deterministic counter hash (seed, round, i, j), evaluated lazily. The 50×51 MATLAB block is unchanged.
3. The BS action index is N+1 (51 at N = 50). The Q-table key stride is N+1. The Q-table is a sparse hash map (as before).
4. Display only: added relays are drawn as small grey nodes labelled `n<id>`, and the legend text is N-independent.

## Not done / limitations
* 500 nodes: only seed 42 (as requested). There is no five-seed spread at 500.
* No sensitivity study over `extraTopologySeed` (relay placement) or over ε at larger N.
* The model's abstractions are unchanged: no MAC contention, centralised sequencing, free control messages,
  no radio-range limit. These matter more at high density, so the results are model-internal, not deployment predictions.
* FND is right-censored at 100 and 250 nodes (one seed each with no unavailable node in 1000 rounds).

## Suggested next steps
1. Five seeds at 500 nodes (`Periyar500_RelayScaling` with `${seed=42..46}`; about 21 s).
2. Repeat 250 nodes with 2–3 alternative `extraTopologySeed` values, to separate placement effects from density effects.
3. A longer horizon (e.g. 3000 rounds) to test whether the larger action space just needs more learning time
   (the Periyar workload would need a defined extension. Do not invent data).
4. Optional: a radio-range limit or a MAC model, both clearly labelled as model changes. They are not part of the MATLAB-faithful baseline.
