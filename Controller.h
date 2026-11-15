#ifndef __PERIYAR_CONTROLLER_H
#define __PERIYAR_CONTROLLER_H

#include <omnetpp.h>
#include <deque>
#include <fstream>
#include <map>
#include <string>
#include <vector>

#include "MatlabRng.h"
#include "PeriyarModel.h"
#include "Messages_m.h"

using namespace omnetpp;

class SensorNode;
class BaseStation;

enum ReportFate { FATE_NONE = 0, FATE_DELIVERED, FATE_LOST_CHANNEL, FATE_LOST_ENERGY,
                  FATE_LOST_NOCANDIDATE, FATE_LOST_TTL, FATE_UNATTEMPTED,
                  FATE_SOURCE_DOWN,   // valid data, but the source was unavailable at round start (not emitted)
                  NUM_FATES };

/**
 * Round controller. It is NOT a radio node. It reproduces the round structure of
 * RL_Hybrid.m as a sequence of simulation events:
 *   round start  -> channel realisation for the round, workload slots, report emission
 *   cluster phase-> each live sensing source, in MATLAB order, chooses a head (and may transmit)
 *   route phase  -> each cluster head 1..50 with a payload aggregates and routes it hop by hop
 *   round end    -> epsilon decay, load EWMA, 200 uJ rule, per-round records
 * Each step starts only after the previous one has finished (a Done notification),
 * which reproduces MATLAB's sequential order of decisions.
 * It also owns the MATLAB-compatible exploration stream rng(seed,'twister') that
 * RL_Hybrid.m uses for rand()/randi(), and the shared epsilon.
 */
class Controller : public cSimpleModule
{
  public:
    struct RoundCounters {
        long scheduled = 0, workloadAvailable = 0, sourceAvailable = 0, sourceUnavailable = 0;
        long delivered = 0, attempts = 0, stageLoss = 0, unattempted = 0;
        long lossNoCandidate = 0, lossChannel = 0, lossEnergy = 0, lossTTL = 0;
        long physicalFrames = 0, successfulFrames = 0, failedFrames = 0;
        long qUpdates = 0, explorations = 0, exploitations = 0;
        double txE = 0, rxE = 0, aggE = 0, delayDelivered = 0;
        double txBits = 0;            // radio traffic: bits on air (report-preserving: sum of the reports' bits)
        long txReports = 0;           // report transmissions (one report on one hop attempt)
        long hopTotal = 0, hopReports = 0;
        double epsilon = 0;
    };

  protected:
    Scenario sc;
    Workload wl;
    MatlabTwister agentRng;           // RL_Hybrid.m: rng(seed,'twister') -> rand()/randi()
    double epsilon = 0.25, epsilonMinimum = 0.05, epsilonDecay = 0.9985;
    int numRounds = 1000;
    int round = 0;                    // current round (1-based); 0 before the first round
    std::vector<unsigned char> success;   // success_history(:,:,round), column-major
    // diagnostics (exportDiagnostics = true): true link quality of the original block this round, and a
    // per-transmission log. Written after the outcome is known; never read by any routing decision.
    bool diagnostics = false;
    std::vector<double> lqRound;
    std::ofstream diagLog;
    std::ofstream deliveredPayloadLog;   // exportDeliveredPayload: payload as received by the BS (test evidence)
    double trueLQ(int i, int j) const;
    long retransmissionsSent = 0;
    mutable long retransmissionsDecoded = 0;
    mutable double retransmissionsExpected = 0, retransmissionsVariance = 0;   // sum lq, sum lq(1-lq)
    simtime_t roundPeriod, guard;

    std::vector<SensorNode *> nodes;  // index = MATLAB id - 1
    BaseStation *bs = nullptr;

    enum Phase { PH_IDLE, PH_CLUSTER, PH_ROUTE } phase = PH_IDLE;
    int phaseIndex = 0;
    std::map<int, int> pendingSourceReport;   // MATLAB node id -> workload report position, this round
    std::vector<ReportRecord> roundReports;   // records emitted this round (template copies)

    RoundCounters rc;                 // current round
    RoundCounters total;
    std::vector<int> aliveCountPerRound;
    std::vector<double> residualPerRound;
    std::vector<unsigned char> fate;          // per workload report (index 0..9824)
    std::vector<int> fateRound;
    long missedNoData = 0, missedSourceDown = 0;
    double energyStartOfRound = 0;
    std::vector<double> sensingOpJ, sensingAllJ;   // scenario study: sensing ledger per node (J), separate from E
    std::vector<int> sensingOpRounds;

