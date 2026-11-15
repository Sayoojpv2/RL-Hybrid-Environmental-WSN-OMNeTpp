#include "PeriyarModel.h"
#include "MatlabRng.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>

// ---------------------------------------------------------------- Scenario

void Scenario::generate(int s, int totalNodes, uint32_t extraTopoSeed)
{
    // generate_scenario.m: rng(seed,'twister'); X = rand(1,n)*L; Y = rand(1,n)*W; sort by X  (n = 50)
    if (totalNodes < MATLAB_NODES) throw std::runtime_error("numNodes must be >= 50 (the MATLAB topology)");
    seed = s;
    const int n0 = MATLAB_NODES;
    MatlabTwister rng((uint32_t)s);
    std::vector<double> x(n0), y(n0);
    for (int i = 0; i < n0; i++) x[i] = rng.rand() * riverLength;
    for (int i = 0; i < n0; i++) y[i] = rng.rand() * riverWidth;
    std::vector<int> idx(n0);
    std::iota(idx.begin(), idx.end(), 0);
    std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return x[a] < x[b]; });   // MATLAB sort is stable
    X.resize(n0); Y.resize(n0);
    for (int i = 0; i < n0; i++) { X[i] = x[idx[i]]; Y[i] = y[idx[i]]; }

    // SCALABILITY EXTENSION: relays 51..N, uniform in the same 600 x 50 m area, appended in draw order
    // (ids are never re-sorted, so nodes 1..50 and the station mapping are untouched).
    numNodes = totalNodes;
    extraTopologySeed = extraTopoSeed;
    if (numNodes > n0) {
        MatlabTwister trng(extraTopoSeed);
        while ((int)X.size() < numNodes) {
            double xn = trng.rand() * riverLength, yn = trng.rand() * riverWidth;
            bool dup = (xn == bsX && yn == bsY);
            for (size_t k = 0; k < X.size() && !dup; k++) dup = (X[k] == xn && Y[k] == yn);
            if (dup) continue;                                   // reject exact duplicates (never observed)
            X.push_back(xn);
            Y.push_back(yn);
        }
    }
    d0 = std::sqrt(Efs / Emp);
    computePrior();
}

void Scenario::channelForRound(int r, std::vector<unsigned char>& success) const
{
    // generate_scenario.m, loop body for round r: rng(seed + r,'twister'); per-link lq; rand(n,n+1) < lq
    // Always the ORIGINAL 50-node block (nodes 1..50 + BS), whatever the network size.
    const int n = MATLAB_NODES, m = MATLAB_NODES + 1;
    MatlabTwister rng((uint32_t)(seed + r));
    std::vector<double> lq(n * m, 0.0);   // column-major like MATLAB: lq[i + j*n]
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            if (i != j) {
                double dx = X[i] - X[j], dy = Y[i] - Y[j];
                double d = std::sqrt(dx * dx + dy * dy);
                double base_lq = 1.0 - (d / (riverLength * 0.8));
                double noise = 0.3 * (rng.rand() - 0.5);
                lq[i + j * n] = std::max(0.1, std::min(0.95, base_lq + noise));
            }
        }
        double dx = X[i] - bsX, dy = Y[i] - bsY;
        double d_bs = std::sqrt(dx * dx + dy * dy);
        double base_lq_bs = 1.0 - (d_bs / (riverLength * 1.2));
        double noise_bs = 0.3 * (rng.rand() - 0.5);
        lq[i + n * n] = std::max(0.1, std::min(0.95, base_lq_bs + noise_bs));
    }
    success.assign(n * m, 0);
    for (int j = 0; j < m; j++)            // rand(n, n+1) fills column-major
        for (int i = 0; i < n; i++)
            success[i + j * n] = rng.rand() < lq[i + j * n] ? 1 : 0;
}


