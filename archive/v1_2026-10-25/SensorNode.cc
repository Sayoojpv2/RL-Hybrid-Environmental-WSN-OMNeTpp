//
// SensorNode.cc - port of protocols/RL_Hybrid.m (MD5 407788e6...) onto OMNeT++ events.
// Line references are to RL_Hybrid.m. Ids are MATLAB ids (1..50, BS = 51).
//
#include "SensorNode.h"
#include "BaseStation.h"
#include "Controller.h"
#include "PeriyarModel.h"

#include <algorithm>
#include <cmath>
#include <limits>

Define_Module(SensorNode);

static const double ALPHA = 0.10, GAMMA = 0.90, MIN_LQ = 0.50, K_PRIOR = 2;   // lines 35-36, 50-51
// BS_ID and NUM_ACTIONS are members: N+1 for an N-node network (51 for the MATLAB 50-node network)

SensorNode::~SensorNode()
{
    cancelAndDelete(ackTimer);
    cancelAndDelete(processTimer);
    delete held;
}

void SensorNode::initialize(int stage)
{
    if (stage == 0) {
        myId = par("nodeId").intValue();
        ctl = check_and_cast<Controller *>(getModuleByPath("^.controller"));
        ackTimeout = par("ackTimeout");
        tProc = par("processingDelay");
        Rbit = par("bitRate").doubleValue();
        ackTimer = new cMessage("ackTimeout");
        processTimer = new cMessage("process");
        WATCH(E);
        WATCH(alive);
        WATCH(nodeLoad);
        WATCH(loadEWMA);
        WATCH(qUpdates);
    }
    else {
        sc = &ctl->scenario();
        n = sc->numNodes;
        E = E0 = sc->initialEnergy;
        BS_ID = n + 1;                 // MATLAB: bs = n + 1
        NUM_ACTIONS = n + 1;           // MATLAB: cfg.numActions = n + 1 (nodes 1..n and the BS)
        linkSucc.assign(n + 1, 0);
        linkAtt.assign(n + 1, 0);
    }
}

// ---------------------------------------------------------------- round hooks

void SensorNode::beginRound()
{
    nodeLoad = 0;                 // line 132: nodeLoad = zeros(1,n)
    clusterBuf.clear();           // clusterReports / clusterUnattempted
    clusterMembers.clear();
    ownReportValid = false;
}

void SensorNode::endRoundLoadUpdate()
{
    loadEWMA = 0.90 * loadEWMA + 0.10 * nodeLoad;   // line 476
}

bool SensorNode::applyMinimumEnergyRule()
{
    // lines 487-491: E < E_elec*k (one packet reception) -> unavailable from the next round
    if (alive && E < sc->Eelec * sc->packetSize) {
        setUnavailable(E == 0 ? "battery_depleted" : "below_minimum_radio_operation_energy");
        return true;
    }
    return false;
}

void SensorNode::setUnavailable(const char *why)
{
    alive = false;
    if (std::isnan(firstUnavailableRound)) {           // setUnavailable(): first reason only
        firstUnavailableRound = ctl->currentRound() + 1;
        reason = why;
    }
    ctl->logUnavailable(myId, why, E);
}

// ---------------------------------------------------------------- RL_Hybrid.m helpers

double SensorNode::qEst(int j) const
{
    // currentLinkEstimate(): (succ + K*p0) ./ (att + K), this node's OWN past outcomes only
    return (linkSucc[j - 1] + K_PRIOR * sc->priorLQ(myId - 1, j - 1)) / (linkAtt[j - 1] + K_PRIOR);
}

double SensorNode::dist(int target) const
{
    return target == BS_ID ? sc->distBS(myId - 1) : sc->distNode(myId - 1, target - 1);
}

