#!/bin/bash
# Runs the whole validation in order; each stage runs only if the previous one passed.
#   B: workload/topology/channel vs MATLAB   C: seed-42 smoke test   D: seeds 42-46   E: internal checks
# This is a full experiment (five 1,000-round seeds), not a quick check.
# Run inside the OMNeT++ 6.4.0 Shell (or via validate.cmd). Builds nothing; run build.cmd first.
# Usage: ./validate.sh [output dir]
#   default output dir: validation_runs/<timestamp>/ (a new folder for every invocation). All results and logs of the
#   run go there; the historical results folders (results/, results_*/, archive/, validation_v*/) are never written.
set -e -o pipefail
cd "$(dirname "$0")"
OUT=${1:-validation_runs/$(date +%Y%m%d-%H%M%S)}
OUT=${OUT#./}; OUT=${OUT%/}
case "$OUT" in
  results|results/*|results_*|archive|archive/*|validation_v*|matlab_reference*|logs|logs/*|data|data/*)
    echo "refusing to write into the historical or input folder '$OUT'; choose a new folder"; exit 2 ;;
esac
[ -z "$(ls -A "$OUT" 2>/dev/null)" ] || { echo "output folder '$OUT' is not empty; choose a new one"; exit 2; }
L=$OUT/logs
mkdir -p "$L"
exec > >(tee "$L/validate.log") 2>&1
export RLH_RESULTS_DIR=$OUT                       # read by compare_with_matlab.py, verify_run.py, five_seed_table.py
sim() { ./RLHybrid_Scalability_Experiment -u Cmdenv --result-dir="$OUT" "$@"; }
PY="python3 -I"
step() { echo; echo "=== $1 ==="; }
echo "validation output: $OUT"

step "Stage B: reference check (workload, topology, channel) for seeds 42-46"
sim -c ReferenceCheck > "$L/run_ReferenceCheck.log" 2>&1
$PY tools/compare_reference.py "$OUT" matlab_reference/data | tee "$L/stageB_reference_check.txt"

step "Stage C: seed-42 smoke test"
sim -c SmokeSeed42 > "$L/run_SmokeSeed42.log" 2>&1
grep -E "PDR|checks" "$L/run_SmokeSeed42.log"
$PY tools/compare_with_matlab.py SmokeSeed42 42 | tee "$L/stageC_seed42_vs_matlab.txt"
$PY tools/verify_run.py SmokeSeed42 42 | tee "$L/stageC_seed42_internal_checks.txt"

step "Stage D: five seeds 42-46"
sim -c FiveSeeds > "$L/run_FiveSeeds.log" 2>&1
$PY tools/compare_with_matlab.py FiveSeeds 42 43 44 45 46 | tee "$L/stageD_five_seeds_vs_matlab.txt"
$PY tools/five_seed_table.py FiveSeeds > "$L/stageD_five_seed_table.md"
echo "table: $L/stageD_five_seed_table.md"

step "Stage E: internal verification of the five-seed runs"
$PY tools/verify_run.py FiveSeeds 42 43 44 45 46 > "$L/stageE_internal_checks.txt"
tail -1 "$L/stageE_internal_checks.txt"
echo; echo "ALL STAGES PASSED"
