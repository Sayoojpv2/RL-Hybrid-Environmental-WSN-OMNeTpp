#!/bin/bash
# Builds the INET-dependent plugin wireless/libRLHybridWireless.dll (communicationModel = "ieee802154").
# Needs INET 4.7.0 built in release mode (samples/inet-4.7.0 of the OMNeT++ 6.4.0 installation, or INET_PROJ=<path>).
# Run in the OMNeT++ shell or through build_wireless.cmd. The main simulator (build.sh) does not depend on INET.
set -e
cd "$(dirname "$0")/wireless"
make MODE=release -j8 "$@"
