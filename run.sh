#!/bin/bash
# Usage: ./run.sh <Config> [scenario|all] [nodes]     abstract-model configurations in Cmdenv (OMNeT++ shell or run.cmd)
# Results go to $RESULT_DIR if set, otherwise to a new runs/<Config>-<timestamp>/ folder, so the historical
# results folders are never written by default. Console log: logs/run_<Config>[_<scenario>_<nodes>]_<timestamp>.log
set -e -o pipefail
cd "$(dirname "$0")"
[ -n "$1" ] || { echo "usage: ./run.sh <Config> [scenario|all] [nodes]"; exit 2; }
cfg=$1 scn=$2 n=${3:-200}
ts=$(date +%Y%m%d-%H%M%S)
out=${RESULT_DIR:-runs/$cfg-$ts}
filter=()
if [ "$scn" = all ]; then filter=(-r "\$N==$n")
elif [ -n "$scn" ]; then filter=(-r "\"\$scenario\"==\"$scn\" && \$N==$n"); fi
log=logs/run_$cfg${scn:+_${scn}_$n}_$ts.log
mkdir -p logs "$out"
echo "result dir: $out    log: $log"
./RLHybrid_Scalability_Experiment -u Cmdenv -c "$cfg" "${filter[@]}" --result-dir="$out" 2>&1 | tee "$log"
