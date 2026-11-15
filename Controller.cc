#include "Controller.h"
#include "BaseStation.h"
#include "SensorNode.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>

Define_Module(Controller);

static const char *FATE_NAMES[] = {"none", "delivered", "lost_channel", "lost_energy", "lost_no_candidate",
                                   "lost_ttl", "unattempted", "source_unavailable"};

static std::string num(double v)
{
    if (std::isnan(v)) return "NaN";
    std::ostringstream os;
    os << std::setprecision(17) << v;
    return os.str();
}

static void openOut(std::ofstream& f, const std::string& path, const char *header)
{
    std::filesystem::path p(path);
    if (p.has_parent_path()) std::filesystem::create_directories(p.parent_path());
    f.open(path);
    if (!f) throw cRuntimeError("cannot write %s", path.c_str());
    if (header) f << header << "\n";
}

Controller::~Controller()
{
    cancelAndDelete(roundTimer);
    cancelAndDelete(nextStepTimer);
}

void Controller::initialize(int stage)
{
    if (stage != 0) return;
    int seed = par("scenarioSeed").intValue();
    numRounds = par("numRounds").intValue();
    roundPeriod = par("roundPeriod");
    guard = par("stepGuard");
    prefix = par("outputPrefix").stdstringValue();
    epsilon = par("epsilonInitial").doubleValue();
    epsilonMinimum = par("epsilonMinimum").doubleValue();
    epsilonDecay = par("epsilonDecayPerRound").doubleValue();

    // network size from the NED network parameter numNodes (50 = the MATLAB experiment)
    int totalNodes = getParentModule()->par("numNodes").intValue();
    int extraSeed = par("extraTopologySeed").intValue();
    if (extraSeed < 0) extraSeed = 900000 + seed;          // dedicated stream for the added relays' coordinates
    int topoSeed = par("topologySeed").intValue();          // -1: nodes 1..50 from rng(seed) exactly as MATLAB
    std::string chMode = par("channelStream").stdstringValue();
    if (chMode != "matlab" && chMode != "independent") throw cRuntimeError("channelStream must be \"matlab\" or \"independent\"");
    diagnostics = par("exportDiagnostics").boolValue();
    std::string cm = par("communicationModel").stdstringValue();
    if (cm != "abstract" && cm != "ieee802154") throw cRuntimeError("communicationModel must be \"abstract\" or \"ieee802154\"");
    wireless = cm == "ieee802154";
    eventAwareOn = par("eventAware").boolValue();
    if (eventAwareOn && !wireless) throw cRuntimeError("eventAware needs communicationModel = \"ieee802154\" (queues exist only there)");
    extendedReports = wireless;
    wirelessAckTO = par("wirelessAckTimeout");
    clusterJitter = par("clusterJitter");
    routeJitter = par("routeJitter");
    routingHeaderB = par("routingHeaderBytes").intValue();
    macPayloadLimitB = par("macPayloadLimitBytes").intValue();
    frameOverheadB = 8.0 * (par("phyOverheadBytes").intValue() + par("macOverheadBytes").intValue() + routingHeaderB);
    defaultPayloadB = par("defaultPayloadBits").intValue();
    ageingS = par("ageingInterval").doubleValue();
    roundStartSignal = registerSignal("rlRoundStart");
    roundEndSignal = registerSignal("rlRoundEnd");
    // scenario geometry / radio constants (defaults = generate_scenario.m)
    sc.riverLength = par("areaLength").doubleValue();
    sc.riverWidth = par("areaWidth").doubleValue();
    sc.bsX = par("bsX").doubleValue();
    sc.bsY = par("bsY").doubleValue();
    sc.packetSize = par("packetSize").intValue();
    sc.initialEnergy = par("initialEnergy").doubleValue();
    sc.numRounds = par("workloadRounds").intValue();
    sc.topologyMode = par("topologyMode").stdstringValue();
    try { sc.stationNodeIds = parseIntList(par("stationNodeIds").stdstringValue()); }
    catch (std::exception& e) { throw cRuntimeError("%s", e.what()); }
    sc.reportPreservingEnergy = par("reportPreservingEnergy").boolValue();
    sc.retransmission = par("enableRetransmission").boolValue();
    sc.maxRetransmissions = sc.retransmission ? (int)par("maxRetransmissions").intValue() : 0;
    sc.retryEnergyReserve = par("retryEnergyReserve").doubleValue();
    sc.qPriorInit = par("qPriorInit").boolValue();
    sc.energyGuard = par("energyGuard").doubleValue();
    if (sc.energyGuard < 0 || sc.energyGuard > 1) throw cRuntimeError("energyGuard must lie in [0, 1]");
    if (sc.maxRetransmissions < 0) throw cRuntimeError("maxRetransmissions must be >= 0");
    try { sc.generate(seed, totalNodes, (uint32_t)extraSeed, topoSeed, chMode == "independent"); }   // generate_scenario.m (+ extra sensing nodes beyond the base layout)
    catch (std::exception& e) { throw cRuntimeError("%s", e.what()); }
    try {                                               // loader + workload builder (defaults = the Periyar workload)
        WorkloadConfig wc;
        wc.mode = par("workloadMode").stdstringValue();
        wc.datasetPath = par("datasetPath").stdstringValue();
        wc.timeColumn = par("datasetTimeColumn").stdstringValue();
        wc.stationColumn = par("datasetStationColumn").stdstringValue();
        wc.datasetFields = parseDatasetFields(par("datasetFields").stdstringValue());
        wc.stationMap = parseStationMap(par("stationMap").stdstringValue());
        wc.invalidRowPolicy = par("invalidRowPolicy").stdstringValue();
        wc.holdPolicy = par("holdPolicy").stdstringValue();
        wc.expectedRawRows = par("expectedRawRows").intValue();
        wc.expectedValidRows = par("expectedValidRows").intValue();
        wc.expectedUniqueTimes = par("expectedUniqueTimes").intValue();
        std::string synth = par("syntheticSources").stdstringValue();
        if (synth == "others") {                         // every node that is not a dataset station
            std::set<int> st;
            for (auto& sm : wc.stationMap) st.insert(sm.second);
            for (int i = 1; i <= sc.numNodes; i++) if (!st.count(i)) wc.syntheticSources.push_back(i);
        }
        else
            wc.syntheticSources = parseIntList(synth);
        if (par("replaySources").stdstringValue() == "others") {   // node k replays station ((k-1) mod S) + 1
            std::set<int> st;
            for (auto& sm : wc.stationMap) st.insert(sm.second);
            const int S = (int)wc.stationMap.size();
            if (S == 0) throw cRuntimeError("replaySources needs a stationMap");
            for (int i = 1; i <= sc.numNodes; i++)
                if (!st.count(i)) wc.replay.push_back({i, (i - 1) % S});
        }
        else if (!par("replaySources").stdstringValue().empty())
            throw cRuntimeError("replaySources must be \"\" or \"others\"");
        wc.syntheticFields = parseSyntheticFields(par("syntheticFields").stdstringValue());
        wc.syntheticSeed = (uint32_t)par("syntheticSeed").intValue();
        wc.syntheticPeriodRounds = par("syntheticPeriodRounds").intValue();
        wc.reportInterval = par("reportInterval").intValue();
        wc.scheduleRounds = par("scheduleRounds").intValue();
        std::string scenarioDataset = par("scenarioDataset").stdstringValue();
        if (!scenarioDataset.empty() && (scenarioDataset.size() < 4 || scenarioDataset.substr(scenarioDataset.size() - 4) != ".csv")) {
            // a dataset folder (data/scenarios/<profile>_<N>): its mixed node map if it has one, else its observations file
            std::string dir = scenarioDataset + "/";
            scenarioDataset = std::ifstream(dir + "node_map.csv").good() ? dir + "node_map.csv" : dir + "observations.csv";
        }
        if (scenarioDataset.empty())
            wl.build(wc, sc.numRounds, sc.numNodes);
        else                                            // scenario study (data/scenarios): the loader settings above are unused
            wl.buildScenario(scenarioDataset, par("scenarioMode").stdstringValue(), sc.numRounds, sc.numNodes,
                             par("scenarioFrameBits").stdstringValue());
        sc.perReportBits = !par("scenarioFrameBits").stdstringValue().empty();
        if (sc.perReportBits && (scenarioDataset.empty() || !sc.reportPreservingEnergy || sc.retransmission || sc.qPriorInit))
            throw cRuntimeError("scenarioFrameBits needs scenarioDataset and reportPreservingEnergy, without retransmission or qPriorInit");
    }
    catch (std::exception& e) { throw cRuntimeError("%s", e.what()); }
    std::string placement = par("placement").stdstringValue();
    if (placement == "scenario") {                      // synthetic profile-specific layout (stream 950000 + seed)
        if ((int)wl.nodeProfile.size() != sc.numNodes) throw cRuntimeError("placement \"scenario\" needs a scenarioDataset");
        try { sc.placeByProfile(wl.nodeProfile, (uint32_t)(950000 + seed)); }
        catch (std::exception& e) { throw cRuntimeError("%s", e.what()); }
    }
    else if (placement != "common") throw cRuntimeError("placement must be \"common\" or \"scenario\"");
    agentRng.seed((uint32_t)seed);                      // RL_Hybrid.m line 28: rng(seed,'twister')

    // nodes are looked up by their nodeId parameter (MATLAB id), the BS by type
    cModule *net = getParentModule();
    nodes.assign(sc.numNodes, nullptr);
    auto consider = [&](cModule *m) {
        if (auto nd = dynamic_cast<SensorNode *>(m)) {
            int id = nd->par("nodeId").intValue();
            if (id < 1 || id > sc.numNodes || nodes[id - 1]) throw cRuntimeError("bad or duplicate nodeId %d", id);
            nodes[id - 1] = nd;
            return true;
        }
        if (auto b = dynamic_cast<BaseStation *>(m)) {
            if (bs) throw cRuntimeError("more than one base station");
            bs = b;
            return true;
        }
        return false;
    };
    for (cModule::SubmoduleIterator it(net); !it.end(); ++it)
        if (!consider(*it))                          // ieee802154: logic modules inside WirelessSensor / WirelessBaseStation
            for (cModule::SubmoduleIterator jt(*it); !jt.end(); ++jt) consider(*jt);
    for (int i = 0; i < sc.numNodes; i++)
        if (!nodes[i]) throw cRuntimeError("node with nodeId %d missing", i + 1);
    if (!bs) throw cRuntimeError("base station missing");
    if (wireless) {     // INET position = the topology above: the host's "p" tag, which INET's StationaryMobility reads as
                        // a double in INITSTAGE_SINGLE_MOBILITY (its initialX/Y are not mutable); z = initialZ = 0
        auto place = [&](cModule *logic, double x, double y) {
            cModule *host = logic->getParentModule();
            if (!host->getSubmodule("mobility")) throw cRuntimeError("communicationModel ieee802154 needs the network PeriyarWirelessNetwork");
            char b[32];
            snprintf(b, sizeof(b), "%.17g", x); host->getDisplayString().setTagArg("p", 0, b);
            snprintf(b, sizeof(b), "%.17g", y); host->getDisplayString().setTagArg("p", 1, b);
        };
        for (int i = 0; i < sc.numNodes; i++) place(nodes[i], sc.X[i], sc.Y[i]);
        place(bs, sc.bsX, sc.bsY);
        std::string lp = par("wirelessLinkPrior").stdstringValue();
        if (lp != "linkBudget" && lp != "matlabDistance") throw cRuntimeError("wirelessLinkPrior must be \"linkBudget\" or \"matlabDistance\"");
        if (lp == "linkBudget") setLinkBudgetPrior(nodes[0]->getParentModule());
        if (!par("eventAnnotations").stdstringValue().empty()) loadEvents(par("eventAnnotations").stdstringValue());
    }
    setupDisplay();
    fate.assign(wl.reports.size(), FATE_NONE);
    sensingOpJ.assign(sc.numNodes, 0.0); sensingAllJ.assign(sc.numNodes, 0.0); sensingOpRounds.assign(sc.numNodes, 0);
    fateRound.assign(wl.reports.size(), 0);

    if (par("exportDecisionLog").boolValue())          // one line per decision (large for big networks)
        openOut(decisionLog, prefix + "-decisions.csv",
                "round,hopType,actor,target,reports,qHat,prior,attemptsBefore,successesBefore,actorE,targetE,outcome,"
                "explored,state,numCandidates,logTime,decisionTime,hop");
    openOut(perRoundLog, prefix + "-per_round.csv",
            "round,delivered,aliveCount,residualJ,qUpdates,explorations,epsilon,scheduled,workloadAvailable,"
            "sourceAvailable,attempts,unattempted,stageLoss,lossNoCandidate,lossChannel,lossEnergy,lossTTL,"
            "physicalFrames,txJ,rxJ,aggJ,roundEndTime");
    openOut(reportLog, prefix + "-reports.csv", extendedReports
            ? "reportIndex,round,sourceNode,station,date,fate,resolvedRound,hops,pathDelayS,latencyS,queueDelayS,eventClass,triggerField,triggerValue,deadlineS"
            : "reportIndex,round,sourceNode,station,date,fate,resolvedRound,hops,pathDelayS");
    openOut(unavailLog, prefix + "-unavailability_events.csv", "round,simTime,node,reason,energyJ");

    if (par("exportReference").boolValue())
        exportReferenceData();
    if (par("exportDeliveredPayload").boolValue()) {
        std::string h = "reportIndex,sourceNode,station,date";
        for (auto& fd : wl.fields) h += "," + fd.name;
        openOut(deliveredPayloadLog, prefix + "-delivered_payload.csv", h.c_str());
    }
    if (diagnostics) {
        openOut(diagLog, prefix + "-hops.csv",
                "round,hopType,actor,target,hop,reports,numCandidates,explored,outcome,trueLQ,qHat,prior,distanceM,"
                "actorAdded,targetAdded");
        std::ofstream d(prefix + "-design.txt");
        d << "runSeed " << sc.seed << "\ntopologySeed " << sc.topologySeed << "\nextraTopologySeed " << sc.extraTopologySeed
          << "\nnumNodes " << sc.numNodes << "\nchannelStream " << chMode << "\nagentStreamSeed " << seed
          << "\nchannelSeedRound1 " << sc.channelSeed(1) << "\n";
    }
    roundTimer = new cMessage("roundStart");
    nextStepTimer = new cMessage("nextStep");
    if (numRounds > 0)
        scheduleAt(SIMTIME_ZERO, roundTimer);
    EV_INFO << "Periyar validation: seed " << seed << ", " << sc.numNodes << " nodes, BS (" << sc.bsX << "," << sc.bsY
            << "), workload " << wl.totalScheduled << " slots / " << wl.totalAvailable << " with data\n";
}

