#!/bin/bash
# Runs a communicationModel = "ieee802154" configuration: loads INET 4.7.0 (NED path + libINET.dll) and the plugin
# wireless/libRLHybridWireless.dll. The validated abstract configurations do not need this script.
# Usage (OMNeT++ shell):  ./run_wireless.sh -c <Config> [-f <ini file>] [-r '<run filter>'] [other options]
set -e
cd "$(dirname "$0")"
ROOT=$(cd "$(dirname "$(opp_configfilepath)")" && pwd)       # OMNeT++ installation
INET="${INET_PROJ:-$ROOT/samples/inet-4.7.0}"
[ -f "$INET/src/libINET.dll" ] || { echo "INET 4.7.0 release build not found in $INET/src (set INET_PROJ)"; exit 1; }
[ -f wireless/libRLHybridWireless.dll ] || { echo "plugin missing: run build_wireless.cmd first"; exit 1; }
export PATH="$INET/src:$(pwd)/wireless:$PATH"
# Without an explicit --result-dir, write to a new runs/wireless-<timestamp>/ folder instead of the configs'
# results_research_upgrade/ folders, so the published results are never overwritten by default.
case " $* " in
  *" --result-dir="*) out=() ;;
  *) out=(--result-dir="runs/wireless-$(date +%Y%m%d-%H%M%S)"); echo "result dir: ${out[0]#--result-dir=} (pass --result-dir to choose)" ;;
esac
exec ./RLHybrid_Scalability_Experiment -u Cmdenv -n ".;$(cygpath -m "$INET/src")" -l wireless/RLHybridWireless "${out[@]}" "$@"
