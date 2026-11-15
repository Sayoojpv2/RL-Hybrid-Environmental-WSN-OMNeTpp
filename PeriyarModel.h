//
// PeriyarModel.h - line-by-line ports of the frozen MATLAB model components.
//
//   Scenario        <- simulation/generate_scenario.m           (topology, radio constants, channel)
//   txEnergy/rxEnergy <- simulation/tx_energy.m, rx_energy.m
//   priorLQ         <- protocols/RL_Hybrid.m  distancePriorLQ()  (lines 738-758)
//   Workload        <- simulation/load_water_quality_data.m + create_periyar_workload_continuous.m
//   hybridState, transitionReward, ternaryBin, energyBin <- protocols/RL_Hybrid.m (lines 621-714)
//
// MATLAB indices are 1-based; here node i (MATLAB) is index i-1, and the base
// station (MATLAB index n+1 = 51) is index n = 50.
//
#ifndef __PERIYAR_MODEL_H
#define __PERIYAR_MODEL_H

#include <cstdint>
#include <string>
#include <vector>

struct Scenario
{
    static constexpr int MATLAB_NODES = 50;   // size of the MATLAB reference layout (generate_scenario draws 50 positions)
    int numNodes = 50;                        // total battery nodes N
    // Topology mode (MATLAB V2 generate_scenario.m):
    //  "referenceLayout"  : nodes 1..50 = the seeded 50-node layout; N > 50 appends nodes from extraTopologySeed
    //  "stationPositions" : the nodes at stationNodeIds of the seeded 50-node layout (V2: 10 nodes = 4,8,...,48)
    std::string topologyMode = "referenceLayout";
    std::vector<int> stationNodeIds;
    int matlabBlock = 50;                     // nodes 1..matlabBlock (+BS) use the MATLAB channel stream rng(seed + r)
    bool reportPreservingEnergy = false;      // V2: a route frame carrying m reports is charged as m packets
    bool perReportBits = false;               // scenario study M2F: every report is charged with its own frame bits
    // EXPERIMENTAL routing variants (not in MATLAB; all off by default = the validated algorithm)
    double retryEnergyReserve = 0;            // A: retry only if sender and receiver keep this fraction of E0
    bool qPriorInit = false;                  // B: untried actions start at the prior expected one-step reward
    double energyGuard = 0;                   // C: skip candidates below this fraction of the candidates' mean energy
    // EXPERIMENTAL (not in MATLAB; off by default): link-layer retransmission of a frame that was not decoded
    bool retransmission = false;
    int maxRetransmissions = 0;
    uint32_t extraTopologySeed = 0;           // stream for the added relays' coordinates
    double riverLength = 600, riverWidth = 50;
    double bsX = 600, bsY = 25;
    double initialEnergy = 2.0;      // J
    int packetSize = 4000;           // bits
    int numRounds = 1000;
    double Eelec = 50e-9, Efs = 10e-12, Emp = 0.0013e-12, Eda = 5e-9;
    double d0 = 0;
    int seed = 0;                    // RUN seed: channel streams (and, in Controller, the agent stream)
    int topologySeed = 0;            // seed of the nodes 1..50 layout (= seed in the MATLAB experiment)
    bool independentChannel = false; // false: MATLAB rng(seed + r); true: rng(1000000*seed + r) (no overlap between runs)
    std::vector<double> X, Y;        // node coordinates (m), sorted by X as in MATLAB
    std::vector<double> prior;       // n x (n+1) geometry prior p0, row-major [i*(n+1)+j]

