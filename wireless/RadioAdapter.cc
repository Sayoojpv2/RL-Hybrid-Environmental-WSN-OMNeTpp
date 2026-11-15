//
// RadioAdapter / PilotSource - the INET-dependent part of communicationModel = "ieee802154" (plugin RLHybridWireless).
//
// RadioAdapter sits between a node's logic (RL-Hybrid SensorNode / BaseStation, or a PilotSource) and its INET
// Ieee802154NarrowbandInterface:
//  * down: a logic frame (cPacket; kind = next-hop node id, numNodes+1 = BS) is wrapped in an INET Packet
//    (cPacketChunk, length = the frame's bit length), tagged with the next hop's MAC address, and handed to the MAC;
//  * up:   a received INET Packet is unwrapped (a copy of the frame) and passed to the logic;
//  * MAC failures of this node's own frames (retry limit, CSMA channel-access failure, queue overflow) are reported to
//    the logic as a notice named like the frame;
//  * radio state times and radio energy are integrated from the radio's own state signals with the power values of the
//    radio's StateBasedEpEnergyConsumer (one source of truth), split into the rounds' active windows and the idle gaps
//    between rounds, and cross-checked against INET's IdealEpEnergyStorage balance.
//
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "inet/common/INETDefs.h"
#include "inet/common/Protocol.h"
#include "inet/common/ProtocolGroup.h"
#include "inet/common/ProtocolTag_m.h"
#include "inet/common/Simsignals.h"
#include "inet/common/Simsignals_m.h"
#include "inet/common/packet/Packet.h"
#include "inet/common/packet/chunk/cPacketChunk.h"
#include "inet/linklayer/common/MacAddressTag_m.h"
#include "inet/networklayer/common/NetworkInterface.h"
#include "inet/physicallayer/wireless/common/contract/packetlevel/IRadio.h"
#include "inet/physicallayer/wireless/common/contract/packetlevel/ITransmission.h"
#include "inet/physicallayer/wireless/common/contract/packetlevel/SignalTag_m.h"

namespace rlwireless {

using namespace omnetpp;
using namespace inet;
using physicallayer::IRadio;
using physicallayer::ITransmission;
static const short KIND_TX_ATTEMPT = 1;     // notice to the logic: a MAC transmission of its frame started (SensorNode.cc)

// RL-Hybrid frames are carried with IEEE 802 "Local Experimental EtherType 1" (0x88B5) as the MAC's network protocol
static const Protocol rlHybridProtocol("rlhybrid", "RL-Hybrid routing frame", Protocol::NetworkLayer);
// INET 4.7 keeps the ethertype protocol group per simulation run, so it is registered at every run's initialization
static void registerRlHybrid()
{
    ProtocolGroup *g = ProtocolGroup::getEthertypeProtocolGroup();
    if (g->findProtocolNumber(&rlHybridProtocol) == -1) g->addProtocol(0x88B5, &rlHybridProtocol);
}

class RadioAdapter : public cSimpleModule, public cListener
{
  protected:
    enum State { S_OFF, S_SLEEP, S_SWITCHING, S_RX_IDLE, S_RX_BUSY, S_RX_RECEIVING, S_TX_IDLE, S_TX, NUM_STATES };
    cModule *host = nullptr, *mac = nullptr;
    IRadio *radio = nullptr;
    std::string myPrefix;                          // "rl:<nodeId>:" (frames of this node)
    std::map<int, MacAddress> macCache;
    std::vector<std::string> notices;
    std::string lastNotice;
    cMessage *flushTimer = nullptr;
    simsignal_t roundStartSignal = 0, roundEndSignal = 0, storageSignal = 0;
    // radio accounting
    double P[NUM_STATES] = {};                     // W, from the radio's energy consumer (0 without one)
    double tActive[NUM_STATES] = {}, tGap[NUM_STATES] = {};
    double eActive = 0, eGap = 0;
    bool inRound = false, hasConsumer = false;
    simtime_t lastChange;
    int lastState = S_OFF;                         // radio state being integrated since lastChange
    double storageBalance = 0;                     // last balance published by the IdealEpEnergyStorage (J, negative)
    simtime_t storageTime;
    long rounds = 0;
    // counters
    double rssiSum = 0, rssiMin = INFINITY, snirSum = 0, snirMin = INFINITY;
    long rssiN = 0, snirN = 0;
    long framesDown = 0, framesUp = 0, corrupted = 0, duplicates = 0, overheard = 0;
    long dropRetry = 0, dropCongestion = 0, dropQueue = 0, dropOther = 0, linkBroken = 0;