void Controller::exportReferenceData()
{
    // Stage B / scenario evidence: the same files and formats as matlab_reference/scripts/export_reference.m
    std::ofstream f;
    std::string hdr = "reportIndex,round,sourceNode,station,date";
    for (auto& fd : wl.fields) hdr += "," + fd.name;
    if (sc.perReportBits) hdr += ",frameBits";
    openOut(f, prefix + "-workload.csv", hdr.c_str());
    for (auto& r : wl.reports) {
        f << r.index << "," << r.round << "," << r.sourceNode << "," << r.station << "," << r.date;
        for (double v : r.values) f << "," << num(v);
        if (sc.perReportBits) f << "," << r.bits;
        f << "\n";
    }
    f.close();
    openOut(f, prefix + "-payload_fields.csv", "name,unit,origin,datasetColumn");
    for (auto& fd : wl.fields) f << fd.name << "," << fd.unit << "," << fd.origin << "," << fd.column << "\n";
    f.close();
    openOut(f, prefix + "-workload_summary.txt", nullptr);
    f << "raw " << wl.rawObservations << " valid " << wl.validObservations << " dates " << wl.uniqueDates
      << " scheduled " << wl.totalScheduled << " available " << wl.totalAvailable << " unavailable "
      << wl.totalUnavailable << "\nr_events ";
    for (int r : wl.rEvents) f << r << " ";
    f << "\nstations ";
    for (size_t i = 0; i < wl.stationNames.size(); i++) f << (i ? "|" : "") << wl.stationNames[i];
    f << "\nnodes ";
    for (int nd : wl.sensingNodes) f << nd << " ";
    f << "\n";
    f.close();
    openOut(f, prefix + "-nodes.csv", "node,x,y");
    for (int i = 0; i < sc.numNodes; i++) f << i + 1 << "," << num(sc.X[i]) << "," << num(sc.Y[i]) << "\n";
    f.close();
    if (par("exportChannel").boolValue()) {
        std::ofstream b(prefix + "-success.bin", std::ios::binary);
        std::vector<unsigned char> s;
        for (int r = 1; r <= sc.numRounds; r++) {
            sc.channelForRound(r, s);
            b.write((const char *)s.data(), s.size());
        }
    }
}