    // generate_scenario.m topology for nodes 1..50 (exactly as MATLAB); if totalNodes > 50, relays
    // 51..N are appended from a dedicated MatlabTwister(extraTopoSeed) stream (no re-sorting).
    // topoSeed < 0 means topoSeed = seed (MATLAB). The defaults reproduce the MATLAB experiment exactly.
    void generate(int seed, int totalNodes = 50, uint32_t extraTopoSeed = 0, int topoSeed = -1,
                  bool independentChannelStream = false);
    uint32_t channelSeed(int round) const;                     // MATLAB: seed + r
    // success_history(:,:,r) of the ORIGINAL 50 x 51 block (nodes 1..50 + BS), column-major,
    // bit-exact MATLAB stream rng(seed + r). Unchanged for every network size.
    void channelForRound(int round, std::vector<unsigned char>& success, std::vector<double> *lqOut = nullptr) const;
    // Outcome of a link that involves an ADDED relay (i or j > 50; ids 1-based, BS = N+1): same
    // clipped distance law, uniform draws from a counter-based hash of (seed, round, i, j).
    bool extraLinkSuccess(int round, int i, int j) const;
    double extraLinkLQ(int round, int i, int j) const;         // the lq behind extraLinkSuccess (diagnostics)
    double txEnergy(double d) const { return txEnergyBits(packetSize, d); }   // tx_energy(k,d,env), one packet
    double txEnergyBits(double k, double d) const;             // tx_energy(k,d,env) for k bits
    double rxEnergy() const { return packetSize * Eelec; }     // rx_energy(k,env)
    double rxEnergyBits(double k) const { return k * Eelec; }  // rx_energy(k,env) for k bits
    // route-frame energies: V2 report-preserving accounting (m reports = m packets) or one packet per frame
    double routeTxEnergy(double d, int reports) const { return routeTxEnergyBits(d, (double)packetSize * reports); }
    double routeRxEnergy(int reports) const { return routeRxEnergyBits((double)packetSize * reports); }
    // the same for a frame whose reports carry `bits` in total (per-report frame bits)
    double routeTxEnergyBits(double d, double bits) const { return reportPreservingEnergy ? txEnergyBits(bits, d) : txEnergy(d); }
    double routeRxEnergyBits(double bits) const { return reportPreservingEnergy ? rxEnergyBits(bits) : rxEnergy(); }
    double distNode(int i, int j) const;                       // hypot as in RL_Hybrid.m
    double distBS(int i) const;
    double priorLQ(int i, int j) const { return prior[i * (numNodes + 1) + j]; }

    // placement = "scenario": SYNTHETIC profile-specific layouts (profile = sensor_type per node), prior recomputed
    void placeByProfile(const std::vector<std::string>& profile, uint32_t seed);

  private:
    void computePrior();                                       // distancePriorLQ(env)
};

// ---- application payload / workload (configuration-driven; never read by the routing code)
constexpr int MAX_PAYLOAD_FIELDS = 16;

struct PayloadField
{
    std::string name, unit;
    std::string origin;              // "dataset" (real CSV column) or "SYNTHETIC"
    std::string column;              // dataset: CSV column name
    double lo = 0, hi = 0;           // dataset: valid range (missing or outside = invalid)
    bool loExclusive = false, hiExclusive = false;
    double mean = 0, amplitude = 0, noise = 0;   // synthetic generator parameters
};

struct WorkloadConfig
{
    std::string mode = "dataset";    // "dataset" | "synthetic" | "mixed"
    // dataset sources
    std::string datasetPath, timeColumn, stationColumn;
    std::vector<PayloadField> datasetFields;
    std::vector<std::pair<std::string, int>> stationMap;   // station label -> node id (order = source order)
    std::string invalidRowPolicy = "drop";                  // "drop" (MATLAB) | "keepNaN"
    std::string holdPolicy = "sampleAndHold";               // "sampleAndHold" (MATLAB, causal LOCF) | "freshOnly"
    int expectedRawRows = -1, expectedValidRows = -1, expectedUniqueTimes = -1;   // regression guards (-1 = off)
    // synthetic sources (labelled SYNTHETIC-n<id>; values are generated, not measured)
    std::vector<int> syntheticSources;
    // virtual dataset-REPLAY sources: (node id, index into stationMap). The node reports the same measured values,
    // on the same sampling dates, as that real station stream; labelled REPLAY-n<id>:<station> (not a real station)
    std::vector<std::pair<int, int>> replay;
    std::vector<PayloadField> syntheticFields;
    uint32_t syntheticSeed = 1;
    int syntheticPeriodRounds = 100;
    // schedule: every source has a slot in rounds 1, 1 + reportInterval, ...
    int reportInterval = 1;
    // length of the timestamp -> round schedule (V2: 1000) when only rounds 1..numRounds are simulated
    // (V2: 500); -1 = numRounds. Rounds 1..numRounds then report exactly what the full schedule reports.
    int scheduleRounds = -1;
};

