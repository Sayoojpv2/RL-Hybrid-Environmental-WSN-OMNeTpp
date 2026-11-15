#!/bin/bash
# Imports this project into a FRESH, temporary OMNeT++ IDE workspace and builds it
# with the IDE's own project builders (Eclipse CDT headless build application).
# Run inside the OMNeT++ shell. It does not touch your normal IDE workspace:
#   - workspace:           $TMPBASE/workspace   (deleted and recreated each time)
#   - configuration area:  $TMPBASE/config      (cascaded on top of the IDE's own, read-only)
set -e
PROJ="$(cd "$(dirname "$0")" && pwd)"
IDE="$__omnetpp_root_dir/ide"
TMPBASE="${TMPBASE:-$(cygpath -u "$LOCALAPPDATA")/Temp/rlhybrid_scalability_ide_check}"
rm -rf "$TMPBASE"; mkdir -p "$TMPBASE/workspace" "$TMPBASE/config"
W() { cygpath -w "$1"; }

cd "$PROJ"
"$IDE/opp_idec.exe" -nosplash \
    -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
    -data "$(W "$TMPBASE/workspace")" \
    -configuration "$(W "$TMPBASE/config")" \
    -import "$(W "$PROJ")" \
    -build "RLHybrid_Scalability_Experiment/${1:-debug}" \
    -vmargs -Dosgi.configuration.cascaded=true \
            "-Dosgi.sharedConfiguration.area=$(W "$IDE/configuration")"
