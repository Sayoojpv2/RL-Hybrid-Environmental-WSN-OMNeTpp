#include "Controller.h"
#include "BaseStation.h"
#include "SensorNode.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <numeric>
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
    try { sc.generate(seed, totalNodes, (uint32_t)extraSeed); }   // generate_scenario.m (+ added relays if N > 50)
    catch (std::exception& e) { throw cRuntimeError("%s", e.what()); }
    try { wl.build(par("datasetPath").stdstringValue(), sc.numRounds); }   // loader + workload builder
    catch (std::exception& e) { throw cRuntimeError("%s", e.what()); }
    agentRng.seed((uint32_t)seed);                      // RL_Hybrid.m line 28: rng(seed,'twister')

    // nodes are looked up by their nodeId parameter (MATLAB id), the BS by type
    cModule *net = getParentModule();
    nodes.assign(sc.numNodes, nullptr);
    for (cModule::SubmoduleIterator it(net); !it.end(); ++it) {
        if (auto nd = dynamic_cast<SensorNode *>(*it)) {
            int id = nd->par("nodeId").intValue();
            if (id < 1 || id > sc.numNodes || nodes[id - 1]) throw cRuntimeError("bad or duplicate nodeId %d", id);
            nodes[id - 1] = nd;
        }
        else if (auto b = dynamic_cast<BaseStation *>(*it)) {
            if (bs) throw cRuntimeError("more than one base station");
            bs = b;
        }
    }
    for (int i = 0; i < sc.numNodes; i++)
        if (!nodes[i]) throw cRuntimeError("node with nodeId %d missing", i + 1);
    if (!bs) throw cRuntimeError("base station missing");
    setupDisplay();
    fate.assign(wl.reports.size(), FATE_NONE);
    fateRound.assign(wl.reports.size(), 0);

    openOut(decisionLog, prefix + "-decisions.csv",
            "round,hopType,actor,target,reports,qHat,prior,attemptsBefore,successesBefore,actorE,targetE,outcome,"
            "explored,state,numCandidates,logTime,decisionTime,hop");
    openOut(perRoundLog, prefix + "-per_round.csv",
            "round,delivered,aliveCount,residualJ,qUpdates,explorations,epsilon,scheduled,workloadAvailable,"
            "sourceAvailable,attempts,unattempted,stageLoss,lossNoCandidate,lossChannel,lossEnergy,lossTTL,"
            "physicalFrames,txJ,rxJ,aggJ,roundEndTime");
    openOut(reportLog, prefix + "-reports.csv", "reportIndex,round,sourceNode,station,date,fate,resolvedRound,hops,pathDelayS");
    openOut(unavailLog, prefix + "-unavailability_events.csv", "round,simTime,node,reason,energyJ");

    if (par("exportReference").boolValue())
        exportReferenceData();
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
    openOut(f, prefix + "-workload.csv", "reportIndex,round,sourceNode,station,date,temperature,pH,conductivity,TDS");
    for (auto& r : wl.reports)
        f << r.index << "," << r.round << "," << r.sourceNode << "," << r.station << "," << r.date << ","
          << num(r.temperature) << "," << num(r.pH) << "," << num(r.conductivity) << "," << num(r.TDS) << "\n";
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
    // original MATLAB block (nodes 1..50 and the BS): bit-exact success_history(i,j,r)
    const int n0 = Scenario::MATLAB_NODES;
    if (i <= n0 && (j <= n0 || j == sc.numNodes + 1)) {
        int jb = (j == sc.numNodes + 1) ? n0 + 1 : j;
        return success[(i - 1) + (jb - 1) * n0] != 0;
    }
    return sc.extraLinkSuccess(round, i, j);              // link involving an added relay (N > 50 only)
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
    // a small guard lets in-flight value feedback reach its node before the next decision
    scheduleAt(simTime() + guard, nextStepTimer);
}

// ---------------------------------------------------------------- round structure