int SensorNode::stateFor(int cand, int hops) const
{
    // hybridState(), lines 621-647
    rlhybrid::StateInputs s;
    s.currentEnergy = E / E0;
    double dCandidateBS;
    if (cand == BS_ID) {
        s.candidateEnergy = 1; s.distance = 0; s.candidateLoad = 0; dCandidateBS = 0; s.linkLQ = qEst(BS_ID);
    }
    else if (cand == myId) {
        s.candidateEnergy = E / E0; s.distance = 0; s.candidateLoad = loadForState();
        dCandidateBS = sc->distBS(cand - 1); s.linkLQ = 1;
    }
    else {
        const SensorNode *o = ctl->node(cand);
        s.candidateEnergy = o->energy() / E0;
        s.distance = sc->distNode(myId - 1, cand - 1);
        s.candidateLoad = o->loadForState();
        dCandidateBS = sc->distBS(cand - 1);
        s.linkLQ = qEst(cand);
    }
    double dCurrentBS = sc->distBS(myId - 1);
    s.progress = std::max(0.0, (dCurrentBS - dCandidateBS) / std::max(1.0, dCurrentBS));
    long att = (cand == myId) ? 0 : linkAtt[cand - 1];
    long suc = (cand == myId) ? 0 : linkSucc[cand - 1];
    s.pastReliability = (att == 0) ? 0.5 : (suc + 1.0) / (att + 2.0);
    s.d0 = sc->d0;
    s.hops = hops;
    int bins[rlhybrid::NUM_FEATURES];
    int st = rlhybrid::stateIndex(s, bins);
    ASSERT(st >= 1 && st <= rlhybrid::NUM_STATES);
    return st;
}

double SensorNode::neighborLoadMean(const std::vector<int>& cands) const
{
    // neighborLoadMean(): node candidates contribute nodeLoad+EWMA, the BS contributes 0; mean + 1
    double sum = 0;
    for (int c : cands)
        sum += (c == BS_ID) ? 0.0 : (c == myId ? loadForState() : ctl->node(c)->loadForState());
    return sum / cands.size() + 1;
}

double SensorNode::cheapestAllowedTx(const std::vector<int>& visited) const
{
    // cheapestAllowedTx(), lines 723-736: BS directly, or any live unvisited strictly-forward node
    double dcur = sc->distBS(myId - 1);
    double e = sc->txEnergy(dcur);
    for (int j = 1; j <= n; j++) {
        if (j == myId || visited[j - 1] || !ctl->node(j)->isAlive()) continue;
        if (sc->distBS(j - 1) >= dcur) continue;
        e = std::min(e, sc->txEnergy(sc->distNode(myId - 1, j - 1)));
    }
    return e;
}

std::vector<int> SensorNode::routeCandidates(int reports, const std::vector<int>& visited) const
{
    // routeCandidates(), lines 681-697 (order: BS first, then nodes 1..n)
    std::vector<int> cands;
    double dcur = sc->distBS(myId - 1);
    double eBS = sc->txEnergy(dcur);
    if (qEst(BS_ID) >= MIN_LQ && E + 1e-15 >= eBS) cands.push_back(BS_ID);
    for (int j = 1; j <= n; j++) {
        if (j == myId || visited[j - 1] || !ctl->node(j)->isAlive()) continue;
        double d = sc->distNode(myId - 1, j - 1);
        double djBS = sc->distBS(j - 1);
        if (djBS >= dcur || qEst(j) < MIN_LQ) continue;
        double eTx = sc->txEnergy(d);
        double eRx = sc->rxEnergy() + sc->Eda * sc->packetSize * reports;
        if (E + 1e-15 >= eTx && ctl->node(j)->energy() + 1e-15 >= eRx) cands.push_back(j);
    }
    return cands;
}

double& SensorNode::qref(int state, int action) { return Q[(long)(state - 1) * NUM_ACTIONS + (action - 1)]; }

double SensorNode::qval(int state, int action) const
{
    auto it = Q.find((long)(state - 1) * NUM_ACTIONS + (action - 1));
    return it == Q.end() ? 0.0 : it->second;
}

