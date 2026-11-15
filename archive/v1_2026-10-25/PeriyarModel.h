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
    static constexpr int MATLAB_NODES = 50;   // nodes 1..50 = the frozen MATLAB topology (never renumbered)
    int numNodes = 50;                        // total battery nodes N (>= 50); relays 51..N are added
    uint32_t extraTopologySeed = 0;           // stream for the added relays' coordinates
    double riverLength = 600, riverWidth = 50;
    double bsX = 600, bsY = 25;
    double initialEnergy = 2.0;      // J
    int packetSize = 4000;           // bits
    int numRounds = 1000;
    double Eelec = 50e-9, Efs = 10e-12, Emp = 0.0013e-12, Eda = 5e-9;
    double d0 = 0;
    int seed = 0;
    std::vector<double> X, Y;        // node coordinates (m), sorted by X as in MATLAB
    std::vector<double> prior;       // n x (n+1) geometry prior p0, row-major [i*(n+1)+j]

    // generate_scenario.m topology for nodes 1..50 (exactly as MATLAB); if totalNodes > 50, relays
    // 51..N are appended from a dedicated MatlabTwister(extraTopoSeed) stream (no re-sorting).
    void generate(int seed, int totalNodes = 50, uint32_t extraTopoSeed = 0);
    // success_history(:,:,r) of the ORIGINAL 50 x 51 block (nodes 1..50 + BS), column-major,
    // bit-exact MATLAB stream rng(seed + r). Unchanged for every network size.
    void channelForRound(int round, std::vector<unsigned char>& success) const;
    // Outcome of a link that involves an ADDED relay (i or j > 50; ids 1-based, BS = N+1): same
    // clipped distance law, uniform draws from a counter-based hash of (seed, round, i, j).
    bool extraLinkSuccess(int round, int i, int j) const;
    double txEnergy(double d) const;                           // tx_energy(k,d,env) for one packet
    double rxEnergy() const { return packetSize * Eelec; }     // rx_energy(k,env)
    double distNode(int i, int j) const;                       // hypot as in RL_Hybrid.m
    double distBS(int i) const;
    double priorLQ(int i, int j) const { return prior[i * (numNodes + 1) + j]; }

  private:
    void computePrior();                                       // distancePriorLQ(env)
};

struct WorkloadReport
{
    int index;            // 1-based report index (MATLAB obs index)
    int round;            // 1..1000
    int sourceNode;       // MATLAB node id (1-based)
    std::string station, date;
    double temperature, pH, conductivity, TDS;
};

struct Workload
{
    int rawObservations = 0, validObservations = 0, uniqueDates = 0;
    int totalScheduled = 0, totalAvailable = 0, totalUnavailable = 0;
    std::vector<std::string> stationNames;     // MATLAB station order
    std::vector<int> sensingNodes;             // [4 8 12 18 22 28 32 38 42 48]
    std::vector<int> rEvents;                  // date -> round milestones (212 entries)
    std::vector<WorkloadReport> reports;       // in MATLAB obs order
    std::vector<std::vector<int>> roundObs;    // per round (0-based round index): report indices into `reports`

    void build(const std::string& csvPath, int numRounds);   // throws std::runtime_error on any mismatch
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