void Controller::startRound()
{
    round++;
    recentHops.clear();                              // display only
    rc = RoundCounters();
    rc.epsilon = epsilon;
    sc.channelForRound(round, success);              // success_history(:,:,round)
    energyStartOfRound = 0;
    for (auto nd : nodes) { energyStartOfRound += nd->energy(); nd->beginRound(); }

    const auto& obs = wl.roundObs[round - 1];
    rc.scheduled = (long)wl.sensingNodes.size();     // 10 slots per round
    rc.workloadAvailable = (long)obs.size();
    missedNoData += rc.scheduled - rc.workloadAvailable;
    for (int idx : obs) {
        const WorkloadReport& w = wl.reports[idx];
        ReportRecord rec;
        rec.reportIndex = w.index; rec.round = w.round; rec.sourceNode = w.sourceNode;
        rec.station = w.station.c_str(); rec.date = w.date.c_str();
        rec.temperature = w.temperature; rec.pH = w.pH; rec.conductivity = w.conductivity; rec.TDS = w.TDS;
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
              << "," << FATE_NAMES[f] << "," << round << "," << hops << "," << num(pathDelay) << "\n";
}

void Controller::logDecision(int hopType, int actor, int target, int reports, const double ctx[6], double outcome,
                             bool explored, int state, int numCandidates, simtime_t decisionTime, int hop)
{
    decisionLog << round << "," << hopType << "," << actor << "," << target << "," << reports << "," << num(ctx[0]) << ","
                << num(ctx[1]) << "," << (long)ctx[2] << "," << (long)ctx[3] << "," << num(ctx[4]) << "," << num(ctx[5])
                << "," << num(outcome) << "," << (explored ? 1 : 0) << "," << state << "," << numCandidates << ","
                << num(simTime().dbl()) << "," << num(decisionTime.dbl()) << "," << hop << "\n";
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
        else if (i + 1 > Scenario::MATLAB_NODES)                // added relay: module relay[k] = node id 51+k
            nd->setDisplayName(("n" + std::to_string(i + 1)).c_str());
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
             "Scheduled report slots so far: %ld  (this run: %d; full Periyar workload: %d)      Valid-data slots so far: %ld      Reports delivered to BS: %ld\n"
             "PDR so far = delivered / scheduled slots so far = %ld / %ld = %.2f %%\n"
             "WSN nodes: %d operational, %d unavailable (of %d)      Q-table updates: %ld      epsilon: %.4f",
             cfg, sc.seed, round, numRounds,
             preview ? "      PREVIEW: first rounds only - not a benchmark result"
                     : "      complete 1000-round experiment",
             sched, numRounds * (int)wl.sensingNodes.size(), wl.totalScheduled, valid, deliv,
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
    bool slotsOk = !complete || (total.scheduled == 10000 && total.workloadAvailable == 9825 && missedNoData == 175 &&
                   fateCount[FATE_NONE] == 0 && emitted + fateCount[FATE_SOURCE_DOWN] == 9825);

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
    s << "network                  : " << sc.numNodes << " battery nodes + BS (" << sc.bsX << ", " << sc.bsY << "), 600 x 50 m, E0 = 2 J\n";
    s << "scheduled slots          : " << total.scheduled << "   (10 per round)\n";
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
    s << "mean path delay          : " << meanDelay << " s  (sum of k/Rbit + Tproc + d/c per hop, MATLAB definition)\n";
    s << "Q updates / explorations : " << total.qUpdates << " / " << total.explorations << "  (exploitation "
      << total.exploitations << ", agent RNG draws " << agentRng.numDraws() << ")\n";
    s << "checks                   : energy closes " << (energyCloses ? "OK" : "FAIL")
      << "; slot accounting " << (slotsOk ? "OK" : "FAIL") << "; per-round MATLAB invariants OK (enforced every round)\n";
    std::ofstream sf;
    openOut(sf, prefix + "-summary.txt", nullptr);
    sf << s.str();
    sf.close();
    std::cout << s.str() << std::flush;
    if (!energyCloses || !slotsOk) throw cRuntimeError("final accounting checks failed");
}