void SensorNode::qUpdate(int state, int action, double reward, double nextMax)
{
    // qUpdate(), line 717-719, followed by recordReward() (qUpdateCount)
    ASSERT(state >= 1 && state <= rlhybrid::NUM_STATES && action >= 1 && action <= NUM_ACTIONS);
    double& q = qref(state, action);
    q = q + ALPHA * (reward + GAMMA * nextMax - q);
    qUpdates++;
    ctl->counters().qUpdates++;
}

int SensorNode::selectAction(std::vector<Cand>& c, bool& explored)
{
    // selectAction(), lines 665-679: explored = rand() < epsilon; random candidate, or the best
    // candidate with ties broken by randi over the tied set (randi always draws, even for 1 tie)
    ASSERT(!c.empty());
    explored = ctl->agentRand() < ctl->currentEpsilon();
    int k;
    if (explored)
        k = ctl->agentRandi((int)c.size()) - 1;
    else {
        double mx = -std::numeric_limits<double>::infinity();
        for (auto& x : c) mx = std::max(mx, x.q);
        std::vector<int> best;
        for (int i = 0; i < (int)c.size(); i++)
            if (std::fabs(c[i].q - mx) < 1e-12) best.push_back(i);
        k = best[ctl->agentRandi((int)best.size()) - 1];
    }
    // recordAction()
    if (explored) ctl->counters().explorations++; else ctl->counters().exploitations++;
    return k;
}

// ---------------------------------------------------------------- events

void SensorNode::handleMessage(cMessage *msg)
{
    if (msg == ackTimer)
        onTimeout();
    else if (msg == processTimer)
        routeStep();
    else if (auto cmd = dynamic_cast<Command *>(msg)) {
        int c = cmd->getCommand();
        delete cmd;
        if (c == CMD_CLUSTER) clusterDecision();
        else if (c == CMD_ROUTE) startRoute();
        else throw cRuntimeError("unknown command");
    }
    else if (auto f = dynamic_cast<DataFrame *>(msg))
        onFrame(f);
    else if (auto a = dynamic_cast<LinkAck *>(msg))
        onAck(a);
    else if (auto fb = dynamic_cast<ValueFeedback *>(msg))
        onFeedback(fb);
    else
        throw cRuntimeError("unexpected message %s", msg->getName());
}

void SensorNode::sendDone() { ctl->stepDone(); }

void SensorNode::loseRecords(const std::vector<ReportRecord>& recs, int fate)
{
    for (auto& r : recs) ctl->setFate(r, (ReportFate)fate);
}

// ---- cluster phase (lines 141-257) -----------------------------------------