bool Controller::decoded(int i, int j) const
{
    // MATLAB block (nodes 1..matlabBlock and the BS): bit-exact success_history(i,j,r)
    const int n0 = sc.matlabBlock;
    if (i <= n0 && (j <= n0 || j == sc.numNodes + 1)) {
        int jb = (j == sc.numNodes + 1) ? n0 + 1 : j;
        return success[(i - 1) + (jb - 1) * n0] != 0;
    }
    return sc.extraLinkSuccess(round, i, j);              // link involving a node beyond the MATLAB block (hash channel)
}

bool Controller::decodedAttempt(int i, int j, int attempt, int txSeq) const
{
    if (attempt == 0)
        return decoded(i, j);                       // the validated MATLAB channel outcome
    // EXPERIMENTAL retransmission: independent uniform from a counter hash of (seed, round, i, j, attempt),
    // compared with this round's true link quality lq(i, j) - the same clipped distance law, no free success
    uint64_t h = 0x9E3779B97F4A7C15ULL ^ ((uint64_t)(uint32_t)sc.seed << 1);
    // txSeq = the sender's own frame counter: two frames on the same link in one round get independent retries
    for (uint64_t v : {(uint64_t)round, (uint64_t)i, (uint64_t)j, (uint64_t)attempt, (uint64_t)txSeq}) {
        h ^= v + 0x9E3779B97F4A7C15ULL + (h << 6) + (h >> 2);
        h += 0x9E3779B97F4A7C15ULL; h = (h ^ (h >> 30)) * 0xBF58476D1CE4E5B9ULL;
        h = (h ^ (h >> 27)) * 0x94D049BB133111EBULL; h ^= h >> 31;
    }
    double u = (h >> 11) * (1.0 / 9007199254740992.0);
    double lq = trueLQ(i, j);
    bool ok = u < lq;
    if (ok) retransmissionsDecoded++;
    retransmissionsExpected += lq; retransmissionsVariance += lq * (1 - lq);   // statistical check of the draw
    return ok;
}

void Controller::handleMessage(cMessage *msg)
{
    if (msg == roundTimer) startRound();
    else if (msg == nextStepTimer) dispatchNext();
    else throw cRuntimeError("unexpected message");
}

void Controller::stepDone()
{
    Enter_Method_Silent();
    if (wireless) {                                 // ieee802154: the phase ends when its last activity ends
        if (--outstanding < 0) throw cRuntimeError("activity accounting below zero");
        if (outstanding == 0) scheduleAt(simTime() + guard, nextStepTimer);
        return;
    }
    // a small guard lets in-flight value feedback reach its node before the next decision
    scheduleAt(simTime() + guard, nextStepTimer);
}

// ---------------------------------------------------------------- round structure

