//
// communicationModel = "ieee802154": the same RL-Hybrid nodes on INET 4.7.0's IEEE 802.15.4 narrowband interface
// (Ieee802154NarrowbandMac: non-beacon CSMA/CA with MAC ACKs and retries; Ieee802154NarrowbandScalarRadio; the
// Ieee802154NarrowbandScalarRadioMedium with its 802.15.4 path loss and background noise).
//
// INET types are named in full and nothing here extends an INET type, so the validated abstract model keeps loading
// this project without INET on the NED path. Wireless runs need:  -n .;<INET>/src  -l wireless/RLHybridWireless
// (run_wireless.sh does this). The C++ of RadioAdapter and PilotSource is in wireless/ (an INET-dependent plugin).
//

// RL-Hybrid node logic (class SensorNode) with the gates to its radio adapter
simple RlWirelessNode extends SensorNode
{
    parameters:
        @class(SensorNode);
    gates:
        input lowerLayerIn;
        output lowerLayerOut;
}

simple RlWirelessBaseStation extends BaseStation
{
    parameters:
        @class(BaseStation);
    gates:
        input lowerLayerIn;
        output lowerLayerOut;
}

// Carries RL-Hybrid frames over the INET interface: wraps each frame in an INET packet for the next hop's MAC address,
// reports MAC failures (retry limit, CSMA channel-access failure, queue overflow) to the node logic, and measures radio
// state times and radio energy (rounds split into the active window and the idle gap between rounds).
simple RadioAdapter
{
    parameters:
        @class(rlwireless::RadioAdapter);
        @signal[rlRadioEnergy](type=double);
    gates:
        input upperIn;
        output upperOut;
        input lowerLayerIn;
        output lowerLayerOut;
}

// Pilot traffic source (wireless pilot tests only): sends frames of a given payload to one destination at given times
simple PilotSource
{
    parameters:
        @class(rlwireless::PilotSource);
        int nodeId;
        int destNode = default(-1);             // -1: receive only
        string sendTimes = default("");         // space-separated send times (s)
        double sendJitter @unit(s) = default(0s);   // each send time + uniform(0, sendJitter)
        int payloadBytes = default(34);         // routing header + one report payload (bytes)
        string logFile = default("");
    gates:
        input lowerLayerIn;
        output lowerLayerOut;
}

module WirelessSensor
{
    parameters:
        int nodeId;
        @networkNode;
        @display("i=misc/node_vs");
        **.mobilityModule = default(absPath(".mobility"));      // INET antenna / radio position
    gates:
        input radioIn @directIn;
    submodules:
        mobility: inet.mobility.static.StationaryMobility {
            initFromDisplayString = true;               // x, y = "p" display tag, written by the controller (full precision)
        }
        interfaceTable: inet.networklayer.common.InterfaceTable;
        energyStorage: inet.power.storage.IdealEpEnergyStorage;   // energy meter (never depletes); see RadioAdapter
        wlan: inet.linklayer.ieee802154.Ieee802154NarrowbandInterface {
            interfaceTableModule = "^.interfaceTable";
            energySourceModule = "^.energyStorage";
        }
        adapter: RadioAdapter;
        rl: RlWirelessNode {
            nodeId = parent.nodeId;
        }
    connections:
        radioIn --> wlan.radioIn;
        rl.lowerLayerOut --> adapter.upperIn;
        adapter.upperOut --> rl.lowerLayerIn;
        adapter.lowerLayerOut --> wlan.upperLayerIn;
        wlan.upperLayerOut --> adapter.lowerLayerIn;
}

module WirelessBaseStation
{
    parameters:
        @networkNode;
        @display("i=device/antennatower");
        **.mobilityModule = default(absPath(".mobility"));      // INET antenna / radio position
    gates:
        input radioIn @directIn;
    submodules:
        mobility: inet.mobility.static.StationaryMobility {
            initFromDisplayString = true;               // x, y = "p" display tag, written by the controller (full precision)
        }
        interfaceTable: inet.networklayer.common.InterfaceTable;
        wlan: inet.linklayer.ieee802154.Ieee802154NarrowbandInterface {
            interfaceTableModule = "^.interfaceTable";
        }
        adapter: RadioAdapter;
        logic: RlWirelessBaseStation;
    connections:
        radioIn --> wlan.radioIn;
        logic.lowerLayerOut --> adapter.upperIn;
        adapter.upperOut --> logic.lowerLayerIn;
        adapter.lowerLayerOut --> wlan.upperLayerIn;
        wlan.upperLayerOut --> adapter.lowerLayerIn;
}

module PilotNode
{
    parameters:
        int nodeId;
        @networkNode;
        **.mobilityModule = default(absPath(".mobility"));      // INET antenna / radio position
    gates:
        input radioIn @directIn;
    submodules:
        mobility: inet.mobility.static.StationaryMobility {
            initFromDisplayString = false;              // position = initialX/Y/Z from wireless/pilot.ini
        }
        interfaceTable: inet.networklayer.common.InterfaceTable;
        energyStorage: inet.power.storage.IdealEpEnergyStorage;
        wlan: inet.linklayer.ieee802154.Ieee802154NarrowbandInterface {
            interfaceTableModule = "^.interfaceTable";
            energySourceModule = "^.energyStorage";
        }
        adapter: RadioAdapter;
        app: PilotSource {
            nodeId = parent.nodeId;
        }
    connections:
        radioIn --> wlan.radioIn;
        app.lowerLayerOut --> adapter.upperIn;
        adapter.upperOut --> app.lowerLayerIn;
        adapter.lowerLayerOut --> wlan.upperLayerIn;
        wlan.upperLayerOut --> adapter.lowerLayerIn;
}

// The environmental WSN on IEEE 802.15.4: same controller, node logic, topology, workload and routing as PeriyarRiverNetwork
network PeriyarWirelessNetwork
{
    parameters:
        int numNodes = default(200);            // battery nodes; node[k] has id k+1, the BS has id numNodes+1
    submodules:
        controller: Controller;
        radioMedium: inet.physicallayer.wireless.ieee802154.packetlevel.Ieee802154NarrowbandScalarRadioMedium;
        bs: WirelessBaseStation;
        node[numNodes]: WirelessSensor {
            nodeId = index + 1;
        }
}

// Pilot network for the wireless tests (wireless/pilot.ini): a few nodes with fixed positions and scripted traffic
network WirelessPilotNetwork
{
    parameters:
        int numNodes = default(2);
    submodules:
        radioMedium: inet.physicallayer.wireless.ieee802154.packetlevel.Ieee802154NarrowbandScalarRadioMedium;
        node[numNodes]: PilotNode {
            nodeId = index + 1;
        }
}