void SensorNode::clusterDecision()
{
    ASSERT(ownReportValid && alive);
    const int reps = 1;   // one report per station per round in this workload
    std::vector<int> cands{myId};
    for (int j = 1; j <= n; j++) {
        if (j == myId || !ctl->node(j)->isAlive()) continue;
        double d = sc->distNode(myId - 1, j - 1);
        double eTx = sc->txEnergy(d) * reps;
        double eRx = sc->rxEnergy() * reps;
        if (qEst(j) >= MIN_LQ && E >= eTx && ctl->node(j)->energy() >= eRx)
            cands.push_back(j);
    }
    double localMeanLoad = neighborLoadMean(cands);
    std::vector<Cand> c;
    for (int t : cands) { int st = stateFor(t, 0); c.push_back({t, st, qval(st, t)}); }
    bool explored;
    int k = selectAction(c, explored);
    int ch = c[k].target;
    ReportRecord rec = own;
    ownReportValid = false;

    if (ch == myId) {
        // self head: no radio operation; reward 0 (line 176)
        double ctx[6] = {1, 1, 0, 0, E, E};
        ctl->logDecision(0, myId, myId, reps, ctx, NAN, explored, c[k].state, (int)c.size(), simTime(), 0);
        qUpdate(c[k].state, ch, 0, 0);
        rec.attempted = false;
        clusterBuf.push_back(rec);
        sendDone();
        return;
    }
    double d = sc->distNode(myId - 1, ch - 1);
    double eTx = sc->txEnergy(d) * reps;
    if (E + 1e-15 < eTx) {                        // lines 182-186
        setUnavailable("insufficient_tx_energy");
        ctl->setFate(rec, FATE_UNATTEMPTED);
        sendDone();
        return;
    }
    out = Outstanding();
    out.active = true; out.type = FRAME_MEMBER; out.target = ch; out.state = c[k].state;
    double ctxv[6] = {qEst(ch), sc->priorLQ(myId - 1, ch - 1), (double)linkAtt[ch - 1], (double)linkSucc[ch - 1],
                      E, ctl->node(ch)->energy()};
    std::copy(ctxv, ctxv + 6, out.ctx);
    out.lq = ctxv[0]; out.eTx = eTx; out.d = d; out.localMeanLoad = localMeanLoad;
    out.explored = explored; out.nCands = (int)c.size(); out.decisionTime = simTime(); out.hop = 0;
    spendTx(eTx);
    ctl->counters().physicalFrames += reps;
    ctl->counters().attempts += reps;
    rec.attempted = true;
    out.reports = {rec};
    if (E == 0) setUnavailable("battery_depleted");
    linkAtt[ch - 1]++;

    auto f = new DataFrame("member report", 5);      // message kind = animation colour only (cyan)
    f->setFrameType(FRAME_MEMBER);
    f->setSenderId(myId);
    f->setClusterHead(ch);
    f->setRound(ctl->currentRound());
    f->setHops(0);
    f->setTxStart(simTime());
    f->setBitLength(sc->packetSize);
    f->appendReports(rec);
    sendDirect(f, d / cLight, sc->packetSize / Rbit, ctl->node(ch)->gate("radioIn"));
    scheduleAt(simTime() + ackTimeout, ackTimer);
}

void SensorNode::spendTx(double e)
{
    E = std::max(0.0, E - e);
    txE += e;
    txFrames++;
    ctl->counters().txE += e;
}

// ---- reception -------------------------------------------------------------