// ---- SCALABILITY EXTENSION: channel outcomes for links that involve an added relay (id > 50)
static uint64_t splitmix64(uint64_t x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

static double unitFromHash(uint64_t h) { return (h >> 11) * (1.0 / 9007199254740992.0); }   // [0,1)

bool Scenario::extraLinkSuccess(int r, int i, int j) const
{
    // Same clipped law as generate_scenario.m (lq = clip(base + 0.3*(u1 - 0.5), 0.1, 0.95); success = u2 < lq),
    // but u1, u2 come from a counter-based hash of (seed, round, i, j): reproducible, independent of the
    // order in which links are used, O(1) per transmitted frame, and only evaluated when the frame arrives.
    if (i == j) return false;
    uint64_t h = splitmix64(0x5CA1AB1E00000000ULL ^ (uint64_t)(uint32_t)seed);
    h = splitmix64(h ^ (uint64_t)r);
    h = splitmix64(h ^ (uint64_t)i);
    h = splitmix64(h ^ (uint64_t)j);
    double u1 = unitFromHash(splitmix64(h ^ 1)), u2 = unitFromHash(splitmix64(h ^ 2));
    double base;
    if (j == numNodes + 1) {
        double dx = X[i - 1] - bsX, dy = Y[i - 1] - bsY;
        base = 1.0 - (std::sqrt(dx * dx + dy * dy) / (riverLength * 1.2));
    }
    else {
        double dx = X[i - 1] - X[j - 1], dy = Y[i - 1] - Y[j - 1];
        base = 1.0 - (std::sqrt(dx * dx + dy * dy) / (riverLength * 0.8));
    }
    double lq = std::max(0.1, std::min(0.95, base + 0.3 * (u1 - 0.5)));
    return u2 < lq;
}

double Scenario::txEnergy(double d) const
{
    // tx_energy.m: free space below d0, multipath at/above d0
    if (d < d0)
        return packetSize * (Eelec + Efs * (d * d));
    return packetSize * (Eelec + Emp * std::pow(d, 4));
}

double Scenario::distNode(int i, int j) const { return std::hypot(X[i] - X[j], Y[i] - Y[j]); }
double Scenario::distBS(int i) const { return std::hypot(X[i] - bsX, Y[i] - bsY); }

void Scenario::computePrior()
{
    // RL_Hybrid.m distancePriorLQ(): closed-form E[LQ | distance] of the clipped channel law
    const int n = numNodes;
    prior.assign(n * (n + 1), 1.0);
    for (int i = 0; i < n; i++) {
        for (int j = 0; j <= n; j++) {
            if (j == i) continue;
            double d, base;
            if (j == n) { d = std::hypot(X[i] - bsX, Y[i] - bsY); base = 1 - d / (riverLength * 1.2); }
            else        { d = std::hypot(X[i] - X[j], Y[i] - Y[j]); base = 1 - d / (riverLength * 0.8); }
            double lo = 0.10, hi = 0.95, a = base - 0.15, b = base + 0.15, w = b - a;
            double pLo = std::min(1.0, std::max(0.0, (lo - a) / w));
            double pHi = std::min(1.0, std::max(0.0, (b - hi) / w));
            double m0 = std::max(a, lo), m1 = std::min(b, hi);
            double mid = (m1 > m0) ? (m0 + m1) / 2 * (m1 - m0) / w : 0;
            prior[i * (n + 1) + j] = lo * pLo + hi * pHi + mid;
        }
    }
}

// ---------------------------------------------------------------- Workload

namespace {

struct Row { std::string location, date; double temp, ph, cond, tds, dobs; int csvLine; };

double parseNum(const std::string& s)
{
    std::string t = s;
    while (!t.empty() && (t.back() == '\r' || t.back() == ' ')) t.pop_back();
    if (t.empty()) return std::numeric_limits<double>::quiet_NaN();
    try { size_t pos; double v = std::stod(t, &pos); if (pos != t.size()) throw 1; return v; }
    catch (...) { return std::numeric_limits<double>::quiet_NaN(); }
}

std::vector<std::string> splitCsv(const std::string& line)
{
    std::vector<std::string> f;
    std::stringstream ss(line);
    std::string cell;
    while (std::getline(ss, cell, ',')) f.push_back(cell);
    if (!line.empty() && line.back() == ',') f.push_back("");
    return f;
}

void require(bool ok, const std::string& msg) { if (!ok) throw std::runtime_error("Workload: " + msg); }

} // namespace

void Workload::build(const std::string& csvPath, int numRounds)
{
    // ---- load_water_quality_data.m: read, keep NaN, sort by (Date, Location), stable
    std::ifstream in(csvPath);
    require((bool)in, "cannot open " + csvPath);
    std::string line;
    std::getline(in, line);
    if (!line.empty() && line.back() == '\r') line.pop_back();
    require(line == "Location,Date,Temperature,pH,Conductivity,TDS,DO", "unexpected header: " + line);
    std::vector<Row> rows;
    int ln = 1;
    while (std::getline(in, line)) {
        ln++;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        auto f = splitCsv(line);
        require(f.size() == 7, "line " + std::to_string(ln) + " does not have 7 fields");
        rows.push_back({f[0], f[1], parseNum(f[2]), parseNum(f[3]), parseNum(f[4]), parseNum(f[5]), parseNum(f[6]), ln});
    }
    std::stable_sort(rows.begin(), rows.end(), [](const Row& a, const Row& b) {
        if (a.date != b.date) return a.date < b.date;     // yyyy-MM-dd: lexical == chronological
        return a.location < b.location;
    });
    rawObservations = (int)rows.size();
    require(rawObservations == 1273, "expected 1273 raw observations, got " + std::to_string(rawObservations));

    // ---- create_periyar_workload_continuous.m: 4-parameter validity filter
    std::vector<Row> clean;
    for (auto& r : rows) {
        bool t_ok = !std::isnan(r.temp) && r.temp >= 15.0 && r.temp <= 50.0;
        bool ph_ok = !std::isnan(r.ph) && r.ph >= 0.0 && r.ph <= 14.0;
        bool c_ok = !std::isnan(r.cond) && r.cond > 0.0;
        bool tds_ok = !std::isnan(r.tds) && r.tds > 0.0;
        if (t_ok && ph_ok && c_ok && tds_ok) clean.push_back(r);
    }
    validObservations = (int)clean.size();
    require(validObservations == 1251, "expected 1251 valid observations, got " + std::to_string(validObservations));

    stationNames = {"ALUVA - MANAPPURAM", "PURAPILLIKADAVU US", "PURAPILLIKADAVU BUND NAVIGATION",
                    "PURAPILLIKADAVU BUND DS", "PATHALAM BUND U/S", "PATHALAM BUND D/S", "PATHALAM BRIDGE",
                    "PUTHALAM KADAVU", "MANJUMMAL BUND", "VETTUKADAVU"};
    sensingNodes = {4, 8, 12, 18, 22, 28, 32, 38, 42, 48};
    const int numStations = (int)stationNames.size();

    std::set<std::string> dateSet;
    for (auto& r : clean) dateSet.insert(r.date);
    uniqueDates = (int)dateSet.size();
    require(uniqueDates == 212, "expected 212 unique dates, got " + std::to_string(uniqueDates));

    // 'uniform' mapping: r_events = 1 + round((d_idx - 1) * ((numRounds - 1) / (num_dates - 1)))
    rEvents.clear();
    std::map<std::string, int> dateToRound;
    int k = 0;
    for (auto& d : dateSet) {
        int rr = 1 + (int)std::round(k * ((double)(numRounds - 1) / (double)(uniqueDates - 1)));
        rEvents.push_back(rr);
        dateToRound[d] = rr;
        k++;
    }
    require(rEvents.front() == 1 && rEvents.back() == numRounds, "milestones must span 1..numRounds");
    require(std::set<int>(rEvents.begin(), rEvents.end()).size() == rEvents.size(), "milestones not unique");

    // per-station chronological observations (stable sort by date of the clean-table order)
    struct Obs { std::string date; int milestone; double t, ph, c, tds; };
    std::vector<std::vector<Obs>> stationObs(numStations);
    for (int s = 0; s < numStations; s++) {
        for (auto& r : clean)
            if (r.location == stationNames[s])
                stationObs[s].push_back({r.date, dateToRound[r.date], r.temp, r.ph, r.cond, r.tds});
        std::stable_sort(stationObs[s].begin(), stationObs[s].end(),
                         [](const Obs& a, const Obs& b) { return a.date < b.date; });
    }

    // causal sample-and-hold (LOCF); no report before a station's first observation
    totalScheduled = numRounds * numStations;
    reports.clear();
    roundObs.assign(numRounds, {});
    for (int r = 1; r <= numRounds; r++) {
        for (int s = 0; s < numStations; s++) {
            int active = -1;
            for (int q = 0; q < (int)stationObs[s].size(); q++)
                if (stationObs[s][q].milestone <= r) active = q;    // last valid_avail
            if (active < 0) continue;
            const Obs& o = stationObs[s][active];
            WorkloadReport w{(int)reports.size() + 1, r, sensingNodes[s], stationNames[s], o.date, o.t, o.ph, o.c, o.tds};
            roundObs[r - 1].push_back((int)reports.size());
            reports.push_back(w);
        }
    }
    totalAvailable = (int)reports.size();
    totalUnavailable = totalScheduled - totalAvailable;
}

// ---------------------------------------------------------------- RL-Hybrid formulas

namespace rlhybrid {

int ternaryBin(double v, double t1, double t2)
{
    if (v <= t1) return 1;
    if (v <= t2) return 2;
    return 3;
}

int energyBin(double ratio)
{
    if (ratio <= 0.33) return 1;
    if (ratio <= 0.66) return 2;
    return 3;
}

int stateIndex(const StateInputs& s, int b[NUM_FEATURES])
{
    // RL_Hybrid.m hybridState(), lines 640-646
    b[0] = energyBin(s.currentEnergy);
    b[1] = energyBin(s.candidateEnergy);
    b[2] = ternaryBin(s.linkLQ, 0.65, 0.80);
    b[3] = ternaryBin(s.distance / std::max(s.d0, std::numeric_limits<double>::epsilon()), 1, 2);
    b[4] = ternaryBin(s.progress, 0.05, 0.25);
    b[5] = ternaryBin(s.pastReliability, 0.50, 0.75);
    b[6] = ternaryBin(s.candidateLoad, 1, 4);
    b[7] = ternaryBin(std::max(0, MAX_HOPS - s.hops), 4, 10);
    int state = 1, p = 1;
    for (int k = NUM_FEATURES - 1; k >= 0; k--) { state += (b[k] - 1) * p; p *= 3; }
    return state;
}

double transitionReward(bool success, bool terminal, double qEst, double energySpent, double relayEnergy,
                        double distance, double riverLength, double load, double meanLoad)
{
    // RL_Hybrid.m transitionReward(), lines 699-714 (operation order preserved)
    double energyTerm = std::min(1.0, std::max(0.0, energySpent / 1e-3));
    if (!success)
        return -1.0 - 0.10 * energyTerm;
    if (terminal)
        return 2.0 + 0.15 * std::min(1.0, std::max(0.0, qEst)) - 0.10 * energyTerm - 0.05;
    double progress = std::min(1.0, std::max(-1.0, distance / std::max(1.0, riverLength)));
    double loadRatio = std::min(1.0, std::max(0.0, load / std::max(1.0, meanLoad)));
    return 0.15 * std::min(1.0, std::max(0.0, qEst)) + 0.15 * progress
         + 0.10 * std::min(1.0, std::max(0.0, relayEnergy)) + 0.10 * (1 - loadRatio)
         - 0.10 * energyTerm - 0.05;
}

} // namespace rlhybrid
