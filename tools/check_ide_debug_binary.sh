#!/bin/bash
# Runs the IDE-built debug executable for seed 42 into a separate folder and compares the
# result with the release-build seed-42 run in results/ (must be identical).
cd "$(dirname "$0")/.."
./RLHybrid_Scalability_Experiment_dbg -u Cmdenv -c SmokeSeed42 --result-dir=logs/ide_debug_run > logs/ide_debug_run.log 2>&1
for f in metrics.csv decisions.csv per_round.csv; do
  if cmp -s logs/ide_debug_run/SmokeSeed42-seed42-$f results/SmokeSeed42-seed42-$f; then
    echo "IDE-built debug binary: SmokeSeed42 $f byte-identical to the release build"
  else
    echo "IDE-built debug binary: SmokeSeed42 $f DIFFERS"
  fi
done
