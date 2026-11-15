#!/bin/bash
# Runs the whole validation in order; each stage runs only if the previous one passed.
#   B: workload/topology/channel vs MATLAB   C: seed-42 smoke test   D: seeds 42-46   E: internal checks
# Run inside the OMNeT++ 6.4.0 Shell (or via validate.cmd). Builds nothing; run build.cmd first.
set -e -o pipefail
cd "$(dirname "$0")"
mkdir -p logs results
BIN=./RLHybrid_Scalability_Experiment
PY="python3 -I"
step() { echo; echo "=== $1 ==="; }

step "Stage B: reference check (workload, topology, channel) for seeds 42-46"
$BIN -u Cmdenv -c ReferenceCheck > logs/run_ReferenceCheck.log 2>&1
$PY tools/compare_reference.py results matlab_reference/data | tee logs/stageB_reference_check.txt

step "Stage C: seed-42 smoke test"
$BIN -u Cmdenv -c SmokeSeed42 > logs/run_SmokeSeed42.log 2>&1
grep -E "PDR|checks" logs/run_SmokeSeed42.log
$PY tools/compare_with_matlab.py SmokeSeed42 42 | tee logs/stageC_seed42_vs_matlab.txt
$PY tools/verify_run.py SmokeSeed42 42 | tee logs/stageC_seed42_internal_checks.txt

step "Stage D: five seeds 42-46"
$BIN -u Cmdenv -c FiveSeeds > logs/run_FiveSeeds.log 2>&1
$PY tools/compare_with_matlab.py FiveSeeds 42 43 44 45 46 | tee logs/stageD_five_seeds_vs_matlab.txt
$PY tools/five_seed_table.py FiveSeeds > logs/stageD_five_seed_table.md
echo "table: logs/stageD_five_seed_table.md"

step "Stage E: internal verification of the five-seed runs"
$PY tools/verify_run.py FiveSeeds 42 43 44 45 46 > logs/stageE_internal_checks.txt
tail -1 logs/stageE_internal_checks.txt
echo; echo "ALL STAGES PASSED"