std::vector<PayloadField> parseDatasetFields(const std::string& spec);    // "column|name|unit|lo|hi; ..."
std::vector<PayloadField> parseSyntheticFields(const std::string& spec);  // "name|unit|mean|amplitude|noise; ..."
std::vector<std::pair<std::string, int>> parseStationMap(const std::string& spec);   // "label=node; ..."
std::vector<int> parseIntList(const std::string& spec);                   // "4, 8, 20-25"

struct WorkloadReport
{
    int index;            // 1-based report index (MATLAB obs index for Periyar)
    int round;            // 1..numRounds
    int sourceNode;       // node id (1-based)
    std::string station, date;
    std::vector<double> values;   // one per Workload::fields entry (NaN = no value)
    int bits = 0;                 // scenario study: radio-frame bits of this report (0 = Scenario::packetSize)
    int payloadBits = 0;          // scenario study: application payload bits (m2_payload_bytes x 8)
};

struct Workload
{
    int rawObservations = 0, validObservations = 0, uniqueDates = 0;
    int totalScheduled = 0, totalAvailable = 0, totalUnavailable = 0;
    std::vector<PayloadField> fields;          // payload layout of every report
    std::vector<std::string> stationNames;     // source labels, in source order
    std::vector<int> sensingNodes;             // Periyar: [4 8 12 18 22 28 32 38 42 48]
    std::vector<int> rEvents;                  // timestamp -> round milestones (Periyar: 212 entries)
    std::vector<int> scheduledPerRound;        // scheduled slots per round (0-based round index)
    std::vector<WorkloadReport> reports;       // in report-index order
    std::vector<std::vector<int>> roundObs;    // per round (0-based round index): report indices into `reports`

    void build(const WorkloadConfig& cfg, int numRounds, int numNodes);   // throws std::runtime_error

    // ---- scenario-study datasets (data/scenarios/*; used only when Controller.scenarioDataset is set)
    // path: <name>/observations.csv, or a mixed node_map.csv (column source_dataset). Every node 1..numNodes is a
    // source. mode "m1": every node has a slot every round, a report where m1_report = 1 (= the V2_200Node slots);
    // "m2": a slot only where the profile schedule emits a report (m2_report = 1). Payload = the value columns.
    std::vector<std::string> nodeProfile;      // sensor_type per node (index = node id - 1)
    std::vector<double> sensingmJ;             // m2_sensing_mJ [(node-1) * numRounds + round-1]; separate ledger only
    // frameBits "type=bits; type+chem=bits; ...": per-report frame bits by sensor_type (+chem when m2_trigger has +chem)
    void buildScenario(const std::string& path, const std::string& mode, int numRounds, int numNodes,
                       const std::string& frameBits = "");
};

namespace rlhybrid {

constexpr int NUM_FEATURES = 8;
constexpr int NUM_STATES = 6561;   // 3^8
constexpr int MAX_HOPS = 15;

int ternaryBin(double v, double t1, double t2);   // returns 1..3 as MATLAB
int energyBin(double ratio);                      // returns 1..3

// All inputs are the values MATLAB's hybridState() reads; returns state 1..6561.
struct StateInputs {
    double currentEnergy, candidateEnergy, linkLQ, distance, d0, progress, pastReliability, candidateLoad;
    int hops;
};
int stateIndex(const StateInputs& s, int bins[NUM_FEATURES]);

double transitionReward(bool success, bool terminal, double qEst, double energySpent, double relayEnergy,
                        double distance, double riverLength, double load, double meanLoad);

} // namespace rlhybrid

#endif