    std::ofstream decisionLog, perRoundLog, reportLog, unavailLog, eventLog;
    std::string prefix;

    cMessage *roundTimer = nullptr, *nextStepTimer = nullptr;
    // communicationModel "ieee802154" (wireless/ plugin) and the eventAware option
    bool wireless = false, eventAwareOn = false, extendedReports = false, phaseStarted = false;
    simtime_t wirelessAckTO, clusterJitter, routeJitter;
    int routingHeaderB = 6, macPayloadLimitB = 118, defaultPayloadB = 144, outstanding = 0;
    double frameOverheadB = 168, ageingS = 1;
    simsignal_t roundStartSignal = 0, roundEndSignal = 0;
    struct EventInfo { int cls; int field; double value; double deadline; };
    std::map<long long, EventInfo> events;       // (node * 100000 + round) -> event annotation
    void setLinkBudgetPrior(cModule *host);
    void loadEvents(const std::string& path);
    void dispatchConcurrent();
    struct Hop { int from, to; bool ok; };
    std::deque<Hop> recentHops;       // display only: frame transfers of the current round

    virtual int numInitStages() const override { return 2; }
    virtual void initialize(int stage) override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void refreshDisplay() const override;
    virtual void finish() override;

    void startRound();
    void dispatchNext();
    void endRound();
    void exportReferenceData();
    void addTotals(const RoundCounters& c);
    void setupDisplay();              // display only

  public:
    virtual ~Controller();
    // ---- read access for the nodes
    const Scenario& scenario() const { return sc; }
    int currentRound() const { return round; }
    double currentEpsilon() const { return epsilon; }
    SensorNode *node(int matlabId) const { return nodes[matlabId - 1]; }
    // radio-frame bits of a workload report: its own frame (scenarioFrameBits) or the uniform packetSize
    double reportBits(int reportIndex) const
        { return sc.perReportBits ? wl.reports[reportIndex - 1].bits : sc.packetSize; }
    BaseStation *baseStation() const { return bs; }
    bool wirelessMode() const { return wireless; }
    bool roundActive() const { return phase != PH_IDLE; }      // between endRound and the next startRound: false
    bool eventAware() const { return eventAwareOn; }
    simtime_t wirelessAckTimeout() const { return wirelessAckTO; }
    int routingHeaderBytes() const { return routingHeaderB; }
    int macPayloadLimitBytes() const { return macPayloadLimitB; }
    double frameOverheadBits() const { return frameOverheadB; }
    int defaultPayloadBits() const { return defaultPayloadB; }
    double ageingInterval() const { return ageingS; }
    void addOutstanding(int k) { Enter_Method_Silent(); outstanding += k; }
    // channel: was the frame i -> j decoded in this round? (j == n+1 is the BS; MATLAB ids)
    bool decoded(int i, int j) const;
    // decoded(i, j) for the first transmission; a retransmission (attempt >= 1, experimental option) gets an
    // independent draw at the same true link quality of this round (the per-round MATLAB bit would repeat)
    bool decodedAttempt(int i, int j, int attempt, int txSeq) const;
    void noteRetransmission() { retransmissionsSent++; }
    // shared exploration stream (the ONLY consumer is SensorNode::selectAction)
    double agentRand() { return agentRng.rand(); }
    int agentRandi(int n) { return agentRng.randi(n); }
    // ---- bookkeeping, called by the nodes at the points where RL_Hybrid.m counts
    RoundCounters& counters() { return rc; }
    void setFate(const ReportRecord& r, ReportFate f, int hops = -1, double pathDelay = NAN);
    simtime_t roundStartTime(int r) const { return roundPeriod * (r - 1); }
    void logDecision(int hopType, int actor, int target, int reports, const double ctx[6], double outcome,
                     bool explored, int state, int numCandidates, simtime_t decisionTime, int hop);
    void logUnavailable(int node, const char *reason, double energy);
    void stepDone();                  // a cluster decision or a route has finished
    void noteHop(int from, int to, bool decodedOk);   // display only (drawing of transfers)
};

#endif