void Controller::startRound()
{
    round++;
    emit(roundStartSignal, (long)round);            // ieee802154: radio adapters split active-window and idle-gap energy
    recentHops.clear();                              // display only
    rc = RoundCounters();
    rc.epsilon = epsilon;
    sc.channelForRound(round, success, (diagnostics || sc.retransmission) ? &lqRound : nullptr);   // success_history(:,:,round)
    energyStartOfRound = 0;
    for (auto nd : nodes) { energyStartOfRound += nd->energy(); nd->beginRound(); }
    if (!wl.sensingmJ.empty())                       // scenario study: sensing ledger, NEVER charged to the radio battery
        for (int i = 0; i < sc.numNodes; i++) {
            double e = wl.sensingmJ[(size_t)i * sc.numRounds + (round - 1)] / 1000.0;
            sensingAllJ[i] += e;
            if (nodes[i]->isAlive()) { sensingOpJ[i] += e; sensingOpRounds[i]++; }
        }

    const auto& obs = wl.roundObs[round - 1];
    rc.scheduled = (long)wl.scheduledPerRound[round - 1];   // Periyar: 10 slots per round
    rc.workloadAvailable = (long)obs.size();
    missedNoData += rc.scheduled - rc.workloadAvailable;
    for (int idx : obs) {
        const WorkloadReport& w = wl.reports[idx];
        ReportRecord rec;
        rec.reportIndex = w.index; rec.round = w.round; rec.sourceNode = w.sourceNode;
        rec.station = w.station.c_str(); rec.date = w.date.c_str();
        rec.genTime = simTime().dbl();
        rec.payloadBits = w.payloadBits;
        if (!events.empty()) {
            auto ev = events.find((long long)w.sourceNode * 100000 + w.round);
            if (ev != events.end()) {
                rec.eventClass = ev->second.cls; rec.triggerField = ev->second.field;
                rec.triggerValue = ev->second.value; rec.deadline = ev->second.deadline;
            }
        }
        rec.numValues = (int)w.values.size();         // application payload (routing never reads it)
        for (size_t k = 0; k < w.values.size(); k++) rec.values[k] = w.values[k];
        SensorNode *src = node(w.sourceNode);
        if (src->isAlive()) {                         // sourceAvailable uses aliveAtStart (line 128)
            rc.sourceAvailable++;
            src->assignReport(rec);
        }
        else
            setFate(rec, FATE_SOURCE_DOWN);
    }
    rc.sourceUnavailable = rc.scheduled - rc.sourceAvailable;
    phase = PH_CLUSTER;
    phaseIndex = 0;
    dispatchNext();
}

void Controller::dispatchNext()
{
    if (wireless) { dispatchConcurrent(); return; }
    if (phase == PH_CLUSTER) {
        while (phaseIndex < (int)wl.sensingNodes.size()) {
            SensorNode *src = node(wl.sensingNodes[phaseIndex++]);
            if (!src->hasOwnReport()) continue;
            if (!src->isAlive()) {                    // line 145: reps>0 but died earlier this round
                setFate(src->ownReport(), FATE_UNATTEMPTED);
                src->clearOwnReport();
                continue;
            }
            src->deliverCommand(CMD_CLUSTER, round);   // event at the node at the same time (no radio frame)
            return;
        }
        phase = PH_ROUTE;
        phaseIndex = 1;
    }
    if (phase == PH_ROUTE) {
        while (phaseIndex <= sc.numNodes) {           // line 261: for ch = 1:n
            SensorNode *ch = node(phaseIndex++);
            if (ch->clusterReportCount() == 0) continue;
            ch->deliverCommand(CMD_ROUTE, round);
            return;
        }
        phase = PH_IDLE;
        endRound();
    }
}

void Controller::dispatchConcurrent()
{
    // ieee802154: every decision of a phase starts at once, with a uniform jitter (controller rng-0), and the phase ends when
    // all its activities (member hops, critical routes, route frames) have ended
    if (phase == PH_CLUSTER) {
        if (!phaseStarted) {
            phaseStarted = true;
            for (int idx = 0; idx < (int)wl.sensingNodes.size(); idx++) {
                SensorNode *src = node(wl.sensingNodes[idx]);
                if (!src->hasOwnReport()) continue;
                if (!src->isAlive()) { setFate(src->ownReport(), FATE_UNATTEMPTED); src->clearOwnReport(); continue; }
                outstanding++;
                src->deliverCommand(CMD_CLUSTER, round, uniform(0, clusterJitter.dbl()));
            }
        }
        if (outstanding > 0) return;
        phase = PH_ROUTE;
        phaseStarted = false;
    }
    if (phase == PH_ROUTE) {
        if (!phaseStarted) {
            phaseStarted = true;
            for (int i = 1; i <= sc.numNodes; i++) {
                SensorNode *ch = node(i);
                if (ch->clusterReportCount() == 0) continue;
                outstanding++;
                ch->deliverCommand(CMD_ROUTE, round, uniform(0, routeJitter.dbl()));
            }
        }
        if (outstanding > 0) return;
        phase = PH_IDLE;
        phaseStarted = false;
        endRound();
    }
}

void Controller::setLinkBudgetPrior(cModule *host)
{
    // ieee802154: the agent's link prior is the expected link quality of the channel actually simulated, as MATLAB's
    // distancePriorLQ is that of its abstract channel law: reception ratio of an isolated link of length d for a maximum
    // 127-byte PSDU, from INET's own parameters (BreakpointPathLoss, background noise, transmitter power, receiver
    // sensitivity and SNIR threshold, isotropic antennas) and the DSSS-OQPSK BER of IEEE 802.15.4-2006 E.4.1.8 (INET's
    // DsssOqpsk16Modulation); clipped to MATLAB's link-quality bounds [0.1, 0.95]. Interference is not part of the prior.
    cModule *med = getParentModule()->getSubmodule("radioMedium");
    cModule *pl = med->getSubmodule("pathLoss"), *radio = host->getSubmodule("wlan")->getSubmodule("radio");
    if (std::string(pl->getNedTypeName()) != "inet.physicallayer.wireless.common.pathloss.BreakpointPathLoss"
        || std::string(radio->getSubmodule("antenna")->getNedTypeName()) != "inet.physicallayer.wireless.common.antenna.IsotropicAntenna")
        throw cRuntimeError("wirelessLinkPrior = \"linkBudget\" assumes INET BreakpointPathLoss and IsotropicAntenna");
    double l01 = pl->par("l01"), a1 = pl->par("alpha1"), l02 = pl->par("l02"), a2 = pl->par("alpha2");
    double bp = pl->par("breakpointDistance"), noise = med->getSubmodule("backgroundNoise")->par("power");   // m, dBm
    double ptx = 10 * std::log10(1000 * radio->getSubmodule("transmitter")->par("power").doubleValue());     // dBm
    double sens = radio->getSubmodule("receiver")->par("sensitivity"), snirTh = radio->getSubmodule("receiver")->par("snirThreshold");
    double bits = (double)radio->getSubmodule("transmitter")->par("headerLength").intValue() + 8 * 127;
    auto prr = [&](double d) {
        double loss = d < bp ? l01 + 10 * a1 * std::log10(d) : l02 + 10 * a2 * std::log10(d / bp);
        double prx = ptx - loss, snirdB = prx - noise;
        if (prx < sens || snirdB < snirTh) return 0.0;
        double s = 20 * std::pow(10, snirdB / 10), sum = 0, c = 1;           // c = C(16, k)
        for (int k = 1; k <= 16; k++) { c = c * (17 - k) / k; if (k >= 2) sum += (k % 2 ? -c : c) * std::exp(s * (1.0 / k - 1)); }
        return std::pow(1 - std::min(1.0, std::max(0.0, 8.0 / 15 / 16 * sum)), bits);
    };
    int n = sc.numNodes;
    for (int i = 0; i < n; i++)
        for (int j = 0; j <= n; j++)
            if (j != i) sc.prior[i * (n + 1) + j] = std::min(0.95, std::max(0.1, prr(j == n ? sc.distBS(i) : sc.distNode(i, j))));
    std::ofstream f;                                     // the prior curve, for the report
    openOut(f, prefix + "-link_prior.csv", "distance_m,prr");
    for (int d = 1; d <= 150; d++) f << d << "," << num(prr(d)) << '\n';
}

