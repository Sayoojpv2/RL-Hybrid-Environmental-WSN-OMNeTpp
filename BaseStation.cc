#include "BaseStation.h"
#include "Controller.h"
#include "SensorNode.h"

Define_Module(BaseStation);

void BaseStation::initialize(int stage)
{
    if (stage == 0) {
        cModule *c = findModuleByPath("^.controller");             // ieee802154: inside a WirelessBaseStation module
        ctl = check_and_cast<Controller *>(c ? c : getModuleByPath("^.^.controller"));
        delaySignal = registerSignal("pathDelay");
        latencySignal = registerSignal("latency");
        hopsSignal = registerSignal("hops");
        WATCH(deliveredReports);
    }
    // (the display position is set by Controller::setupDisplay)
}

void BaseStation::handleMessage(cMessage *msg)
{
    if (ctl->wirelessMode() && !dynamic_cast<DataFrame *>(msg)) { delete msg; return; }   // adapter notices (the BS sends no data)
    auto f = check_and_cast<DataFrame *>(msg);
    const int BS_ID = ctl->scenario().numNodes + 1;
    bool decodedOk;
    if (ctl->wirelessMode()) {                     // the 802.15.4 receiver already decided; drop MAC duplicates
        if (lastSeqFrom.empty()) lastSeqFrom.assign(BS_ID, 0);
        if (f->getTxSeq() <= lastSeqFrom[f->getSenderId()]) { delete f; return; }
        lastSeqFrom[f->getSenderId()] = f->getTxSeq();
        decodedOk = true;
    }
    else decodedOk = ctl->decodedAttempt(f->getSenderId(), BS_ID, f->getAttempt(), f->getTxSeq());   // success_history(curr, bs, r) for attempt 0
    ctl->noteHop(f->getSenderId(), BS_ID, decodedOk);           // display only
    if (!decodedOk) {
        framesLost++;
        delete f;
        return;
    }
    framesReceived++;
    Controller::RoundCounters& rc = ctl->counters();
    rc.successfulFrames++;                           // line 384
    double hopDelay = (simTime() - f->getTxStart()).dbl() + par("processingDelay").doubleValue();
    for (int i = 0; i < (int)f->getReportsArraySize(); i++) {
        ReportRecord r = f->getReports(i);
        r.pathDelay += hopDelay;                     // carriedDelay + reports*hopDelay (lines 386-387)
        int hops = f->getHops() + (r.ingressHop ? 1 : 0);   // lines 388-393
        rc.delayDelivered += r.pathDelay;
        rc.hopTotal += hops;
        rc.hopReports++;
        deliveredReports++;
        emit(delaySignal, r.pathDelay);
        emit(hopsSignal, (long)hops);
        // OMNeT++-only: time from the start of the report's round to reception at the BS
        emit(latencySignal, simTime() - ctl->roundStartTime(r.round));
        ctl->setFate(r, FATE_DELIVERED, hops, r.pathDelay);
    }
    auto ack = new LinkAck("ack");
    ack->setReceiverId(BS_ID);
    ack->setTxSeq(f->getTxSeq());
    ack->setRxOk(true);
    ack->setAtBS(true);
    ack->setReceiverEnergy(1);
    ack->setKind(1);                                 // animation colour only (green)
    SensorNode *snd = ctl->node(f->getSenderId());
    sendDirect(ack, ctl->scenario().distBS(f->getSenderId() - 1) / 3e8, 0, snd->gate("radioIn"));
    delete f;
}

void BaseStation::refreshDisplay() const
{
    // display only: the label is just the module name "BS"; the count is in the tooltip
    char buf[100];
    snprintf(buf, sizeof(buf), "Base station (600, 25) m - reports delivered: %ld", deliveredReports);
    const_cast<BaseStation *>(this)->getDisplayString().setTagArg("tt", 0, buf);
}

void BaseStation::finish()
{
    recordScalar("deliveredReports", deliveredReports);
    recordScalar("framesReceived", framesReceived);
    recordScalar("framesNotDecoded", framesLost);
}