    virtual int numInitStages() const override { return NUM_INIT_STAGES; }
    virtual void initialize(int stage) override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;
    virtual void receiveSignal(cComponent *src, simsignal_t id, intval_t value, cObject *details) override;
    virtual void receiveSignal(cComponent *src, simsignal_t id, double value, cObject *details) override;
    virtual void receiveSignal(cComponent *src, simsignal_t id, cObject *obj, cObject *details) override;
    int state() const;
    void account();
    void notice(const char *name);
    bool isMine(const char *name) const { return !myPrefix.empty() && std::strncmp(name, myPrefix.c_str(), myPrefix.size()) == 0; }
    MacAddress macOf(int id);

  public:
    virtual ~RadioAdapter() { cancelAndDelete(flushTimer); }
};

Define_Module(RadioAdapter);

void RadioAdapter::initialize(int stage)
{
    if (stage == INITSTAGE_LOCAL) {
        registerRlHybrid();
        host = getParentModule();
        cModule *wlan = host->getSubmodule("wlan");
        mac = wlan->getSubmodule("mac");
        radio = check_and_cast<IRadio *>(wlan->getSubmodule("radio"));
        if (host->hasPar("nodeId")) myPrefix = "rl:" + std::to_string(host->par("nodeId").intValue()) + ":";
        flushTimer = new cMessage("flushNotices");
        // power per radio state = the radio's StateBasedEpEnergyConsumer parameters (W); nodes without one draw 0
        cModule *consumer = check_and_cast<cModule *>(wlan->getSubmodule("radio"))->getSubmodule("energyConsumer");
        if (consumer && consumer->hasPar("receiverIdlePowerConsumption")) {
            hasConsumer = true;
            P[S_OFF] = consumer->par("offPowerConsumption").doubleValue();
            P[S_SLEEP] = consumer->par("sleepPowerConsumption").doubleValue();
            P[S_SWITCHING] = consumer->par("switchingPowerConsumption").doubleValue();
            P[S_RX_IDLE] = consumer->par("receiverIdlePowerConsumption").doubleValue();
            P[S_RX_BUSY] = consumer->par("receiverBusyPowerConsumption").doubleValue();
            P[S_RX_RECEIVING] = consumer->par("receiverReceivingPowerConsumption").doubleValue();
            P[S_TX_IDLE] = consumer->par("transmitterIdlePowerConsumption").doubleValue();
            P[S_TX] = consumer->par("transmitterTransmittingPowerConsumption").doubleValue();
            for (const char *p : {"receiverReceivingPreamblePowerConsumption", "receiverReceivingHeaderPowerConsumption",
                                  "receiverReceivingDataPowerConsumption"})
                if (consumer->par(p).doubleValue() != P[S_RX_RECEIVING]) throw cRuntimeError("%s must equal receiverReceivingPowerConsumption", p);
            for (const char *p : {"transmitterTransmittingPreamblePowerConsumption", "transmitterTransmittingHeaderPowerConsumption",
                                  "transmitterTransmittingDataPowerConsumption"})
                if (consumer->par(p).doubleValue() != P[S_TX]) throw cRuntimeError("%s must equal transmitterTransmittingPowerConsumption", p);
        }
        host->subscribe(IRadio::radioModeChangedSignal, this);
        host->subscribe(IRadio::receptionStateChangedSignal, this);
        host->subscribe(IRadio::transmissionStateChangedSignal, this);
        host->subscribe(transmissionStartedSignal, this);
        host->subscribe(packetDroppedSignal, this);
        host->subscribe(linkBrokenSignal, this);
        storageSignal = registerSignal("residualEnergyCapacityChanged");
        if (host->getSubmodule("energyStorage")) host->getSubmodule("energyStorage")->subscribe(storageSignal, this);
        roundStartSignal = registerSignal("rlRoundStart");
        roundEndSignal = registerSignal("rlRoundEnd");
        cModule *net = getSimulation()->getSystemModule();
        net->subscribe(roundStartSignal, this);
        net->subscribe(roundEndSignal, this);
        inRound = net->getSubmodule("controller") == nullptr;   // pilot networks: the whole run is one active window
        lastChange = simTime();
        WATCH(framesDown);
        WATCH(framesUp);
        WATCH(corrupted);
    }
    else if (stage == INITSTAGE_LAST) {           // the radio has its initial mode now
        account();
        lastState = state();
    }
}

int RadioAdapter::state() const
{
    switch (radio->getRadioMode()) {
        case IRadio::RADIO_MODE_OFF: return S_OFF;
        case IRadio::RADIO_MODE_SLEEP: return S_SLEEP;
        case IRadio::RADIO_MODE_SWITCHING: return S_SWITCHING;
        case IRadio::RADIO_MODE_TRANSMITTER:
            return radio->getTransmissionState() == IRadio::TRANSMISSION_STATE_TRANSMITTING ? S_TX : S_TX_IDLE;
        case IRadio::RADIO_MODE_TRANSCEIVER:
            if (radio->getTransmissionState() == IRadio::TRANSMISSION_STATE_TRANSMITTING) return S_TX;
            // fall through: receiver part
        default:
            switch (radio->getReceptionState()) {
                case IRadio::RECEPTION_STATE_BUSY: return S_RX_BUSY;
                case IRadio::RECEPTION_STATE_RECEIVING: return S_RX_RECEIVING;
                default: return S_RX_IDLE;
            }
    }
}

void RadioAdapter::account()
{
    // integrate the state the radio was in since the last change (called before every state change and round boundary)
    double dt = (simTime() - lastChange).dbl();
    if (dt > 0) {
        int s = lastState;
        (inRound ? tActive : tGap)[s] += dt;
        (inRound ? eActive : eGap) += P[s] * dt;
    }
    lastChange = simTime();
}

void RadioAdapter::receiveSignal(cComponent *src, simsignal_t id, intval_t value, cObject *details)
{
    if (id == IRadio::radioModeChangedSignal || id == IRadio::receptionStateChangedSignal || id == IRadio::transmissionStateChangedSignal) {
        account();
        lastState = state();                       // the radio already holds its new state
    }
    else if (id == roundStartSignal) { account(); inRound = true; rounds++; }
    else if (id == roundEndSignal) { account(); inRound = false; }
}

void RadioAdapter::receiveSignal(cComponent *src, simsignal_t id, double value, cObject *details)
{
    if (id == storageSignal) { storageBalance = value; storageTime = simTime(); }
}

void RadioAdapter::receiveSignal(cComponent *src, simsignal_t id, cObject *obj, cObject *details)
{
    if (id == transmissionStartedSignal) {   // a MAC transmission (first or retry) of this node's own frame
        const char *name = check_and_cast<const ITransmission *>(obj)->getPacket()->getName();
        if (isMine(name)) { Enter_Method_Silent(); send(new cMessage(name, KIND_TX_ATTEMPT), "upperOut"); }
        return;
    }
    auto pk = dynamic_cast<Packet *>(obj);
    if (!pk) return;
    if (id == linkBrokenSignal) {
        if (isMine(pk->getName())) { linkBroken++; notice(pk->getName()); }
    }
    else if (id == packetDroppedSignal) {
        auto d = dynamic_cast<PacketDropDetails *>(details);
        int reason = d ? d->getReason() : OTHER_PACKET_DROP;
        if (isMine(pk->getName())) {               // this node's own frame was given up
            if (reason == RETRY_LIMIT_REACHED) dropRetry++;
            else if (reason == CONGESTION) dropCongestion++;
            else if (reason == QUEUE_OVERFLOW) dropQueue++;
            else dropOther++;
            notice(pk->getName());
        }
        else if (reason == INCORRECTLY_RECEIVED) corrupted++;   // bit errors: collision, interference or noise
        else if (reason == DUPLICATE_DETECTED) duplicates++;
        else if (reason == NOT_ADDRESSED_TO_US) overheard++;
    }
}

void RadioAdapter::notice(const char *name)
{
    Enter_Method_Silent();
    if (lastNotice == name) return;               // linkBroken and packetDropped report the same failure
    lastNotice = name;
    notices.push_back(name);
    if (!flushTimer->isScheduled()) scheduleAt(simTime(), flushTimer);
}

MacAddress RadioAdapter::macOf(int id)
{
    auto it = macCache.find(id);
    if (it != macCache.end()) return it->second;
    cModule *net = getSimulation()->getSystemModule();
    int n = net->par("numNodes").intValue();
    cModule *dst = (id == n + 1) ? net->getSubmodule("bs") : net->getSubmodule("node", id - 1);
    if (!dst) throw cRuntimeError("no radio node with id %d", id);
    MacAddress a = check_and_cast<NetworkInterface *>(dst->getSubmodule("wlan"))->getMacAddress();
    macCache[id] = a;
    return a;
}

void RadioAdapter::handleMessage(cMessage *msg)
{
    if (msg == flushTimer) {
        for (auto& n : notices) send(new cMessage(n.c_str()), "upperOut");
        notices.clear();
        return;
    }
    if (msg->arrivedOn("upperIn")) {
        if (!msg->isPacket()) {                    // control from the node logic
            if (std::strcmp(msg->getName(), "radioOff") == 0) radio->setRadioMode(IRadio::RADIO_MODE_OFF);
            delete msg;
            return;
        }
        auto f = check_and_cast<cPacket *>(msg);
        int dest = f->getKind();
        auto pk = new Packet(f->getName(), makeShared<cPacketChunk>(f));
        pk->addTag<MacAddressReq>()->setDestAddress(macOf(dest));
        pk->addTag<PacketProtocolTag>()->setProtocol(&rlHybridProtocol);
        framesDown++;
        send(pk, "lowerLayerOut");
        return;
    }
    auto pk = check_and_cast<Packet *>(msg);       // from the interface: a frame addressed to this node
    if (auto p = pk->findTag<SignalPowerInd>()) {  // RSSI and SNIR of the accepted frame (INET has no 802.15.4 LQI)
        double dBm = 10 * std::log10(p->getPower().get() * 1000);
        rssiSum += dBm; rssiMin = std::min(rssiMin, dBm); rssiN++;
    }
    if (auto s = pk->findTag<SnirInd>()) {
        double dB = 10 * std::log10(s->getMinimumSnir());
        snirSum += dB; snirMin = std::min(snirMin, dB); snirN++;
    }
    cPacket *f = pk->peekAtFront<cPacketChunk>()->getPacket()->dup();
    delete pk;
    framesUp++;
    send(f, "upperOut");
}

void RadioAdapter::finish()
{
    account();
    const char *names[NUM_STATES] = {"off", "sleep", "switching", "rxIdle", "rxBusy", "rxReceiving", "txIdle", "tx"};
    double tA = 0, tG = 0;
    for (int s = 0; s < NUM_STATES; s++) {
        recordScalar((std::string("timeActive:") + names[s]).c_str(), tActive[s], "s");
        recordScalar((std::string("timeGap:") + names[s]).c_str(), tGap[s], "s");
        tA += tActive[s]; tG += tGap[s];
    }
    recordScalar("timeActive", tA, "s");
    recordScalar("timeGap", tG, "s");
    recordScalar("rounds", rounds);
    recordScalar("radioEnergyActive", eActive, "J");
    recordScalar("radioEnergyGap", eGap, "J");
    if (hasConsumer && host->getSubmodule("energyStorage")) {
        // INET's own integral: last published storage balance + the power drawn since (the radio is the only consumer)
        double inetJ = -storageBalance + P[lastState] * (simTime() - storageTime).dbl();
        recordScalar("radioEnergyInet", inetJ, "J");
    }
    for (int s = 0; s < NUM_STATES; s++) recordScalar((std::string("power:") + names[s]).c_str(), P[s], "W");
    recordScalar("rssiMean", rssiN ? rssiSum / rssiN : NAN, "dBm");    // over the frames this node accepted
    recordScalar("rssiMin", rssiN ? rssiMin : NAN, "dBm");
    recordScalar("snirMinMean", snirN ? snirSum / snirN : NAN, "dB");  // per-frame minimum SNIR, averaged
    recordScalar("snirMin", snirN ? snirMin : NAN, "dB");
    recordScalar("framesDown", framesDown);
    recordScalar("framesUp", framesUp);
    recordScalar("corruptedReceptions", corrupted);
    recordScalar("duplicatesDropped", duplicates);
    recordScalar("overheardFrames", overheard);
    recordScalar("dropRetryLimit", dropRetry);
    recordScalar("dropChannelAccess", dropCongestion);
    recordScalar("dropQueueOverflow", dropQueue);
    recordScalar("dropOther", dropOther);
    recordScalar("linkBroken", linkBroken);
}

// ------------------------------------------------------------------------------------------- pilot traffic source

class PilotSource : public cSimpleModule
{
  protected:
    int id = 0, dest = -1, bytes = 0;
    long seq = 0, sent = 0, received = 0, failed = 0, macTx = 0;
    double delaySum = 0;
    std::ofstream log;
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;
};

Define_Module(PilotSource);

void PilotSource::initialize()
{
    id = par("nodeId").intValue();
    dest = par("destNode").intValue();
    bytes = par("payloadBytes").intValue();
    std::string lf = par("logFile").stdstringValue();
    if (!lf.empty()) {
        log.open(lf, std::ios::app);
        if (!log) throw cRuntimeError("cannot open %s", lf.c_str());
    }
    std::istringstream in(par("sendTimes").stdstringValue());
    double t;
    double jitter = par("sendJitter").doubleValue();      // unsynchronised node clocks (P3/P4)
    while (in >> t) scheduleAt(t + (jitter > 0 ? uniform(0, jitter) : 0), new cMessage("send"));
}

void PilotSource::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage()) {
        delete msg;
        char name[48];
        snprintf(name, sizeof(name), "rl:%d:%ld", id, ++seq);
        auto f = new cPacket(name, dest);          // kind = destination node id
        f->setBitLength(8L * bytes);
        f->setTimestamp(simTime());
        sent++;
        if (log.is_open()) log << getSimulation()->getActiveEnvir()->getConfigEx()->getActiveConfigName() << ",tx," << simTime() << "," << id << "," << name << "," << bytes << ",\n";
        send(f, "lowerLayerOut");
        return;
    }
    if (!msg->isPacket() && msg->getKind() == KIND_TX_ATTEMPT) { macTx++; delete msg; return; }
    const char *cfg = getSimulation()->getActiveEnvir()->getConfigEx()->getActiveConfigName();
    if (auto f = dynamic_cast<cPacket *>(msg)) {
        received++;
        double d = (simTime() - f->getTimestamp()).dbl();
        delaySum += d;
        if (log.is_open()) log << cfg << ",rx," << simTime() << "," << id << "," << f->getName() << "," << f->getBitLength() / 8 << "," << d << "\n";
    }
    else {
        failed++;
        if (log.is_open()) log << cfg << ",fail," << simTime() << "," << id << "," << msg->getName() << ",,\n";
    }
    delete msg;
}

void PilotSource::finish()
{
    recordScalar("framesSent", sent);
    recordScalar("framesReceived", received);
    recordScalar("framesFailed", failed);
    recordScalar("macTransmissions", macTx);       // attempt notices seen by the upper layer (= MAC nbTxFrames)
    recordScalar("meanDelay", received ? delaySum / received : NAN, "s");
}

}   // namespace rlwireless
