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
#include <cstdlib>
#include <cstring>
#include <limits>

Define_Module(SensorNode);

static const short KIND_TX_ATTEMPT = 1;       // ieee802154: RadioAdapter's "MAC transmission started" notice (wireless/)
static const double ALPHA = 0.10, GAMMA = 0.90, MIN_LQ = 0.50, K_PRIOR = 2;   // lines 35-36, 50-51
// BS_ID and NUM_ACTIONS are members: N+1 for an N-node network (51 for the MATLAB 50-node network)

SensorNode::~SensorNode()
{
    cancelAndDelete(ackTimer);
    cancelAndDelete(processTimer);
    delete held;
    for (auto& q : inbox) delete q.f;
}

void SensorNode::initialize(int stage)
{
    if (stage == 0) {
        myId = par("nodeId").intValue();
        cModule *c = findModuleByPath("^.controller");             // ieee802154: inside a WirelessSensor module
        ctl = check_and_cast<Controller *>(c ? c : getModuleByPath("^.^.controller"));
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
        wireless = ctl->wirelessMode();
        wirelessAckTimeout = ctl->wirelessAckTimeout();
        lastSeqFrom.assign(n + 1, 0);
    }
}

// ---------------------------------------------------------------- round hooks

void SensorNode::beginRound()
{
    nodeLoad = 0;                 // line 132: nodeLoad = zeros(1,n)
    clusterBuf.clear();           // clusterReports / clusterUnattempted
    clusterMembers.clear();
    ownReportValid = false;
    if (wireless && !alive && !radioOffSent) {     // an unavailable node switches its radio off (between rounds)
        Enter_Method_Silent();
        send(new cMessage("radioOff"), "lowerLayerOut");
        radioOffSent = true;
    }
    if (deferredTxJ > 0) { chargeRetry(deferredTxJ); deferredTxJ = 0; }   // after the round-start energy snapshot
}

void SensorNode::endRoundLoadUpdate()
{
    loadEWMA = 0.90 * loadEWMA + 0.10 * nodeLoad;   // line 476
}