void SensorNode::onFrame(DataFrame *f)
{
    int sender = f->getSenderId();
    bool decodedOk = ctl->decoded(sender, myId);   // success_history(sender, me, r)
    ctl->noteHop(sender, myId, decodedOk);         // display only
    if (!decodedOk) {
        delete f;                                  // not decoded: no ACK, sender times out
        return;
    }
    SensorNode *snd = ctl->node(sender);
    double back = sc->distNode(myId - 1, sender - 1) / cLight;
    auto ack = new LinkAck("ack");
    ack->setReceiverId(myId);
    ack->setAtBS(false);

    if (f->getFrameType() == FRAME_MEMBER) {
        // lines 205-246
        const int reps = 1;
        double eRx = sc->rxEnergy() * reps;
        if (alive && E + 1e-15 >= eRx) {
            ctl->counters().successfulFrames += reps;
            E = std::max(0.0, E - eRx);
            rxE += eRx; rxFrames++;
            ctl->counters().rxE += eRx;
            ReportRecord r = f->getReports(0);
            r.ingressHop = true;
            r.pathDelay += (simTime() - f->getTxStart()).dbl() + tProc.dbl();
            clusterBuf.push_back(r);
            clusterMembers.push_back(sender);
            nodeLoad += reps;
            if (E == 0) {                          // lines 219-225
                setUnavailable("battery_depleted");
                std::vector<ReportRecord> stranded, keep;
                for (auto& x : clusterBuf) (x.attempted ? stranded : keep).push_back(x);
                loseRecords(stranded, FATE_LOST_ENERGY);
                clusterBuf = keep;
            }
            ack->setRxOk(true);
            ack->setReceiverDied(E == 0);
            ack->setReceiverEnergy(E);
            ack->setReceiverLoad(nodeLoad);
        }
        else {                                     // lines 232-241
            if (alive) setUnavailable("insufficient_rx_energy");
            std::vector<ReportRecord> stranded, keep;
            for (auto& x : clusterBuf) (x.attempted ? stranded : keep).push_back(x);
            loseRecords(stranded, FATE_LOST_ENERGY);
            clusterBuf = keep;
            ack->setRxOk(false);
            ack->setReceiverLoad(nodeLoad);
        }
        ack->setKind(ack->getRxOk() ? 1 : 0);   // animation colour only: green ACK, red NACK
        sendDirect(ack, back, 0, snd->gate("radioIn"));
        delete f;
        return;
    }

    // FRAME_ROUTE, lines 398-449
    int reports = f->getReportsArraySize();
    double eRx = sc->rxEnergy();
    double eAggRelay = sc->Eda * sc->packetSize * reports;
    double needed = eRx + eAggRelay;
    if (!alive || E + 1e-15 < needed) {
        if (alive) setUnavailable(E + 1e-15 < eRx ? "insufficient_rx_energy" : "insufficient_aggregation_energy");
        ack->setRxOk(false);
        ack->setKind(ack->getRxOk() ? 1 : 0);   // animation colour only: green ACK, red NACK
        sendDirect(ack, back, 0, snd->gate("radioIn"));
        delete f;
        return;
    }
    ctl->counters().successfulFrames++;
    E = E - needed;
    rxE += eRx; aggE += eAggRelay; rxFrames++;
    ctl->counters().rxE += eRx;
    ctl->counters().aggE += eAggRelay;
    nodeLoad += reports;
    if (E == 0) {                                  // lines 430-438
        setUnavailable("battery_depleted");
        ack->setRxOk(true);
        ack->setReceiverDied(true);
        ack->setReceiverEnergy(E);
        ack->setReceiverLoad(nodeLoad);
        ack->setKind(ack->getRxOk() ? 1 : 0);   // animation colour only: green ACK, red NACK
        sendDirect(ack, back, 0, snd->gate("radioIn"));
        delete f;                                  // the sender accounts the reports as lost (energy)
        return;
    }
    for (int i = 0; i < reports; i++) {
        ReportRecord r = f->getReports(i);
        r.pathDelay += (simTime() - f->getTxStart()).dbl() + tProc.dbl();
        f->setReports(i, r);
    }
    ack->setRxOk(true);
    ack->setReceiverDied(false);
    ack->setReceiverEnergy(E);
    ack->setReceiverLoad(nodeLoad);
    ack->setKind(ack->getRxOk() ? 1 : 0);   // animation colour only: green ACK, red NACK
        sendDirect(ack, back, 0, snd->gate("radioIn"));
    f->appendVisited(myId);                        // visited(curr) = true
    ASSERT(held == nullptr);
    held = f;
    heldHasPending = true;                         // the previous hop's update waits for our max Q
    heldPrev = sender;
    scheduleAt(simTime() + tProc, processTimer);   // Tproc, then this node decides the next hop
}

// ---- outcome at the sender ----------------------------------------------------

