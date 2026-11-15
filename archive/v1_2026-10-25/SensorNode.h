#ifndef __PERIYAR_SENSORNODE_H
#define __PERIYAR_SENSORNODE_H

#include <omnetpp.h>
#include <string>
#include <unordered_map>
#include <vector>

#include "Messages_m.h"

using namespace omnetpp;

class Controller;
struct Scenario;

/**
 * Battery-powered WSN node (50 per network). Ten of them are sensing stations
 * (MATLAB ids 4 8 12 18 22 28 32 38 42 48); all 50 can act as cluster head or relay.
 * Implements protocols/RL_Hybrid.m: per-node tabular Q(s,a) with 3^8 = 6561 states and
 * 51 actions (nodes 1..50 and BS), candidate-conditioned states, epsilon-greedy selection,
 * the frozen reward and update rules, and the operational death rules.
 */
class SensorNode : public cSimpleModule
{
  public:
    // ---- state other nodes may read (RL_Hybrid.m reads the global E/alive/load arrays)
    int id() const { return myId; }
    bool isAlive() const { return alive; }
    double energy() const { return E; }
    double loadForState() const { return nodeLoad + loadEWMA; }   // load + forwardingLoadEWMA
    double roundLoad() const { return nodeLoad; }
    bool hasOwnReport() const { return ownReportValid; }
    const ReportRecord& ownReport() const { return own; }
    void clearOwnReport() { ownReportValid = false; }
    int clusterReportCount() const { return (int)clusterBuf.size(); }
    double firstUnavailable() const { return firstUnavailableRound; }
    const std::string& unavailableReason() const { return reason; }
    long qEntries() const { return (long)Q.size(); }
    // ---- called by the controller
    void beginRound();
    void assignReport(const ReportRecord& r) { own = r; ownReportValid = true; }
    void endRoundLoadUpdate();                 // forwardingLoadEWMA = 0.9*EWMA + 0.1*nodeLoad
    bool applyMinimumEnergyRule();            // E < E_elec*k  -> unavailable (end of round)
    void setUnavailable(const char *why);
    void deliverCommand(int command, int round);   // controller step: schedules the command event here
    void setDisplayRole(bool sensing, const std::string& station) { sensingRole = sensing; stationName = station; }   // display only

  protected:
    struct Cand { int target; int state; double q; };          // target: MATLAB id, 51 = BS
    struct Outstanding {
        bool active = false; int type = 0; int target = 0; int state = 0;
        double lq = 0, eTx = 0, d = 0, localMeanLoad = 0; double ctx[6];
        bool explored = false; int nCands = 0; simtime_t decisionTime; int hop = 0;
        std::vector<ReportRecord> reports;                      // copies, for fate accounting
    };

    int myId = 0, n = 50;
    int BS_ID = 51, NUM_ACTIONS = 51;                           // set to n+1 in initialize (scalable action space)
    Controller *ctl = nullptr;
    const Scenario *sc = nullptr;
    double E = 0, E0 = 0;
    bool alive = true;
    double firstUnavailableRound = NAN;
    std::string reason;
    std::vector<long> linkSucc, linkAtt;                        // this node's OWN row, size n+1
    std::unordered_map<long, double> Q;                         // sparse; key (state-1)*NUM_ACTIONS + (action-1), NUM_ACTIONS = n+1
    double nodeLoad = 0, loadEWMA = 0;
    // round-local
    bool ownReportValid = false;
    ReportRecord own;
    std::vector<ReportRecord> clusterBuf;                       // clusterReports(ch)
    std::vector<int> clusterMembers;                            // clusterMemberNodes{ch}
    // multi-hop route state while this node holds the aggregate
    DataFrame *held = nullptr;
    bool heldHasPending = false;                                // previous hop awaits feedback
    int heldPrev = -1;
    Outstanding out;
    struct Pending { bool active = false; int state = 0; int action = 0; double reward = 0; } pending;
    cMessage *ackTimer = nullptr, *processTimer = nullptr;
    simtime_t ackTimeout, tProc;
    double Rbit = 250e3, cLight = 3e8;
    long txFrames = 0, rxFrames = 0, qUpdates = 0;
    double txE = 0, rxE = 0, aggE = 0;
    bool sensingRole = false;                                   // display only
    std::string stationName;                                    // display only

    virtual int numInitStages() const override { return 2; }
    virtual void initialize(int stage) override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void refreshDisplay() const override;
    virtual void finish() override;

    // ---- RL_Hybrid.m helpers
    double qEst(int j) const;                                   // currentLinkEstimate(), own row
    int stateFor(int cand, int hops) const;                     // hybridState()
    double neighborLoadMean(const std::vector<int>& cands) const;
    double cheapestAllowedTx(const std::vector<int>& visited) const;
    std::vector<int> routeCandidates(int reports, const std::vector<int>& visited) const;
    int selectAction(std::vector<Cand>& c, bool& explored);
    double& qref(int state, int action);
    double qval(int state, int action) const;
    void qUpdate(int state, int action, double reward, double nextMax);
    double dist(int target) const;                              // distanceTo()

    // ---- behaviour
    void clusterDecision();
    void startRoute();
    void routeStep();
    void transmit(int type, int target, const Cand& c, bool explored, int nCands, DataFrame *f);
    void onFrame(DataFrame *f);
    void onAck(LinkAck *a);
    void onTimeout();
    void onFeedback(ValueFeedback *fb);
    void finishRoute();                                         // route ended (any outcome) -> Done
    void failHeld(int fate, bool strandOwnAsUnattempted);
    void sendFeedback(double value, bool terminal);
    void loseRecords(const std::vector<ReportRecord>& recs, int fate);
    void spendTx(double e);
    void sendDone();

  public:
    virtual ~SensorNode();
};

#endif
