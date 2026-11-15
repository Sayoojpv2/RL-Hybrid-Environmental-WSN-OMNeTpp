# Changelog

## v1.0.1 (16 Nov 2026): maintenance

Scripts and documentation only. No C++, NED, configuration value, dataset or experimental result was changed, and
no simulation was run.

* Windows wrappers (`build.cmd`, `build_wireless.cmd`, `run.cmd`, `validate.cmd`, `ide_headless_build.cmd`):
  * now return the exit code of the build or run, not `tee`'s (`set -o pipefail`, `exit /b %ERRORLEVEL%`);
    before, a failed build or run still returned 0;
  * guards rewritten as grouped `if (...)` blocks;
  * timestamped logs;
  * `ide_headless_build.cmd` now creates `logs\`.
* `run.cmd` now calls the new `run.sh`, which builds the run filter in bash (no nested CMD quoting).
* Validation and runs no longer write into the published result folders by default:
  * `validate.sh` uses a new `validation_runs/<timestamp>/` (or a given new folder; historical folders are refused);
  * `run.sh` uses `runs/<Config>-<timestamp>/` (or `RESULT_DIR`);
  * `run_wireless.sh` uses `runs/wireless-<timestamp>/` unless `--result-dir` is given;
  * `compare_with_matlab.py`, `verify_run.py` and `five_seed_table.py` read `RLH_RESULTS_DIR` (default `results`).
* Documentation:
  * Python 3.11+ is required (`python -P`), with numpy and matplotlib (pandas is not needed);
  * Windows 11 is the tested platform and Linux is unverified;
  * build, short demonstration and full validation are described separately;
  * Mermaid architecture diagram added; this changelog added.

## v1.0.0 (15 Nov 2026): final simulation-study snapshot

Initial public import of the project: source, configurations, scripts, tools, input data, MATLAB reference exports,
results and documentation. Raw per-event outputs are attached to the v1.0.0 release as `.tar.xz` archives. The
500-node IEEE 802.15.4 five-seed experiment is incomplete (seed 42 only); see `docs/EXPERIMENT_STATUS.md`.