void SensorNode::onAck(LinkAck *a)
{
    ASSERT(out.active);
    cancelEvent(ackTimer);
    out.active = false;
    linkSucc[out.target - 1]++;                    // decoded: own success observation
    int hopType = out.type == FRAME_MEMBER ? 1 : (out.target == BS_ID ? 3 : 2);
    int reports = (int)out.reports.size();
    ctl->logDecision(hopType, myId, out.target, reports, out.ctx, 1, out.explored, out.state, out.nCands, out.decisionTime, out.hop);

    if (out.type == FRAME_MEMBER) {
        double eRx = sc->rxEnergy();
        if (a->getRxOk()) {                        // lines 226-231
            double progress = sc->distBS(myId - 1) - sc->distBS(out.target - 1);
            double r = rlhybrid::transitionReward(true, false, out.lq, out.eTx + eRx, a->getReceiverEnergy() / E0,
                                                  progress, sc->riverLength, a->getReceiverLoad(), out.localMeanLoad);
            qUpdate(out.state, out.target, r, 0);
        }
        else {                                     // lines 232-245
            ctl->counters().failedFrames += reports;
            loseRecords(out.reports, FATE_LOST_ENERGY);
            double r = rlhybrid::transitionReward(false, false, out.lq, out.eTx, 0, out.d, sc->riverLength,
                                                  a->getReceiverLoad(), out.localMeanLoad);
            qUpdate(out.state, out.target, r, 0);
        }
        delete a;
        sendDone();
        return;
    }

    double needed = sc->rxEnergy() + sc->Eda * sc->packetSize * reports;
    if (a->getAtBS()) {                            // lines 382-397 (delivery is counted by the BS)
        double r = rlhybrid::transitionReward(true, true, out.lq, out.eTx, 1, out.d, sc->riverLength, 0, out.localMeanLoad);
        qUpdate(out.state, out.target, r, 0);
        delete a;
        finishRoute();
    }
    else if (!a->getRxOk()) {                      // lines 403-419
        ctl->counters().failedFrames++;
        loseRecords(out.reports, FATE_LOST_ENERGY);
        double r = rlhybrid::transitionReward(false, false, out.lq, out.eTx, 0, out.d, sc->riverLength,
                                              a->getReceiverLoad(), out.localMeanLoad);
        qUpdate(out.state, out.target, r, 0);
        delete a;
        finishRoute();
    }
    else if (a->getReceiverDied()) {               // lines 430-438
        loseRecords(out.reports, FATE_LOST_ENERGY);
        double r = rlhybrid::transitionReward(false, false, out.lq, out.eTx + needed, 0, out.d, sc->riverLength,
                                              a->getReceiverLoad(), out.localMeanLoad);
        qUpdate(out.state, out.target, r, 0);
        delete a;
        finishRoute();
    }
    else {                                         // lines 440-447: successful relay -> pending update
        double progress = sc->distBS(myId - 1) - sc->distBS(out.target - 1);
        pending.active = true;
        pending.state = out.state;
        pending.action = out.target;
        pending.reward = rlhybrid::transitionReward(true, false, out.lq, out.eTx + needed, a->getReceiverEnergy() / E0,
                                                    progress, sc->riverLength, a->getReceiverLoad(), out.localMeanLoad);
        delete a;                                  // the route continues at the receiver
    }
}

void SensorNode::onTimeout()
{
    // no ACK: the frame was not decoded (success_history == false), lines 247-254 / 374-381
    ASSERT(out.active);
    out.active = false;
    int hopType = out.type == FRAME_MEMBER ? 1 : (out.target == BS_ID ? 3 : 2);
    int reports = (int)out.reports.size();
    ctl->logDecision(hopType, myId, out.target, reports, out.ctx, 0, out.explored, out.state, out.nCands, out.decisionTime, out.hop);
    ctl->counters().failedFrames += (out.type == FRAME_MEMBER) ? reports : 1;
    loseRecords(out.reports, FATE_LOST_CHANNEL);
    double r = rlhybrid::transitionReward(false, out.target == BS_ID, out.lq, out.eTx, 0, out.d, sc->riverLength,
                                          0, out.localMeanLoad);
    qUpdate(out.state, out.target, r, 0);
    if (out.type == FRAME_MEMBER) sendDone(); else finishRoute();
}

void SensorNode::onFeedback(ValueFeedback *fb)
{
    // the deferred update of lines 322-330 (bootstrap = next node's max Q) or the terminal
    // return of lines 312-316 / 456-459 (pendingReward - gamma*1 == pendingReward + gamma*(-1))
    if (!pending.active) throw cRuntimeError("value feedback without a pending update");
    qUpdate(pending.state, pending.action, pending.reward, fb->getValue());
    pending.active = false;
    delete fb;
}

void SensorNode::sendFeedback(double value, bool terminal)
{
    auto fb = new ValueFeedback(terminal ? "feedback(terminal)" : "feedback");
    fb->setValue(value);
    fb->setTerminal(terminal);
    fb->setKind(7);                                // animation colour only (grey)
    sendDirect(fb, sc->distNode(myId - 1, heldPrev - 1) / cLight, 0, ctl->node(heldPrev)->gate("radioIn"));
    heldHasPending = false;
}

void SensorNode::finishRoute() { sendDone(); }

// ---- routing phase (lines 259-462) -----------------------------------------