void Controller::loadEvents(const std::string& path)
{
    // data/events/<dataset>.csv from tools/build_event_annotations.py: node_id,round,event_class,trigger_field,trigger_value,deadline_s
    std::ifstream in(path);
    if (!in) throw cRuntimeError("cannot open eventAnnotations file %s", path.c_str());
    std::string line;
    std::getline(in, line);
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        std::vector<std::string> f;
        size_t a = 0, b;
        while ((b = line.find(',', a)) != std::string::npos) { f.push_back(line.substr(a, b - a)); a = b + 1; }
        f.push_back(line.substr(a));
        if (f.size() < 6) throw cRuntimeError("bad eventAnnotations line: %s", line.c_str());
        events[std::stoll(f[0]) * 100000 + std::stoll(f[1])] = {std::stoi(f[2]), std::stoi(f[3]), std::stod(f[4]), std::stod(f[5])};
    }
}

void Controller::endRound()
{
    // lines 464-497
    epsilon = std::max(epsilonMinimum, epsilon * epsilonDecay);
    auto check = [&](bool ok, const char *what) {
        if (!ok) throw cRuntimeError("round %d: MATLAB invariant violated: %s", round, what);
    };
    check(rc.scheduled == rc.sourceUnavailable + rc.sourceAvailable, "scheduled == sourceUnavailable + sourceAvailable");
    check(rc.sourceAvailable == rc.unattempted + rc.attempts, "sourceAvailable == unattempted + attempts");
    check(rc.attempts == rc.delivered + rc.stageLoss, "attempts == delivered + stageLoss");
    check(rc.physicalFrames == rc.successfulFrames + rc.failedFrames, "physicalFrames == successful + failed");
    check(rc.lossNoCandidate + rc.lossChannel + rc.lossEnergy + rc.lossTTL == rc.stageLoss, "loss causes == stageLoss");
    for (size_t i = 0; i < fate.size(); i++)
        if (wl.reports[i].round == round) check(fate[i] != FATE_NONE, "every report of the round has exactly one fate");
    for (auto nd : nodes) nd->endRoundLoadUpdate();
    double energyEnd = 0;
    for (auto nd : nodes) { check(nd->energy() >= 0 && nd->energy() <= sc.initialEnergy + 1e-12, "0 <= E <= E0"); energyEnd += nd->energy(); }
    double spent = rc.txE + rc.rxE + rc.aggE;
    check(std::fabs((energyStartOfRound - energyEnd) - spent) < 1e-10, "battery-energy conservation");
    for (auto nd : nodes) nd->applyMinimumEnergyRule();
    int aliveCount = 0;
    double residual = 0;
    for (auto nd : nodes) { aliveCount += nd->isAlive() ? 1 : 0; residual += nd->energy(); }
    aliveCountPerRound.push_back(aliveCount);
    residualPerRound.push_back(residual);
    perRoundLog << round << "," << rc.delivered << "," << aliveCount << "," << num(residual) << "," << rc.qUpdates << ","
                << rc.explorations << "," << num(rc.epsilon) << "," << rc.scheduled << "," << rc.workloadAvailable << ","
                << rc.sourceAvailable << "," << rc.attempts << "," << rc.unattempted << "," << rc.stageLoss << ","
                << rc.lossNoCandidate << "," << rc.lossChannel << "," << rc.lossEnergy << "," << rc.lossTTL << ","
                << rc.physicalFrames << "," << num(rc.txE) << "," << num(rc.rxE) << "," << num(rc.aggE) << ","
                << simTime().dbl() << "\n";
    addTotals(rc);
    emit(roundEndSignal, (long)round);
    if (round < numRounds) {
        simtime_t next = roundPeriod * round;
        if (simTime() >= next) throw cRuntimeError("round %d overran its %g s period", round, roundPeriod.dbl());
        scheduleAt(next, roundTimer);
    }
}

void Controller::addTotals(const RoundCounters& c)
{
    total.scheduled += c.scheduled; total.workloadAvailable += c.workloadAvailable;
    total.sourceAvailable += c.sourceAvailable; total.sourceUnavailable += c.sourceUnavailable;
    total.delivered += c.delivered; total.attempts += c.attempts; total.stageLoss += c.stageLoss;
    total.unattempted += c.unattempted; total.lossNoCandidate += c.lossNoCandidate; total.lossChannel += c.lossChannel;
    total.lossEnergy += c.lossEnergy; total.lossTTL += c.lossTTL; total.physicalFrames += c.physicalFrames;
    total.successfulFrames += c.successfulFrames; total.failedFrames += c.failedFrames;
    total.qUpdates += c.qUpdates; total.explorations += c.explorations; total.exploitations += c.exploitations;
    total.txE += c.txE; total.rxE += c.rxE; total.aggE += c.aggE; total.delayDelivered += c.delayDelivered;
    total.hopTotal += c.hopTotal; total.hopReports += c.hopReports;
    total.txBits += c.txBits; total.txReports += c.txReports;
}

// ---------------------------------------------------------------- bookkeeping

