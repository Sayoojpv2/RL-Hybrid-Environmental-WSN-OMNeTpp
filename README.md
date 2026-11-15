# RL-Hybrid Environmental WSN — OMNeT++ / INET simulation study

Reinforcement-learning-based adaptive routing for environmental wireless sensor networks, implemented and evaluated
with OMNeT++ 6.4.0 and INET 4.7.0.

**v1.0.0 is the frozen final snapshot of the software simulation study; v1.0.1 only repairs scripts and documentation
([CHANGELOG.md](CHANGELOG.md)).** Hardware deployment is not part of this project's results; it is a proposed future
extension.

## The project in three stages

| Stage | What it is | Status |
|---|---|---|
| 1. MATLAB algorithm development | RL-Hybrid (tabular Q-learning with a hybrid sinkward/cluster rule) designed and compared with conventional routing in MATLAB on the Periyar river scenario | done (separate MATLAB project; exported reference data in `matlab_reference/`) |
| 2. OMNeT++ / INET validation | MATLAB-equivalent abstract model, scaling 50-500 nodes, five environmental scenarios, IEEE 802.15.4 MAC/PHY over INET, radio-state energy, event-aware routing | done as far as stated in [docs/EXPERIMENT_STATUS.md](docs/EXPERIMENT_STATUS.md) |
| 3. Hardware demonstration | small air-quality sensor WSN | **proposed, not implemented** ([docs/RESEARCH_ROADMAP.md](docs/RESEARCH_ROADMAP.md)) |

## Key results (evidence in this repository)

| Experiment | Result | Status |
|---|---|---|
| 50-node OMNeT++ model vs MATLAB reference | 112/112 equivalence checks pass | complete |
| Relay-density scaling 50 → 500 nodes (abstract) | PDR 41.0 % (50) → 36.4 % (250) → 32.1 % (500, one seed) | complete (500: one seed) |
| Five environmental scenarios, 200 and 500 nodes (abstract, 5 seeds each) | PDR 41.9-46.9 % (200), 40.5-45.1 % (500); no node failure in 500 rounds | complete |
| IEEE 802.15.4, 200 nodes, mixed, variant C (5 seeds) | PDR **89.80 ± 0.34 %** vs 45.08 ± 1.47 % abstract (paired +44.7 points, 95 % CI [42.7, 46.7]) | complete |
| IEEE 802.15.4, 200 nodes, event-aware option | critical reports within 2 s: 94.17 % vs 0.11 % (variant C) | one seed only |
| IEEE 802.15.4, 200 nodes, MATLAB link prior | PDR 78.71 % vs 89.51 % with the link-budget prior | one seed only |
| IEEE 802.15.4, 500 nodes, mixed | seed 42: PDR 49.84 % vs 44.54 % abstract (500 rounds complete); seeds 43-46 stopped at round 96 | **incomplete: one of five seeds** |

These figures are simulation results under documented assumptions. They do not show that RL-Hybrid outperforms
every existing routing method; the comparisons are between the abstract and the 802.15.4 models of the same
algorithm and between algorithm options.

## Repository map

| Path | Content |
|---|---|
| `*.cc`, `*.h`, `*.ned`, `Messages.msg` | simulator: `SensorNode` (RL-Hybrid / Q-learning), `BaseStation`, `Controller`, `PeriyarModel`, networks |
| `wireless/` | INET 802.15.4 integration plugin (adapter, CC2420 radio values, pilot tests) |
| `omnetpp.ini` | all configurations (MATLAB validation, scaling, environmental, `W_*` wireless) |
| `tools/` | dataset conversion, workload/event generation, verification, analysis and plotting scripts |
| `data/` | input datasets and generated workloads (provenance: `scenario_study/DATASET_PROVENANCE.md`) |
| `matlab_reference/` | MATLAB reference exports used by the equivalence validation |
| `results_*`, `validation_v*`, `reports_v2/`, `logs*/` | experiment results (summaries, per-round CSVs, figures, logs) |
| `results_research_upgrade/` | IEEE 802.15.4 results, smoke tests, interrupted and failed runs |
| `archive/` | earlier frozen versions and audits with checksums |
| `docs/` | documentation; start with the files below |

## Documentation

* [PROJECT_REPORT.md](PROJECT_REPORT.md): the complete project report.
* [docs/EXPERIMENT_STATUS.md](docs/EXPERIMENT_STATUS.md): every experiment, labelled complete, single-seed, partial, failed or smoke test.
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): modules, data flow and energy accounting.
* [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md): build, run and analyse; raw-data archives.
* [docs/RESEARCH_ROADMAP.md](docs/RESEARCH_ROADMAP.md): open gaps and future work, including hardware.
* [PROJECT_RESEARCH_UPGRADE_REPORT.md](PROJECT_RESEARCH_UPGRADE_REPORT.md): detailed IEEE 802.15.4 report.
* [PROJECT_FINAL_AUDIT.md](PROJECT_FINAL_AUDIT.md): audit of the abstract environmental study.

## Getting started

**Tested environment:** Windows 11, OMNeT++ 6.4.0 with its bundled MSYS2 clang64 toolchain, INET 4.7.0 (release
build, wireless model only), Python 3.11+ with numpy and matplotlib. Linux and macOS are **not verified**: the wireless
scripts load Windows DLLs (`libINET.dll`, `libRLHybridWireless.dll`) and use `cygpath`.

Set `OMNETPP_ROOT` once (Windows prompt): `setx OMNETPP_ROOT "D:\omnetpp-6.4.0"`, then open a new prompt.

1. **Build** (minutes): `build.cmd` (simulator), and for the wireless model `build_wireless.cmd` after building INET.
2. **Optional short demonstration** (seed 42, rounds 1-20 of the 50-node MATLAB-equivalent model):
   `run.cmd GuiDemo20Rounds`. Output goes to a new `runs\GuiDemo20Rounds-<timestamp>\` folder.
3. **Full validation suite** (an experiment, not a quick check: reference check, a 1,000-round smoke run and five
   1,000-round seeds): `validate.cmd`. Output and logs go to a new `validation_runs\<timestamp>\` folder.
4. **Experiments**: `run.cmd V2_200Node_Environmental mixed 200` (abstract model, five seeds) or, in the OMNeT++ shell,
   `./run_wireless.sh -c W_Environmental -r '"$scenario"=="mixed" && $N==200 && $seed==42'` (802.15.4).

The wrappers never write into the published `results*` folders by default; set `RESULT_DIR` (for `run.cmd`) or pass
`--result-dir` (for `run_wireless.sh`) to choose a folder. Details: [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

Bulky per-event raw outputs are published as `.tar.xz` assets of the GitHub Release; see
[docs/RAW_DATA_MANIFEST.md](docs/RAW_DATA_MANIFEST.md).

## Data and licences

* KSPCB River Periyar water-quality analysis reports (Jan-Jul 2025): converted tables of the project's own data, attributed to
  the Kerala State Pollution Control Board. The original workbook is not included.
* UCI Beijing Multi-Site Air Quality (Chen S., 2017, DOI 10.24432/C5RK5G), CC BY 4.0, included with attribution.
* Industrial-effluent and soil datasets are synthetic (deterministic generators), not measurements.

**Licence:** no licence is granted. All rights are reserved by the author; the code is public for reading and review only.