bool SensorNode::applyMinimumEnergyRule()
{
    // lines 487-491: E < E_elec*k (one packet reception) -> unavailable from the next round. k = packetSize in every
    // mode (environmental WSN: 4000 bit, the validated 200 uJ threshold; frames do not change it)
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

double SensorNode::bitsOf(const ReportRecord& r) const
{
    if (wireless)                                  // application payload (+ trigger field id 1 B + value 2 B for event reports)
        return (r.payloadBits > 0 ? r.payloadBits : ctl->defaultPayloadBits()) + (ctl->eventAware() && r.eventClass > 0 ? 24 : 0);
    return ctl->reportBits(r.reportIndex);
}

double SensorNode::sumBits(const std::vector<ReportRecord>& v) const
{
    double b = wireless ? ctl->frameOverheadBits() : 0;   // ieee802154: PHY + MAC + routing header once per frame
    for (auto& r : v) b += bitsOf(r);
    return b;
}

double SensorNode::sumBits(const DataFrame *f) const
{
    double b = wireless ? ctl->frameOverheadBits() : 0;
    for (int i = 0; i < (int)f->getReportsArraySize(); i++) b += bitsOf(f->getReports(i));
    return b;
}

double SensorNode::aggEnergy(double bits, int reports) const
{
    // uniform packets keep the original expression (bit-identical results); per-report bits: E_DA x bits
    return sc->perReportBits ? sc->Eda * bits : sc->Eda * sc->packetSize * reports;
}

double SensorNode::cheapestAllowedTx(const std::vector<int>& visited, double oneBits) const
{
    // cheapestAllowedTx(), lines 723-736: BS directly, or any live unvisited strictly-forward node.
    // oneBits: MATLAB one packet (packetSize); per-report frames: the bits of the frame actually forwarded
    double dcur = sc->distBS(myId - 1);
    double e = sc->txEnergyBits(oneBits, dcur);
    for (int j = 1; j <= n; j++) {
        if (j == myId || visited[j - 1] || !ctl->node(j)->isAlive()) continue;
        if (sc->distBS(j - 1) >= dcur) continue;
        e = std::min(e, sc->txEnergyBits(oneBits, sc->distNode(myId - 1, j - 1)));
    }
    return e;
}

std::vector<int> SensorNode::routeCandidates(int reports, const std::vector<int>& visited, double frameBits) const
{
    // routeCandidates(), lines 681-697 (order: BS first, then nodes 1..n). MATLAB checks one packet (frameBits / reports);
    // per-report frames check the whole frame actually forwarded (sum of its reports' bits = the energy then charged)
    std::vector<int> cands;
    double oneBits = sc->perReportBits ? frameBits : frameBits / reports;
    double dcur = sc->distBS(myId - 1);
    double eBS = sc->txEnergyBits(oneBits, dcur);
    if (qEst(BS_ID) >= MIN_LQ && E + 1e-15 >= eBS) cands.push_back(BS_ID);
    for (int j = 1; j <= n; j++) {
        if (j == myId || visited[j - 1] || !ctl->node(j)->isAlive()) continue;
        double d = sc->distNode(myId - 1, j - 1);
        double djBS = sc->distBS(j - 1);
        if (djBS >= dcur || qEst(j) < MIN_LQ) continue;
        double eTx = sc->txEnergyBits(oneBits, d);
        double eRx = sc->rxEnergyBits(oneBits) + aggEnergy(frameBits, reports);
        if (E + 1e-15 >= eTx && ctl->node(j)->energy() + 1e-15 >= eRx) cands.push_back(j);
    }
    return cands;
}

double& SensorNode::qref(int state, int action) { return Q[(long)(state - 1) * NUM_ACTIONS + (action - 1)]; }

double SensorNode::qOrPrior(int state, int target, int reports, bool member, double localMeanLoad) const
{
    auto it = Q.find((long)(state - 1) * NUM_ACTIONS + (target - 1));
    if (it != Q.end()) return it->second;
    return sc->qPriorInit ? qPriorValue(target, reports, member, localMeanLoad) : 0.0;   // baseline: 0
}

double SensorNode::qPriorValue(int t, int reports, bool member, double localMeanLoad) const
{
    // variant B: one-step expected reward of an untried action under the geometric link prior p0, computed with the
    // unchanged reward function: p0 * r(success) + (1 - p0) * r(failure). Self-head keeps 0 (its reward is 0).
    if (t == myId) return 0.0;
    double p = sc->priorLQ(myId - 1, t - 1);
    double d = dist(t);
    double eTx = member ? sc->txEnergy(d) : sc->routeTxEnergy(d, reports);
    double rFail = rlhybrid::transitionReward(false, t == BS_ID, p, eTx, 0, d, sc->riverLength, 0, localMeanLoad);
    double rOk;
    if (t == BS_ID)
        rOk = rlhybrid::transitionReward(true, true, p, eTx, 1, d, sc->riverLength, 0, localMeanLoad);
    else {
        const SensorNode *o = ctl->node(t);
        double eRx = member ? sc->rxEnergy() : sc->routeRxEnergy(reports) + sc->Eda * sc->packetSize * reports;
        double progress = sc->distBS(myId - 1) - sc->distBS(t - 1);
        rOk = rlhybrid::transitionReward(true, false, p, eTx + eRx, o->energy() / E0, progress, sc->riverLength,
                                         o->roundLoad() + reports, localMeanLoad);
    }
    return p * rOk + (1 - p) * rFail;
}

void SensorNode::keepChosenPrior(const Cand& c)
{
    // variant B: the chosen untried action's table entry starts at its prior value, so the unchanged update
    // Q <- Q + alpha (r + gamma max Q' - Q) starts from it (baseline: entry starts at 0)
    if (sc->qPriorInit) Q.emplace((long)(c.state - 1) * NUM_ACTIONS + (c.target - 1), c.q);
}

void SensorNode::applyEnergyGuard(std::vector<int>& cands) const
{
    // variant C: drop node candidates whose residual energy is below energyGuard x the candidates' mean energy.
    // The BS and the node itself are always kept; with energyGuard <= 1 the highest-energy candidate always passes.
    if (sc->energyGuard <= 0) return;
    double sum = 0; int m = 0;
    for (int t : cands) if (t != BS_ID && t != myId) { sum += ctl->node(t)->energy(); m++; }
    if (m == 0) return;
    double thr = sc->energyGuard * sum / m;
    std::vector<int> keep;
    for (int t : cands) if (t == BS_ID || t == myId || ctl->node(t)->energy() >= thr) keep.push_back(t);
    cands.swap(keep);
}

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
        if (c == CMD_CLUSTER && wireless && busy()) pendingCluster = true;   // decide once the current frame is done
        else if (c == CMD_CLUSTER) runCluster();
        else if (c == CMD_ROUTE) startRoute();
        else throw cRuntimeError("unknown command");
    }
    else if (wireless && !dynamic_cast<DataFrame *>(msg) && msg->getArrivalGate() && msg->arrivedOn("lowerLayerIn")) {
        if (msg->getKind() == KIND_TX_ATTEMPT) { onTxAttempt(msg->getName()); delete msg; return; }
        bool mine = out.active && outName == msg->getName();   // the MAC gave up on this frame (retries / CSMA / queue)
        delete msg;
        if (mine) {
            TxLog& t = txLog[frameSeq % 8];
            if (t.seq == frameSeq && t.attempts == 0) {    // never on air (channel access failure, queue overflow):
                E += t.energy; txE -= t.energy; txFrames--; // the decision's TX charge is returned
                ctl->counters().txE -= t.energy; out.eTx -= t.energy; t.energy = 0;
            }
            cancelEvent(ackTimer);
            onTimeout();
        }
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

void SensorNode::sendDone()
{
    ctl->stepDone();
    if (wireless) popInbox();                      // the node may now be free for its next frame
}

void SensorNode::loseRecords(const std::vector<ReportRecord>& recs, int fate)
{
    for (auto& r : recs) ctl->setFate(r, (ReportFate)fate);
}

// ---- cluster phase (lines 141-257) -----------------------------------------

void SensorNode::clusterDecision()
{
    ASSERT(ownReportValid && alive);
    if (wireless && ctl->eventAware() && own.eventClass == 2) {   // critical: no cluster aggregation, routed at once
        ReportRecord rec = own;
        ownReportValid = false;
        rec.attempted = false;
        ctl->addOutstanding(1);                    // its route is one more activity of this phase
        startRouteWireless(std::vector<ReportRecord>{rec}, std::vector<int>());
        sendDone();                                // the cluster step itself is complete
        return;
    }
    const int reps = 1;   // one report per station per round in this workload
    const double b = wireless ? sumBits(std::vector<ReportRecord>{own}) : bitsOf(own);   // its frame bits
    std::vector<int> cands{myId};
    for (int j = 1; j <= n; j++) {
        if (j == myId || !ctl->node(j)->isAlive()) continue;
        double d = sc->distNode(myId - 1, j - 1);
        double eTx = sc->txEnergyBits(b, d) * reps;
        double eRx = sc->rxEnergyBits(b) * reps;
        if (qEst(j) >= MIN_LQ && E >= eTx && ctl->node(j)->energy() >= eRx)
            cands.push_back(j);
    }
    applyEnergyGuard(cands);                      // variant C (off by default)
    double localMeanLoad = neighborLoadMean(cands);
    std::vector<Cand> c;
    for (int t : cands) { int st = stateFor(t, 0); c.push_back({t, st, qOrPrior(st, t, reps, true, localMeanLoad)}); }
    bool explored;
    int k = selectAction(c, explored);
    keepChosenPrior(c[k]);                        // variant B (off by default)
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
    double eTx = sc->txEnergyBits(b, d) * reps;
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
    ctl->counters().txBits += b * reps;
    ctl->counters().txReports += reps;
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
    f->setBitLength((int64_t)b);
    f->appendReports(rec);
    if (wireless) { txWireless(f, ch); return; }
    armRetry(f, d, ctl->node(ch)->gate("radioIn"), eTx);
    sendDirect(f, d / cLight, b / Rbit, ctl->node(ch)->gate("radioIn"));
    scheduleAt(simTime() + ackTimeout, ackTimer);
}

void SensorNode::armRetry(DataFrame *f, double d, cGate *g, double eTx)
{
    if (!sc->retransmission || sc->maxRetransmissions <= 0) return;   // baseline: nothing is kept
    f->setTxSeq((int)++retrySeq);
    out.retry = f->dup();
    out.attempt = 0; out.eTxAttempt = eTx; out.gate = g;
    out.prop = d / cLight; out.dur = sc->packetSize / Rbit;
}

void SensorNode::dropRetry()
{
    if (out.retry) { delete out.retry; out.retry = nullptr; }
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
    bool decodedOk;
    if (wireless) {                                // the 802.15.4 receiver already decided; drop MAC duplicates
        if (f->getTxSeq() <= lastSeqFrom[sender]) { delete f; return; }
        lastSeqFrom[sender] = f->getTxSeq();
        decodedOk = true;
    }
    else decodedOk = ctl->decodedAttempt(sender, myId, f->getAttempt(), f->getTxSeq());   // success_history(sender, me, r) for attempt 0
    ctl->noteHop(sender, myId, decodedOk);         // display only
    if (!decodedOk) {
        delete f;                                  // not decoded: no ACK, sender times out
        return;
    }
    SensorNode *snd = ctl->node(sender);
    double back = sc->distNode(myId - 1, sender - 1) / cLight;
    auto ack = new LinkAck("ack");
    ack->setReceiverId(myId);
    ack->setTxSeq(f->getTxSeq());
    ack->setAtBS(false);

    if (f->getFrameType() == FRAME_MEMBER) {
        // lines 205-246
        const int reps = 1;
        double eRx = sc->rxEnergyBits(bitsOf(f->getReports(0))) * reps;
        if (alive && E + 1e-15 >= eRx) {
            ctl->counters().successfulFrames += reps;
            E = std::max(0.0, E - eRx);
            rxE += eRx; rxFrames++; rxReports += reps;
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
    double fb = sumBits(f);                        // packetSize * reports unless per-report frames
    double eRx = sc->routeRxEnergyBits(fb);        // V2 line 404: rx_energy(packetSize*reports) (RP); frozen: one packet
    double eAggRelay = aggEnergy(fb, reports);
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
    rxE += eRx; aggE += eAggRelay; rxFrames++; rxReports += reports;
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
    if (wireless) {                                // bootstrap value sent now; the frame waits for this node
        f->appendVisited(myId);
        ack->setHasNextValue(true);
        ack->setNextValue(valueAtReception(f));
        sendDirect(ack, back, 0, snd->gate("radioIn"));
        inbox.push_back({f, simTime(), tProc});
        popInbox();
        return;
    }
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
    if (wireless && (!out.active || a->getTxSeq() != frameSeq)) {   // answer to a frame already given up: ignore it
        staleAcks++;
        delete a;
        return;
    }
    ASSERT(out.active);
    cancelEvent(ackTimer);
    dropRetry();
    out.active = false;
    if (wireless) { macDelaySum += (simTime() - txTime).dbl(); macDelayN++; }   // queue + CSMA/CA + retries + airtime
    linkSucc[out.target - 1]++;                    // decoded: own success observation
    int hopType = out.type == FRAME_MEMBER ? 1 : (out.target == BS_ID ? 3 : 2);
    int reports = (int)out.reports.size();
    ctl->logDecision(hopType, myId, out.target, reports, out.ctx, 1, out.explored, out.state, out.nCands, out.decisionTime, out.hop);

    if (out.type == FRAME_MEMBER) {
        double eRx = sc->rxEnergyBits(bitsOf(out.reports[0]));
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

    double ob = sumBits(out.reports);
    double needed = sc->routeRxEnergyBits(ob) + aggEnergy(ob, reports);   // = eRx + eAggRelay
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
    else if (wireless) {                           // ieee802154: immediate update with the value carried by the ACK
        double progress = sc->distBS(myId - 1) - sc->distBS(out.target - 1);
        double r = rlhybrid::transitionReward(true, false, out.lq, out.eTx + needed, a->getReceiverEnergy() / E0,
                                              progress, sc->riverLength, a->getReceiverLoad(), out.localMeanLoad);
        qUpdate(out.state, out.target, r, a->getNextValue());
        delete a;
        popInbox();
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
    // ieee802154: no outcome within wirelessAckTimeout (> the longest MAC service, about 0.44 s) means the frame was lost
    // inside the receiver's MAC: INET's Ieee802154Mac records the sequence number of a frame that arrives while it starts a
    // transmission, discards it, then ACKs the retransmission as a duplicate without delivering it. A failed hop.
    if (wireless && !ackTimer->isScheduled() && simTime() - out.decisionTime >= wirelessAckTimeout) {
        lostNoOutcome++;
        EV_WARN << "frame " << outName << ": no outcome within " << wirelessAckTimeout << ", counted as a lost hop" << endl;
    }
    int hopType = out.type == FRAME_MEMBER ? 1 : (out.target == BS_ID ? 3 : 2);
    int reports = (int)out.reports.size();
    ctl->counters().failedFrames += (out.type == FRAME_MEMBER) ? reports : 1;   // this physical attempt failed
    // EXPERIMENTAL retransmission (off by default): resend the same frame to the same target, same decision.
    // Full TX energy per attempt; RX energy is charged by the receiver only on decoding (as for every frame);
    // the retry keeps the original txStart, so the hop delay includes the ACK wait and the retransmission.
    bool reserveOk = true;                         // variant A: keep energy for later forwarding (off when reserve = 0)
    if (out.retry && sc->retryEnergyReserve > 0) {
        double keep = sc->retryEnergyReserve * E0;
        reserveOk = E - out.eTxAttempt >= keep;
        if (out.target != BS_ID) {
            const SensorNode *o = ctl->node(out.target);
            double need = (out.type == FRAME_MEMBER) ? sc->rxEnergy()
                                                     : sc->routeRxEnergy(reports) + sc->Eda * sc->packetSize * reports;
            reserveOk = reserveOk && o->isAlive() && o->energy() - need >= keep;
        }
    }
    if (out.retry && reserveOk && out.attempt < sc->maxRetransmissions && alive && E + 1e-15 >= out.eTxAttempt) {
        out.attempt++;
        spendTx(out.eTxAttempt);
        retryE += out.eTxAttempt;
        out.eTx += out.eTxAttempt;                     // energy actually spent on this action (used by the reward)
        ctl->counters().physicalFrames += (out.type == FRAME_MEMBER) ? reports : 1;
        ctl->counters().txBits += sumBits(out.reports);
        ctl->counters().txReports += reports;
        linkAtt[out.target - 1]++;                     // every attempt is a link observation
        ctl->noteRetransmission();
        if (E == 0) setUnavailable("battery_depleted");
        DataFrame *f = out.retry->dup();
        f->setAttempt(out.attempt);
        sendDirect(f, out.prop, out.dur, out.gate);
        scheduleAt(simTime() + ackTimeout, ackTimer);
        return;
    }
    dropRetry();
    out.active = false;
    ctl->logDecision(hopType, myId, out.target, reports, out.ctx, 0, out.explored, out.state, out.nCands, out.decisionTime, out.hop);
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
    if (wireless) {                                // frames that fit the 802.15.4 MAC payload, queued at this node
        std::vector<ReportRecord> recs = clusterBuf;
        clusterBuf.clear();
        startRouteWireless(recs, clusterMembers);
        return;
    }
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
    double eAgg = aggEnergy(sumBits(clusterBuf), reports);
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
    if (sc->perReportBits) held->setBitLength((int64_t)sumBits(held));   // display: the frame's real length
    held->appendVisited(myId);
    for (int m : clusterMembers) { held->appendMembers(m); held->appendVisited(m); }
    clusterBuf.clear();
    heldHasPending = false;
    routeStep();
}

void SensorNode::routeStep()
{
    ASSERT(held);
    if (wireless) {                                // time the frame waited for this node (relay or cluster-head queue)
        double wait = (simTime() - heldArrival - heldProc).dbl();
        if (wait > 1e-12)
            for (int i = 0; i < (int)held->getReportsArraySize(); i++) {
                ReportRecord r = held->getReports(i);
                r.pathDelay += wait;
                r.queueDelay += wait;
                held->setReports(i, r);
            }
    }
    int reports = held->getReportsArraySize();
    double fb = sumBits(held);                     // packetSize * reports unless per-report frames
    int hops = held->getHops();
    std::vector<int> visited(n, 0);
    for (int i = 0; i < (int)held->getVisitedArraySize(); i++) visited[held->getVisited(i) - 1] = 1;

    if (hops >= rlhybrid::MAX_HOPS) {              // lines 452-460: TTL
        if (heldHasPending) sendFeedback(-1, true);
        failHeld(FATE_LOST_TTL, true);
        finishRoute();
        return;
    }
    std::vector<int> cands = routeCandidates(reports, visited, fb);
    if (cands.empty()) {                           // lines 298-318
        bool energyFail = (E + 1e-15 < cheapestAllowedTx(visited, sc->perReportBits ? fb : fb / reports));
        if (energyFail) setUnavailable("insufficient_tx_energy");
        if (heldHasPending) sendFeedback(-1, true);
        failHeld(energyFail ? FATE_LOST_ENERGY : FATE_LOST_NOCANDIDATE, true);
        finishRoute();
        return;
    }
    applyEnergyGuard(cands);                      // variant C (off by default)
    double localMeanLoad = neighborLoadMean(cands);
    std::vector<Cand> c;
    for (int t : cands) { int st = stateFor(t, hops); c.push_back({t, st, qOrPrior(st, t, reports, false, localMeanLoad)}); }
    if (heldHasPending) {                          // lines 322-330
        double mx = -std::numeric_limits<double>::infinity();
        for (auto& x : c) mx = std::max(mx, x.q);
        sendFeedback(mx, false);
    }
    bool explored;
    int k = selectAction(c, explored);
    keepChosenPrior(c[k]);                        // variant B (off by default)
    int nexthop = c[k].target;
    // lines 332-342: safety checks (never expected to fire)
    if (nexthop != BS_ID && (visited[nexthop - 1] || !ctl->node(nexthop)->isAlive() ||
                             sc->distBS(nexthop - 1) >= sc->distBS(myId - 1)))
        throw cRuntimeError("ineligible, looping, dead or non-sinkward route action");

    double d = dist(nexthop);
    double eTx = sc->routeTxEnergyBits(d, fb);    // V2 line 350: tx_energy(packetSize*reports, d) (RP); frozen: one packet
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
    ctl->counters().txBits += fb;
    ctl->counters().txReports += reports;
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
    f->setAttempt(0);                              // first transmission of THIS hop (a forwarded frame may carry 1)
    if (wireless) { txWireless(f, nexthop); return; }
    armRetry(f, d, g, eTx);
    if (!sc->perReportBits) {
        sendDirect(f, d / cLight, fb / reports / Rbit, g);   // one-packet time (MATLAB k/Rbit)
        scheduleAt(simTime() + ackTimeout, ackTimer);
        return;
    }
    double dur = fb / Rbit;                        // per-report frames: the whole frame is on air
    sendDirect(f, d / cLight, dur, g);
    scheduleAt(simTime() + dur + ackTimeout, ackTimer);   // ackTimeout counts from the frame's end (frames > 20 ms exist)
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

void SensorNode::deliverCommand(int command, int round, simtime_t delay)
{
    // The controller's step command becomes an event at this node at the current simulation time,
    // exactly when the former zero-delay sendDirect() delivery arrived. It is not a radio frame.
    Enter_Method_Silent();
    auto cmd = new Command(command == CMD_CLUSTER ? "cluster step" : "route step");
    cmd->setCommand(command);
    cmd->setRound(round);
    scheduleAt(simTime() + delay, cmd);
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
    recordScalar("reportsReceivedFromOthers", rxReports);
    if (sc->retransmission || wireless) recordScalar("retryEnergy", retryE, "J");   // ieee802154: MAC retries
    if (wireless) {
        recordScalar("macHopDelayMean", macDelayN ? macDelaySum / macDelayN : NAN, "s");
        recordScalar("macHopsDelivered", macDelayN);
        recordScalar("inboxMax", (double)inboxMax);
        recordScalar("framesLostNoOutcome", lostNoOutcome);   // frames lost inside a receiver MAC (see onTimeout)
        recordScalar("staleLinkAcks", staleAcks);
    }
}

// ---------------------------------------------------------------- communicationModel = "ieee802154"

void SensorNode::runCluster()
{
    if (wireless && (!alive || !ownReportValid)) {  // the node died while its decision waited
        if (ownReportValid) { ctl->setFate(own, FATE_UNATTEMPTED); ownReportValid = false; }
        sendDone();
        return;
    }
    clusterDecision();
}

void SensorNode::txWireless(DataFrame *f, int target)
{
    // The frame goes down to the radio adapter (wireless/RadioAdapter), which hands it to INET's 802.15.4 MAC addressed to
    // `target`. The outcome comes back as a LinkAck (the receiver accepted the frame) or a MAC failure notice.
    f->setTxSeq((int)++frameSeq);
    char name[48];
    snprintf(name, sizeof(name), "rl:%d:%ld", myId, frameSeq);
    f->setName(name);
    outName = name;
    txLog[frameSeq % 8] = {frameSeq, 0, out.eTx};          // the decision charged one transmission of out.eTx
    double payload = 0;
    for (int i = 0; i < (int)f->getReportsArraySize(); i++) payload += bitsOf(f->getReports(i));
    f->setBitLength((int64_t)(8 * ctl->routingHeaderBytes() + payload));   // INET adds MAC (9 B) and PHY (6 B) itself
    if (f->getBitLength() > 8 * ctl->macPayloadLimitBytes())
        throw cRuntimeError("frame %s (%ld bit) exceeds the 802.15.4 MAC payload", name, (long)f->getBitLength());
    f->setKind(target);                                    // the adapter reads the next hop (node id, N+1 = BS) from the kind
    txTime = simTime();
    send(f, "lowerLayerOut");
    scheduleAt(simTime() + wirelessAckTimeout, ackTimer);  // safety net; the MAC outcome normally arrives first
}

void SensorNode::onTxAttempt(const char *name)
{
    // ieee802154: one first-order TX charge per MAC transmission actually started. The decision charged the first; each
    // MAC retry (no MAC ACK, also after a lost MAC ACK of a delivered frame) is charged here, or at the next round start
    // when it falls between rounds (that round's energy balance is closed). Dead nodes are not charged.
    long seq = std::atol(std::strrchr(name, ':') + 1);
    TxLog& t = txLog[seq % 8];
    if (t.seq != seq || ++t.attempts == 1 || !alive) return;
    if (!ctl->roundActive()) { deferredTxJ += t.energy; return; }
    double e = chargeRetry(t.energy);
    if (out.active && outName == name) out.eTx += e;     // energy spent on this action (transition reward)
}

double SensorNode::chargeRetry(double e)
{
    e = std::min(E, e);                                  // a retry the battery cannot cover empties it
    spendTx(e);
    retryE += e;
    if (E == 0 && alive) setUnavailable("battery_depleted");
    return e;
}

void SensorNode::popInbox()
{
    // One transmission at a time per node. A deferred cluster decision goes first; waiting frames leave in arrival order,
    // or, with eventAware, by event class aged by waiting time (+1 level per ageingInterval, so routine frames cannot starve).
    inboxMax = std::max(inboxMax, inbox.size());
    if (!wireless || busy() || processTimer->isScheduled()) return;
    if (pendingCluster) { pendingCluster = false; runCluster(); return; }
    if (inbox.empty()) return;
    size_t k = 0;
    if (ctl->eventAware()) {
        double best = -1;
        for (size_t i = 0; i < inbox.size(); i++) {
            int cls = 0;
            for (int j = 0; j < (int)inbox[i].f->getReportsArraySize(); j++) cls = std::max(cls, inbox[i].f->getReports(j).eventClass);
            double p = cls + std::floor((simTime() - inbox[i].arrival).dbl() / ctl->ageingInterval());
            if (p > best + 1e-12) { best = p; k = i; }     // ties: earliest arrival
        }
    }
    held = inbox[k].f;
    heldArrival = inbox[k].arrival;
    heldProc = inbox[k].proc;
    inbox.erase(inbox.begin() + k);
    heldHasPending = false;
    scheduleAt(std::max(simTime(), heldArrival + heldProc), processTimer);
}

double SensorNode::valueAtReception(const DataFrame *f) const
{
    // the value routeStep would bootstrap from (lines 298-330): -1 when the route ends here (TTL or no candidate),
    // otherwise max Q over the candidates after the energy guard
    int hops = f->getHops();
    if (hops >= rlhybrid::MAX_HOPS) return -1;
    std::vector<int> visited(n, 0);
    for (int i = 0; i < (int)f->getVisitedArraySize(); i++) visited[f->getVisited(i) - 1] = 1;
    int reports = f->getReportsArraySize();
    std::vector<int> cands = routeCandidates(reports, visited, sumBits(f));
    if (cands.empty()) return -1;
    applyEnergyGuard(cands);
    double localMeanLoad = neighborLoadMean(cands);
    double mx = -std::numeric_limits<double>::infinity();
    for (int t : cands) mx = std::max(mx, qOrPrior(stateFor(t, hops), t, reports, false, localMeanLoad));
    return mx;
}

DataFrame *SensorNode::newRouteFrame(const std::vector<ReportRecord>& recs, const std::vector<int>& members)
{
    auto f = new DataFrame("aggregate", FRAME_ROUTE);
    f->setFrameType(FRAME_ROUTE);
    f->setClusterHead(myId);
    f->setRound(ctl->currentRound());
    f->setHops(0);
    for (auto& r : recs) f->appendReports(r);
    f->appendVisited(myId);
    for (int m : members) { f->appendMembers(m); f->appendVisited(m); }
    return f;
}

void SensorNode::startRouteWireless(const std::vector<ReportRecord>& recs, const std::vector<int>& members)
{
    // lines 265-289 (aggregation energy and death checks) for these reports, then frames no larger than the 802.15.4 MAC
    // payload: routing header + report payloads (eventAware: critical, then warning reports first)
    std::vector<ReportRecord> stranded, ownPending;
    for (auto& r : recs) (r.attempted ? stranded : ownPending).push_back(r);
    auto strand = [&]() {
        loseRecords(stranded, FATE_LOST_ENERGY);
        loseRecords(ownPending, FATE_UNATTEMPTED);
        sendDone();
    };
    if (recs.empty()) { sendDone(); return; }
    if (!alive) { strand(); return; }
    double eAgg = aggEnergy(sumBits(recs), (int)recs.size());
    if (E + 1e-15 < eAgg) { setUnavailable("insufficient_aggregation_energy"); strand(); return; }
    E = std::max(0.0, E - eAgg);
    aggE += eAgg;
    ctl->counters().aggE += eAgg;
    if (E == 0) { setUnavailable("battery_depleted"); strand(); return; }
    std::vector<ReportRecord> order = recs;
    if (ctl->eventAware())
        std::stable_sort(order.begin(), order.end(), [](const ReportRecord& a, const ReportRecord& b) { return a.eventClass > b.eventClass; });
    const double limit = 8.0 * ctl->macPayloadLimitBytes(), hdr = 8.0 * ctl->routingHeaderBytes();
    std::vector<std::vector<ReportRecord>> bundles;
    double used = limit + 1;                       // the first report opens the first frame
    for (auto& r : order) {
        double b = bitsOf(r);
        if (hdr + b > limit) throw cRuntimeError("a %g-bit report exceeds the 802.15.4 MAC payload", b);
        if (used + b > limit) { bundles.emplace_back(); used = hdr; }
        bundles.back().push_back(r);
        used += b;
    }
    ctl->addOutstanding((int)bundles.size() - 1);  // this step was counted once; every frame ends on its own
    for (auto& b : bundles) inbox.push_back({newRouteFrame(b, members), simTime(), SIMTIME_ZERO});
    popInbox();
}