void SensorNode::failHeld(int fate, bool strandOwnAsUnattempted)
{
    std::vector<ReportRecord> lost, own;
    for (int i = 0; i < (int)held->getReportsArraySize(); i++) {
        const ReportRecord& r = held->getReports(i);
        (r.attempted ? lost : own).push_back(r);
    }
    loseRecords(lost, fate);
    if (strandOwnAsUnattempted) loseRecords(own, FATE_UNATTEMPTED);
    delete held;
    held = nullptr;
}

void SensorNode::startRoute()
{
    int reports = (int)clusterBuf.size();
    ASSERT(reports > 0);
    std::vector<ReportRecord> stranded, ownPending;
    for (auto& r : clusterBuf) (r.attempted ? stranded : ownPending).push_back(r);
    auto strand = [&]() {                          // stranded reports lost; own ones stay unattempted
        loseRecords(stranded, FATE_LOST_ENERGY);
        loseRecords(ownPending, FATE_UNATTEMPTED);
        clusterBuf.clear();
        sendDone();
    };
    if (!alive) { strand(); return; }              // lines 265-274
    double eAgg = sc->Eda * sc->packetSize * reports;
    if (E + 1e-15 < eAgg) { setUnavailable("insufficient_aggregation_energy"); strand(); return; }   // 276-281
    E = std::max(0.0, E - eAgg);
    aggE += eAgg;
    ctl->counters().aggE += eAgg;
    if (E == 0) { setUnavailable("battery_depleted"); strand(); return; }                            // 284-289

    held = new DataFrame("aggregate", FRAME_ROUTE);
    held->setFrameType(FRAME_ROUTE);
    held->setClusterHead(myId);
    held->setRound(ctl->currentRound());
    held->setHops(0);
    held->setBitLength(sc->packetSize);
    for (auto& r : clusterBuf) held->appendReports(r);
    held->appendVisited(myId);
    for (int m : clusterMembers) { held->appendMembers(m); held->appendVisited(m); }
    clusterBuf.clear();
    heldHasPending = false;
    routeStep();
}

