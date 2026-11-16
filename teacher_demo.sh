#!/bin/bash
# Teacher demonstration launcher: opens ONE of five existing short (20-round) configurations in Qtenv.
#   ./teacher_demo.sh          menu (OMNeT++ shell)
#   ./teacher_demo.sh <1-5>    start one demo directly (teacher_demo.cmd uses this)
# Every launch writes to a new runs/teacher_demo/<Config>-<timestamp>/ folder (never an existing one, never a
# published results folder). Nothing is built here: run build.cmd (and build_wireless.cmd for demo 5) first.
# DEMO_UI=Cmdenv runs the same launch without the GUI; DEMO_OUT_ROOT changes the output root (both only for checks).
cd "$(dirname "$0")" || exit 1
UI=${DEMO_UI:-Qtenv}
OUT_ROOT=${DEMO_OUT_ROOT:-runs/teacher_demo}
CONFIGS=(V2_10Node_Smoke GuiDemo20Rounds Periyar250_GuiPreview Synthetic_Smoke W10_Smoke)
TITLES=("10-node Periyar real-data demo (KSPCB-derived water-quality reports)"
        "50-node MATLAB-equivalent demo (recommended first)"
        "250-node network preview (10 sources + 240 relays)"
        "Synthetic environmental monitoring demo (generated values, not measurements)"
        "IEEE 802.15.4 wireless demo (INET 4.7.0 MAC/PHY)")

err() { echo; echo "ERROR: $*"; echo; return 1; }

new_dir() {   # mkdir without -p fails if the folder exists, so an existing folder is never reused
    local base d i=1
    mkdir -p "$OUT_ROOT" || return 1
    base="$OUT_ROOT/$1-$(date +%Y%m%d-%H%M%S)"; d=$base
    until mkdir "$d" 2>/dev/null; do i=$((i + 1)); [ $i -le 99 ] || return 1; d="$base-$i"; done
    echo "$d"
}

launch() {
    local k=$1 cfg=${CONFIGS[$1 - 1]} out rc
    [ -e RLHybrid_Scalability_Experiment.exe ] || [ -e RLHybrid_Scalability_Experiment ] ||
        { err "the simulator is not built (RLHybrid_Scalability_Experiment.exe is missing). Run build.cmd first."; return; }
    if [ "$cfg" = W10_Smoke ] && [ ! -e wireless/libRLHybridWireless.dll ]; then
        err "the wireless plugin wireless/libRLHybridWireless.dll is missing. Build INET 4.7.0 (release) and run build_wireless.cmd first."; return
    fi
    out=$(new_dir "$cfg") || { err "could not create a new output folder under $OUT_ROOT"; return; }
    echo
    echo "Demo $k: ${TITLES[$k - 1]}"
    echo "  configuration: $cfg (existing, 20 rounds)   user interface: $UI"
    echo "  output folder: $out"
    [ "$UI" = Qtenv ] && echo "  In Qtenv press Run (or Step / Fast / Express); close the window to return to the menu."
    if [ "$cfg" = W10_Smoke ]; then
        OPP_UI=$UI ./run_wireless.sh -c "$cfg" -r 0 --result-dir="$out"     # loads INET and the plugin
    else
        ./RLHybrid_Scalability_Experiment -u "$UI" -c "$cfg" -r 0 --result-dir="$out"
    fi
    rc=$?
    if rmdir "$out" 2>/dev/null; then   # rmdir only succeeds if the run wrote nothing
        echo "Demo $k closed (exit code $rc); no output was written."
    else
        echo "Demo $k closed (exit code $rc). Output: $out"
    fi
    return $rc
}

if [ -n "$1" ]; then
    case $1 in [1-5]) launch "$1"; exit $? ;; *) echo "usage: ./teacher_demo.sh [1-5]"; exit 2 ;; esac
fi
while true; do
    echo; echo "RL-Hybrid Environmental WSN - teacher demonstration (OMNeT++ Qtenv)"; echo
    for i in 1 2 3 4 5; do echo "  $i. ${TITLES[$i - 1]}"; done
    echo "  6. Exit"; echo
    read -rp "Select 1-6: " k || exit 0
    case $k in [1-5]) launch "$k" ;; 6) exit 0 ;; *) echo "Please enter a number from 1 to 6." ;; esac
done