void Controller::setFate(const ReportRecord& r, ReportFate f, int hops, double pathDelay)
{
    Enter_Method_Silent();
    int i = r.reportIndex - 1;
    if (i < 0 || i >= (int)fate.size()) throw cRuntimeError("bad report index %d", r.reportIndex);
    if (fate[i] != FATE_NONE)
        throw cRuntimeError("report %d already has fate %s, cannot set %s", r.reportIndex, FATE_NAMES[fate[i]], FATE_NAMES[f]);
    fate[i] = f;
    fateRound[i] = round;
    if (f == FATE_DELIVERED && deliveredPayloadLog.is_open()) {   // r = the record carried in the frame received by the BS
        deliveredPayloadLog << r.reportIndex << "," << r.sourceNode << "," << r.station.c_str() << "," << r.date.c_str();
        for (int k = 0; k < r.numValues; k++) deliveredPayloadLog << "," << num(r.values[k]);
        deliveredPayloadLog << "\n";
    }
    switch (f) {
        case FATE_DELIVERED: rc.delivered++; break;
        case FATE_LOST_CHANNEL: rc.stageLoss++; rc.lossChannel++; break;
        case FATE_LOST_ENERGY: rc.stageLoss++; rc.lossEnergy++; break;
        case FATE_LOST_NOCANDIDATE: rc.stageLoss++; rc.lossNoCandidate++; break;
        case FATE_LOST_TTL: rc.stageLoss++; rc.lossTTL++; break;
        case FATE_SOURCE_DOWN: missedSourceDown++; break;
        case FATE_UNATTEMPTED: rc.unattempted++; break;
        default: break;
    }
    reportLog << r.reportIndex << "," << r.round << "," << r.sourceNode << "," << r.station.c_str() << "," << r.date.c_str()
              << "," << FATE_NAMES[f] << "," << round << "," << hops << "," << num(pathDelay);
    if (extendedReports)                           // generation-to-delivery latency (delivered reports) and event fields
        reportLog << "," << num(f == FATE_DELIVERED ? simTime().dbl() - r.genTime : NAN) << "," << num(r.queueDelay) << ","
                  << r.eventClass << "," << r.triggerField << "," << num(r.triggerValue) << "," << num(r.deadline);
    reportLog << "\n";
}

void Controller::logDecision(int hopType, int actor, int target, int reports, const double ctx[6], double outcome,
                             bool explored, int state, int numCandidates, simtime_t decisionTime, int hop)
{
    if (decisionLog.is_open())
    decisionLog << round << "," << hopType << "," << actor << "," << target << "," << reports << "," << num(ctx[0]) << ","
                << num(ctx[1]) << "," << (long)ctx[2] << "," << (long)ctx[3] << "," << num(ctx[4]) << "," << num(ctx[5])
                << "," << num(outcome) << "," << (explored ? 1 : 0) << "," << state << "," << numCandidates << ","
                << num(simTime().dbl()) << "," << num(decisionTime.dbl()) << "," << hop << "\n";
    if (diagnostics && target != actor) {        // a real transmission; its outcome is already known here
        int bsId = sc.numNodes + 1;
        double dist = target == bsId ? sc.distBS(actor - 1) : sc.distNode(actor - 1, target - 1);
        diagLog << round << "," << hopType << "," << actor << "," << target << "," << hop << "," << reports << ","
                << numCandidates << "," << (explored ? 1 : 0) << "," << num(outcome) << "," << num(trueLQ(actor, target)) << ","
                << num(ctx[0]) << "," << num(ctx[1]) << "," << num(dist) << "," << (actor > sc.matlabBlock ? 1 : 0) << ","
                << (target > sc.matlabBlock && target != bsId ? 1 : 0) << "\n";
    }
}

double Controller::trueLQ(int i, int j) const
{
    // diagnostics only: the link quality that produced this round's outcome on link i -> j
    const int n0 = sc.matlabBlock;
    if (i <= n0 && (j <= n0 || j == sc.numNodes + 1)) {
        int jb = (j == sc.numNodes + 1) ? n0 + 1 : j;
        return lqRound[(i - 1) + (jb - 1) * n0];
    }
    return sc.extraLinkLQ(round, i, j);
}

void Controller::logUnavailable(int nd, const char *reason, double energy)
{
    Enter_Method_Silent();
    unavailLog << round << "," << num(simTime().dbl()) << "," << nd << "," << reason << "," << num(energy) << "\n";
}

// ---------------------------------------------------------------- display only (no effect on the model)

// Display transform: metres -> canvas pixels (map area 960 x 340 px, see PeriyarValidation.ned).
// Routing, energy and channel calculations never use these values.
static double mapX(double x) { return 60 + 1.6 * x; }
static double mapY(double y) { return 140 + 6.8 * y; }

static std::string stationShortName(const std::string& full)
{
    // short display labels for the station names used by the MATLAB workload (display only)
    static const std::map<std::string, std::string> shortNames = {
        {"ALUVA - MANAPPURAM", "Aluva"}, {"PURAPILLIKADAVU US", "Purap. US"},
        {"PURAPILLIKADAVU BUND NAVIGATION", "Purap. Nav"}, {"PURAPILLIKADAVU BUND DS", "Purap. DS"},
        {"PATHALAM BUND U/S", "Path. Bund US"}, {"PATHALAM BUND D/S", "Path. Bund DS"},
        {"PATHALAM BRIDGE", "Path. Bridge"}, {"PUTHALAM KADAVU", "Puthalam K."},
        {"MANJUMMAL BUND", "Manjummal"}, {"VETTUKADAVU", "Vettukadavu"}};
    auto it = shortNames.find(full);
    return it == shortNames.end() ? full : it->second;
}

void Controller::setupDisplay()
{
    // roles and station names come from the workload (= create_periyar_workload_continuous.m mapping)
    std::map<int, std::string> stationOfNode;
    for (size_t s = 0; s < wl.stationNames.size(); s++)
        stationOfNode[wl.sensingNodes[s]] = wl.stationNames[s];
    for (int i = 0; i < sc.numNodes; i++) {
        SensorNode *nd = nodes[i];
        auto it = stationOfNode.find(i + 1);
        bool sensing = it != stationOfNode.end();
        char ds[160];
        snprintf(ds, sizeof(ds), sensing ? "p=%.1f,%.1f;b=16,16,oval,#1f6fd1,#0b3d80,1" : "p=%.1f,%.1f;b=9,9,oval,#a8a8a8,#6e6e6e,1",
                 mapX(sc.X[i]), mapY(sc.Y[i]));
        nd->getDisplayString().parse(ds);
        if (sensing) nd->setDisplayName(stationShortName(it->second).c_str());
        else
            nd->setDisplayName(("n" + std::to_string(i + 1)).c_str());   // module node[i] = node id i+1
        nd->setDisplayRole(sensing, sensing ? it->second : std::string());
    }
    char ds[120];
    snprintf(ds, sizeof(ds), "p=%.1f,%.1f;i=device/antennatower;is=s", mapX(sc.bsX), mapY(sc.bsY));
    bs->getDisplayString().parse(ds);

    std::ostringstream st;
    st << "Sensing stations (MATLAB workload mapping)\n";
    for (size_t s = 0; s < wl.stationNames.size(); s++)
        st << "n" << wl.sensingNodes[s] << "  " << stationShortName(wl.stationNames[s]) << "  =  " << wl.stationNames[s] << "\n";
    if (auto fig = dynamic_cast<cTextFigure *>(getParentModule()->getCanvas()->getFigure("stations")))
        fig->setText(st.str().c_str());
}

void Controller::noteHop(int from, int to, bool decodedOk)
{
    // display only: remember the frame transfers of the current round for drawing
    recentHops.push_back({from, to, decodedOk});
    if (recentHops.size() > 14) recentHops.pop_front();
}

