#!/bin/bash
# Builds ONLY this project (never the IDE workspace, never INET).
# Run inside the "OMNeT++ 6.4.0 Shell", or via build.cmd on Windows.
set -e
cd "$(dirname "$0")"
# The Makefile is owned by the OMNeT++ IDE (generated from .oppbuildspec); only create one if missing.
[ -f Makefile ] || opp_makemake -f --deep
make MODE=release -j4
echo "Build finished: $(pwd)/RLHybrid_Scalability_Experiment.exe"