void SensorNode::routeStep()
{
    ASSERT(held);
    int reports = held->getReportsArraySize();
    int hops = held->getHops();
    std::vector<int> visited(n, 0);
    for (int i = 0; i < (int)held->getVisitedArraySize(); i++) visited[held->getVisited(i) - 1] = 1;

    if (hops >= rlhybrid::MAX_HOPS) {              // lines 452-460: TTL
        if (heldHasPending) sendFeedback(-1, true);
        failHeld(FATE_LOST_TTL, true);
        finishRoute();
        return;
    }
    std::vector<int> cands = routeCandidates(reports, visited);
    if (cands.empty()) {                           // lines 298-318
        bool energyFail = (E + 1e-15 < cheapestAllowedTx(visited));
        if (energyFail) setUnavailable("insufficient_tx_energy");
        if (heldHasPending) sendFeedback(-1, true);
        failHeld(energyFail ? FATE_LOST_ENERGY : FATE_LOST_NOCANDIDATE, true);
        finishRoute();
        return;
    }
    std::vector<Cand> c;
    for (int t : cands) { int st = stateFor(t, hops); c.push_back({t, st, qval(st, t)}); }
    double localMeanLoad = neighborLoadMean(cands);
    if (heldHasPending) {                          // lines 322-330
        double mx = -std::numeric_limits<double>::infinity();
        for (auto& x : c) mx = std::max(mx, x.q);
        sendFeedback(mx, false);
    }
    bool explored;
    int k = selectAction(c, explored);
    int nexthop = c[k].target;
    // lines 332-342: safety checks (never expected to fire)
    if (nexthop != BS_ID && (visited[nexthop - 1] || !ctl->node(nexthop)->isAlive() ||
                             sc->distBS(nexthop - 1) >= sc->distBS(myId - 1)))
        throw cRuntimeError("ineligible, looping, dead or non-sinkward route action");

    double d = dist(nexthop);
    double eTx = sc->txEnergy(d);
    if (E + 1e-15 < eTx) {                         // lines 347-353
        setUnavailable("insufficient_tx_energy");
        failHeld(FATE_LOST_ENERGY, true);
        finishRoute();
        return;
    }
    out = Outstanding();
    out.active = true; out.type = FRAME_ROUTE; out.target = nexthop; out.state = c[k].state;
    double ctxv[6] = {qEst(nexthop), sc->priorLQ(myId - 1, nexthop - 1), (double)linkAtt[nexthop - 1],
                      (double)linkSucc[nexthop - 1], E, nexthop == BS_ID ? NAN : ctl->node(nexthop)->energy()};
    std::copy(ctxv, ctxv + 6, out.ctx);
    out.lq = ctxv[0]; out.eTx = eTx; out.d = d; out.localMeanLoad = localMeanLoad;
    out.explored = explored; out.nCands = (int)c.size(); out.decisionTime = simTime(); out.hop = hops + 1;
    spendTx(eTx);
    ctl->counters().physicalFrames++;
    for (int i = 0; i < reports; i++) {            // attempts += pendingOwn (own reports go on air now)
        ReportRecord r = held->getReports(i);
        if (!r.attempted) { r.attempted = true; held->setReports(i, r); ctl->counters().attempts++; }
    }
    if (E == 0) setUnavailable("battery_depleted");
    linkAtt[nexthop - 1]++;
    for (int i = 0; i < reports; i++) out.reports.push_back(held->getReports(i));

    DataFrame *f = held;
    held = nullptr;
    f->setHops(hops + 1);
    f->setSenderId(myId);
    f->setTxStart(simTime());
    cGate *g = (nexthop == BS_ID) ? (cGate *)ctl->baseStation()->gate("radioIn") : ctl->node(nexthop)->gate("radioIn");
    sendDirect(f, d / cLight, sc->packetSize / Rbit, g);
    scheduleAt(simTime() + ackTimeout, ackTimer);
}

// ---------------------------------------------------------------- display / results

void SensorNode::refreshDisplay() const
{
    // display only: one label (module name nK, plus the station name for sources) set by the
    // controller; colour encodes the role and availability; details are in the tooltip
    cDisplayString& ds = const_cast<SensorNode *>(this)->getDisplayString();
    ds.setTagArg("b", 3, !alive ? "#d62728" : (sensingRole ? "#1f6fd1" : "#a8a8a8"));
    ds.setTagArg("b", 4, !alive ? "#7a0000" : (sensingRole ? "#0b3d80" : "#6e6e6e"));
    char tt[300];
    snprintf(tt, sizeof(tt), "MATLAB node %d - %s%s\nresidual energy %.4f J%s%s", myId,
             sensingRole ? "sensing station " : "relay-only node", sensingRole ? stationName.c_str() : "", E,
             alive ? "" : "\nUNAVAILABLE: ", alive ? "" : reason.c_str());
    ds.setTagArg("tt", 0, tt);
}

void SensorNode::deliverCommand(int command, int round)
{
    // The controller's step command becomes an event at this node at the current simulation time,
    // exactly when the former zero-delay sendDirect() delivery arrived. It is not a radio frame.
    Enter_Method_Silent();
    auto cmd = new Command(command == CMD_CLUSTER ? "cluster step" : "route step");
    cmd->setCommand(command);
    cmd->setRound(round);
    scheduleAt(simTime(), cmd);
}

void SensorNode::finish()
{
    recordScalar("residualEnergy", E, "J");
    recordScalar("alive", alive ? 1 : 0);
    recordScalar("firstUnavailableRound", firstUnavailableRound);
    recordScalar("txEnergy", txE, "J");
    recordScalar("rxEnergy", rxE, "J");
    recordScalar("aggregationEnergy", aggE, "J");
    recordScalar("txFrames", txFrames);
    recordScalar("rxFrames", rxFrames);
    recordScalar("qUpdates", qUpdates);
    recordScalar("qTableNonZeroEntries", (double)Q.size());
}
