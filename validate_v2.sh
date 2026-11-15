#!/bin/bash
# v2 re-validation of the 50-node MATLAB reproduction WITHOUT touching the v1 results/ directory:
# the simulations run from the project folder with --result-dir=${VALDIR}/results and the unchanged
# comparison scripts run inside ${VALDIR}/ (which holds copies of tools/ and matlab_reference/).
set -e -o pipefail
VALDIR=${VALDIR:-validation_v2}   # output folder; must contain copies of tools/ and data/ and matlab_reference/
cd "$(dirname "$0")"
BIN=./RLHybrid_Scalability_Experiment
RD=${VALDIR}/results
PY="python3 -I"
step() { echo; echo "=== $1 ==="; }
step "Stage B: reference check (workload, topology, channel) for seeds 42-46"
$BIN -u Cmdenv -c ReferenceCheck --result-dir=$RD > ${VALDIR}/logs/run_ReferenceCheck.log 2>&1
(cd ${VALDIR} && $PY tools/compare_reference.py results matlab_reference/data | tee logs/stageB_reference_check.txt)
step "Stage C: seed-42 smoke test"
$BIN -u Cmdenv -c SmokeSeed42 --result-dir=$RD > ${VALDIR}/logs/run_SmokeSeed42.log 2>&1
(cd ${VALDIR} && $PY tools/compare_with_matlab.py SmokeSeed42 42 | tee logs/stageC_seed42_vs_matlab.txt)
(cd ${VALDIR} && $PY tools/verify_run.py SmokeSeed42 42 | tee logs/stageC_seed42_internal_checks.txt)
step "Stage D: five seeds 42-46"
$BIN -u Cmdenv -c FiveSeeds --result-dir=$RD > ${VALDIR}/logs/run_FiveSeeds.log 2>&1
(cd ${VALDIR} && $PY tools/compare_with_matlab.py FiveSeeds 42 43 44 45 46 | tee logs/stageD_five_seeds_vs_matlab.txt)
step "Stage E: internal verification of the five-seed runs"
(cd ${VALDIR} && $PY tools/verify_run.py FiveSeeds 42 43 44 45 46 > logs/stageE_internal_checks.txt; tail -1 logs/stageE_internal_checks.txt)
step "Byte identity with the archived v1 baseline (logs/baseline_unmodified_copy)"
n=0; d=0
for f in logs/baseline_unmodified_copy/*; do n=$((n+1)); cmp -s "$f" "$RD/$(basename "$f")" || { d=$((d+1)); echo "DIFF $(basename "$f")"; }; done
echo "$n files compared, $d different" | tee ${VALDIR}/logs/byte_identity_vs_unmodified_copy.txt
[ "$d" = 0 ]
echo; echo "ALL STAGES PASSED"
