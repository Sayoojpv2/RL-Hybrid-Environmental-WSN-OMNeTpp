#!/bin/bash
# Teacher demonstration launcher: opens ONE of the five environmental scenarios of the existing
# [Config V2_200Node_Environmental] in Qtenv (N = 200, seed 42, abstract MATLAB-equivalent model),
# limited to a 20-round preview by command-line overrides (the ini file and the 500-round workload are unchanged).
#   ./teacher_demo.sh          menu (OMNeT++ shell)
#   ./teacher_demo.sh <1-5>    start one scenario directly (teacher_demo.cmd uses this)
# Every launch writes to a new runs/teacher_demo/<scenario>/<timestamp>/ folder, never an existing one and never a
# published results folder. Nothing is built here: run build.cmd first.
# DEMO_UI=Cmdenv runs the same launch without the GUI; DEMO_OUT_ROOT changes the output root (both only for checks).
cd "$(dirname "$0")" || exit 1
UI=${DEMO_UI:-Qtenv}
OUT_ROOT=${DEMO_OUT_ROOT:-runs/teacher_demo}
CONFIG=V2_200Node_Environmental
ROUNDS=20                              # preview length; the full experiment has 500 rounds
LIMIT=$((ROUNDS * 100))s               # roundPeriod = 100s (V2_200Node_Common): ends the run right after round 20
SCEN=(water effluent air soil mixed)
TITLES=("Water quality monitoring" "Industrial effluent monitoring" "Air quality monitoring"
        "Soil monitoring" "Mixed environmental monitoring")
DATA=("real KSPCB River Periyar water quality (10 station streams, replayed on the other nodes)"
      "synthetic effluent outfalls (generated values, not measurements)"
      "real UCI Beijing air quality (12 station streams, replayed on the other nodes)"
      "synthetic soil fields (generated values, not measurements)"
      "mix of the four profiles above, one profile per node")

err() { echo; echo "ERROR: $*"; echo; return 1; }

new_dir() {   # mkdir without -p fails if the folder exists, so an existing folder is never reused
    local base d i=1
    mkdir -p "$OUT_ROOT/$1" || return 1
    base="$OUT_ROOT/$1/$(date +%Y%m%d-%H%M%S)"; d=$base
    until mkdir "$d" 2>/dev/null; do i=$((i + 1)); [ $i -le 99 ] || return 1; d="$base-$i"; done
    echo "$d"
}

launch() {
    local k=$1 s=${SCEN[$1 - 1]} filter run out rc
    [ -e RLHybrid_Scalability_Experiment.exe ] || [ -e RLHybrid_Scalability_Experiment ] ||
        { err "the simulator is not built (RLHybrid_Scalability_Experiment.exe is missing). Run build.cmd first."; return; }
    filter="\"\$scenario\"==\"$s\" && \$N==200 && \$seed==42"
    run=$(./RLHybrid_Scalability_Experiment -s -c $CONFIG -r "$filter" -q runnumbers 2>/dev/null | tail -1)
    set -- $run
    [ $# -eq 1 ] || { err "the filter $filter selected '$run' in $CONFIG instead of exactly one run."; return; }
    out=$(new_dir "$s") || { err "could not create a new output folder under $OUT_ROOT/$s"; return; }
    echo
    echo "=== Scenario $k: ${TITLES[$k - 1]} ==="
    echo "  data:    ${DATA[$k - 1]}"
    echo "  network: 200 nodes + base station, seed 42, abstract MATLAB-equivalent channel"
    echo "  run:     $CONFIG run #$1 ($filter), preview of rounds 1-$ROUNDS of 500"
    echo "  output:  $out"
    [ "$UI" = Qtenv ] && echo "  In Qtenv press Run (or Step / Fast / Express); close the window to return to the menu."
    ./RLHybrid_Scalability_Experiment -u "$UI" -c $CONFIG -r "$1" --"**.controller.numRounds=$ROUNDS" \
        --sim-time-limit=$LIMIT --result-dir="$out"
    rc=$?
    local sum="$out/$CONFIG-$s-seed42-summary.txt"
    if rmdir "$out" 2>/dev/null; then   # rmdir only succeeds if the run wrote nothing
        echo "${TITLES[$k - 1]} closed (exit code $rc); no output was written."
    elif [ -f "$sum" ]; then
        echo "${TITLES[$k - 1]} closed (exit code $rc). Summary: $sum"
        grep -aE "rounds simulated|^scenario|PDR \(|residual energy" "$sum"
    else
        echo "${TITLES[$k - 1]} closed (exit code $rc) before the $ROUNDS rounds finished: no summary was written"
        echo "(it is written when the run ends; use Express to finish). Partial files: $out"
    fi
    return $rc
}

if [ -n "$1" ]; then
    case $1 in [1-5]) launch "$1"; exit $? ;; *) echo "usage: ./teacher_demo.sh [1-5]"; exit 2 ;; esac
fi
while true; do
    echo; echo "RL-Hybrid environmental WSN - 200 nodes, Qtenv demonstration"; echo
    for i in 1 2 3 4 5; do echo "  $i. ${TITLES[$i - 1]}"; done
    echo "  6. Exit"; echo
    read -rp "Select 1-6: " k || exit 0
    case $k in [1-5]) launch "$k" ;; 6) exit 0 ;; *) echo "Please enter a number from 1 to 6." ;; esac
done