void Controller::refreshDisplay() const
{
    int alive = 0;
    for (auto nd : nodes) alive += nd->isAlive();
    long sched = total.scheduled + rc.scheduled, valid = total.workloadAvailable + rc.workloadAvailable;
    long deliv = total.delivered + rc.delivered, qupd = total.qUpdates + rc.qUpdates;
    const char *cfg = getEnvir()->getConfigEx()->getActiveConfigName();
    bool preview = numRounds < sc.numRounds;
    char buf[900];
    snprintf(buf, sizeof(buf),
             "Configuration: %s   (seed %d)      Round %d of %d%s\n"
             "Scheduled report slots so far: %ld  (this run: %d; full workload: %d)      Valid-data slots so far: %ld      Reports delivered to BS: %ld\n"
             "PDR so far = delivered / scheduled slots so far = %ld / %ld = %.2f %%\n"
             "WSN nodes: %d operational, %d unavailable (of %d)      Q-table updates: %ld      epsilon: %.4f",
             cfg, sc.seed, round, numRounds,
             preview ? "      PREVIEW: first rounds only - not a benchmark result"
                     : "      complete 1000-round experiment",
             sched, (int)std::accumulate(wl.scheduledPerRound.begin(), wl.scheduledPerRound.begin() + std::min<size_t>(numRounds, wl.scheduledPerRound.size()), 0), wl.totalScheduled, valid, deliv,
             deliv, sched, sched ? 100.0 * deliv / sched : 0.0,
             alive, sc.numNodes - alive, sc.numNodes, qupd, epsilon);
    cCanvas *canvas = getParentModule()->getCanvas();
    if (auto fig = dynamic_cast<cTextFigure *>(canvas->getFigure("status")))
        fig->setText(buf);

    // transient lines for this round's frame transfers: green = decoded, red dashed = lost
    if (auto grp = canvas->getFigure("hops")) {
        while (grp->getNumFigures() > 0)
            delete grp->removeFigure(0);
        for (auto& h : recentHops) {
            auto line = new cLineFigure();
            double x1 = mapX(sc.X[h.from - 1]), y1 = mapY(sc.Y[h.from - 1]);
            double x2 = h.to > sc.numNodes ? mapX(sc.bsX) : mapX(sc.X[h.to - 1]);
            double y2 = h.to > sc.numNodes ? mapY(sc.bsY) : mapY(sc.Y[h.to - 1]);
            line->setStart(cFigure::Point(x1, y1));
            line->setEnd(cFigure::Point(x2, y2));
            line->setLineColor(h.ok ? cFigure::Color("#2e9e44") : cFigure::Color("#d62728"));
            line->setLineWidth(h.ok ? 3 : 2);
            line->setLineStyle(h.ok ? cFigure::LINE_SOLID : cFigure::LINE_DASHED);
            line->setEndArrowhead(cFigure::ARROW_BARBED);
            grp->addFigure(line);
        }
    }
}

void Controller::finish()
{
    if (sc.retransmission) {
        recordScalar("retransmissionsSent", retransmissionsSent);
        recordScalar("retransmissionsDecoded", retransmissionsDecoded);
        recordScalar("retransmissionsExpectedDecoded", retransmissionsExpected);
        recordScalar("retransmissionsDecodedVariance", retransmissionsVariance);
    }
    // MATLAB metric definitions (run_five_seed_rl_hybrid.m / run_final_project_dashboards.m)
    int fnd = -1;
    for (size_t r = 0; r < aliveCountPerRound.size(); r++)
        if (aliveCountPerRound[r] < sc.numNodes) { fnd = (int)r + 1; break; }
    int finalAlive = aliveCountPerRound.empty() ? sc.numNodes : aliveCountPerRound.back();
    double residual = 0, e0 = 0;
    for (auto nd : nodes) { residual += nd->energy(); e0 += sc.initialEnergy; }
    double spent = total.txE + total.rxE + total.aggE;
    double pdr = total.scheduled ? 100.0 * total.delivered / total.scheduled : NAN;
    double epr = total.delivered ? spent / total.delivered : NAN;
    double meanHops = total.hopReports ? (double)total.hopTotal / total.hopReports : NAN;
    double meanDelay = total.delivered ? total.delayDelivered / total.delivered : NAN;
    double firstUnav = NAN; int firstNode = 0;
    for (auto nd : nodes)
        if (!std::isnan(nd->firstUnavailable()) && (std::isnan(firstUnav) || nd->firstUnavailable() < firstUnav)) {
            firstUnav = nd->firstUnavailable(); firstNode = nd->id();
        }
    long fateCount[NUM_FATES] = {};
    for (auto v : fate) fateCount[v]++;
    bool energyCloses = std::fabs(spent + residual - e0) < 1e-8;
    long emitted = total.sourceAvailable;
    bool complete = (round == sc.numRounds);
    // Periyar: 10000 / 9825 / 175 (the workload's expected* guards enforce the Periyar counts at load time)
    bool slotsOk = !complete || (total.scheduled == wl.totalScheduled && total.workloadAvailable == wl.totalAvailable &&
                   missedNoData == wl.totalUnavailable && fateCount[FATE_NONE] == 0 &&
                   emitted + fateCount[FATE_SOURCE_DOWN] == wl.totalAvailable);

    recordScalar("scheduledSlots", total.scheduled);
    recordScalar("validDataSlots", total.workloadAvailable);
    recordScalar("preObservationSlots", missedNoData);
    recordScalar("sourceUnavailableDataSlots", missedSourceDown);
    recordScalar("reportsEmitted", emitted);
    recordScalar("reportsAttempted", total.attempts);
    recordScalar("reportsUnattempted", total.unattempted);
    recordScalar("reportsDelivered", total.delivered);
    recordScalar("networkLossTotal", total.stageLoss);
    recordScalar("lossChannel", total.lossChannel);
    recordScalar("lossEnergy", total.lossEnergy);
    recordScalar("lossNoCandidate", total.lossNoCandidate);
    recordScalar("lossTTL", total.lossTTL);
    recordScalar("PDR_scheduled_percent", pdr);
    recordScalar("FND_round", fnd);
    recordScalar("finalOperationalNodes", finalAlive);
    recordScalar("residualEnergy", residual, "J");
    recordScalar("energySpent", spent, "J");
    recordScalar("energyPerDeliveredReport", epr, "J");
    recordScalar("meanDeliveredHops", meanHops);
    recordScalar("meanPathDelay", meanDelay, "s");
    recordScalar("qUpdates", total.qUpdates);
    recordScalar("explorationDecisions", total.explorations);
    recordScalar("exploitationDecisions", total.exploitations);
    recordScalar("physicalFrames", total.physicalFrames);
    recordScalar("successfulFrames", total.successfulFrames);
    recordScalar("failedFrames", total.failedFrames);
    recordScalar("agentRngDraws", (double)agentRng.numDraws());

    std::ofstream m;
    openOut(m, prefix + "-metrics.csv",
            "seed,scheduled,workloadAvailable,sourceAvailable,attempts,unattempted,delivered,stageLoss,lossNoCandidate,"
            "lossChannel,lossEnergy,lossTTL,PDR,FND,finalAlive,residualJ,spentJ,energyPerDeliveredJ,meanHops,meanDelayS,"
            "qUpdates,explorations,exploitations,physicalFrames");
    m << sc.seed << "," << total.scheduled << "," << total.workloadAvailable << "," << total.sourceAvailable << ","
      << total.attempts << "," << total.unattempted << "," << total.delivered << "," << total.stageLoss << ","
      << total.lossNoCandidate << "," << total.lossChannel << "," << total.lossEnergy << "," << total.lossTTL << ","
      << num(pdr) << "," << fnd << "," << finalAlive << "," << num(residual) << "," << num(spent) << "," << num(epr) << ","
      << num(meanHops) << "," << num(meanDelay) << "," << total.qUpdates << "," << total.explorations << ","
      << total.exploitations << "," << total.physicalFrames << "\n";
    m.close();

    std::ofstream u;
    openOut(u, prefix + "-unavailability.csv", "node,firstUnavailableRound,reason");
    for (auto nd : nodes) u << nd->id() << "," << num(nd->firstUnavailable()) << "," << nd->unavailableReason() << "\n";
    u.close();

    std::ostringstream s;
    s << std::fixed;
    s << "==== Periyar RL-Hybrid OMNeT++ validation run (logged measurements) ====\n";
    s << "seed                     : " << sc.seed << "   rounds simulated: " << round << " of " << sc.numRounds << "\n";
    s << "network                  : " << sc.numNodes << " battery nodes + BS (" << sc.bsX << ", " << sc.bsY << "), "
      << std::defaultfloat << sc.riverLength << " x " << sc.riverWidth << " m, E0 = " << sc.initialEnergy << " J\n" << std::fixed;
    if (!par("scenario").stdstringValue().empty())
        s << "scenario                 : " << par("scenario").stdstringValue() << "   (" << par("scenarioDataset").stdstringValue() << ")\n";
    int interval = par("reportInterval").intValue();
    bool profileSchedule = !wl.sensingmJ.empty() && par("scenarioMode").stdstringValue() == "m2";
    s << "scheduled slots          : " << total.scheduled << "   (" << (profileSchedule ? std::string("m2 profile schedule: one slot per report")
      : std::to_string(wl.sensingNodes.size()) + " per round" + (interval > 1 ? ", every " + std::to_string(interval) + " rounds" : std::string())) << ")\n";
    s << "  pre-observation slots  : " << missedNoData << "   (no data yet; never a report)\n";
    s << "  valid-data slots       : " << total.workloadAvailable << "\n";
    s << "    source unavailable   : " << missedSourceDown << "   (valid data, source down at round start)\n";
    s << "    reports emitted      : " << emitted << "\n";
    s << "      unattempted        : " << total.unattempted << "\n";
    s << "      attempted          : " << total.attempts << "\n";
    s << "        delivered        : " << total.delivered << "\n";
    s << "        network losses   : " << total.stageLoss << "  (channel " << total.lossChannel << ", energy "
      << total.lossEnergy << ", no candidate " << total.lossNoCandidate << ", TTL " << total.lossTTL << ")\n";
    s << std::setprecision(3);
    s << "PDR (delivered/scheduled): " << pdr << " %\n";
    s << "delivered / emitted      : " << (emitted ? 100.0 * total.delivered / emitted : NAN) << " %  (conditional; not the MATLAB PDR)\n";
    s << "FND (first round < " << sc.numNodes << " op): " << fnd << "\n";
    s << "first unavailable node   : " << firstNode << "  (MATLAB firstUnavailableRound " << firstUnav << ")\n";
    s << "final operational nodes  : " << finalAlive << "\n";
    s << std::setprecision(4);
    s << "residual energy          : " << residual << " J   spent " << spent << " J (tx " << total.txE << ", rx "
      << total.rxE << ", aggregation " << total.aggE << ")\n";
    s << std::setprecision(6);
    s << "energy / delivered report: " << epr << " J\n";
    s << std::setprecision(3);
    s << "mean delivered hops      : " << meanHops << "\n";
    s << std::setprecision(5);
    s << "mean path delay          : " << meanDelay << " s  " << (sc.perReportBits
        ? "(sum of frame bits/Rbit + Tproc + d/c per hop)\n" : "(sum of k/Rbit + Tproc + d/c per hop, MATLAB definition)\n");
    s << "Q updates / explorations : " << total.qUpdates << " / " << total.explorations << "  (exploitation "
      << total.exploitations << ", agent RNG draws " << agentRng.numDraws() << ")\n";
    s << "checks                   : energy closes " << (energyCloses ? "OK" : "FAIL")
      << "; slot accounting " << (slotsOk ? "OK" : "FAIL") << "; per-round MATLAB invariants OK (enforced every round)\n";
    if (!wl.sensingmJ.empty()) {                     // scenario study: separate sensing ledger
        std::ofstream lg;
        openOut(lg, prefix + "-sensing_ledger.csv", "node,sensorType,operationalRounds,sensingJ_operational,sensingJ_allRounds");
        double op = 0, all = 0;
        for (int i = 0; i < sc.numNodes; i++) {
            lg << i + 1 << "," << wl.nodeProfile[i] << "," << sensingOpRounds[i] << "," << num(sensingOpJ[i]) << ","
               << num(sensingAllJ[i]) << "\n";
            op += sensingOpJ[i]; all += sensingAllJ[i];
        }
        double genBits = 0;
        for (auto& r : wl.reports) genBits += reportBits(r.index);
        s << std::setprecision(1) << "radio traffic            : " << total.txBits / 1e6 << " Mbit on air in " << total.txReports
          << " report transmissions (mean " << (total.txReports ? total.txBits / total.txReports : NAN) << " bit); mean generated frame "
          << (wl.reports.empty() ? NAN : genBits / wl.reports.size()) << " bit" << (sc.perReportBits ? " (per-report frames)" : "") << "\n";
        s << std::setprecision(1) << "sensing ledger (separate): " << op << " J in operational node-rounds (" << all
          << " J if all nodes sensed all " << round << " rounds); NOT charged to the " << sc.initialEnergy << " J radio battery\n";
    }
    std::ofstream sf;
    openOut(sf, prefix + "-summary.txt", nullptr);
    sf << s.str();
    sf.close();
    std::cout << s.str() << std::flush;
    if (!energyCloses || !slotsOk) throw cRuntimeError("final accounting checks failed");
}
