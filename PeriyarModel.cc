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

void Scenario::generate(int s, int totalNodes, uint32_t extraTopoSeed, int topoSeed, bool independentChannelStream)
{
    // generate_scenario.m: rng(seed,'twister'); X = rand(1,n)*L; Y = rand(1,n)*W; sort by X  (n = 50)
    const bool station = topologyMode == "stationPositions";
    if (!station && topologyMode != "referenceLayout")
        throw std::runtime_error("topologyMode must be referenceLayout or stationPositions");
    if (!station && totalNodes < MATLAB_NODES)
        throw std::runtime_error("referenceLayout needs numNodes >= 50 (use topologyMode stationPositions for fewer)");
    if (station) {
        if (stationNodeIds.empty() || (int)stationNodeIds.size() > totalNodes)
            throw std::runtime_error("stationPositions: numNodes must be >= the number of stationNodeIds (> 0)");
        for (int id : stationNodeIds)
            if (id < 1 || id > MATLAB_NODES) throw std::runtime_error("stationNodeIds must lie in 1..50");
    }
    seed = s;
    topologySeed = topoSeed < 0 ? s : topoSeed;   // MATLAB: the topology uses the run seed
    independentChannel = independentChannelStream;
    const int n0 = MATLAB_NODES;
    MatlabTwister rng((uint32_t)topologySeed);
    std::vector<double> x(n0), y(n0);
    for (int i = 0; i < n0; i++) x[i] = rng.rand() * riverLength;
    for (int i = 0; i < n0; i++) y[i] = rng.rand() * riverWidth;
    std::vector<int> idx(n0);
    std::iota(idx.begin(), idx.end(), 0);
    std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return x[a] < x[b]; });   // MATLAB sort is stable
    X.resize(n0); Y.resize(n0);
    for (int i = 0; i < n0; i++) { X[i] = x[idx[i]]; Y[i] = y[idx[i]]; }
    matlabBlock = n0;
    if (station) {   // V2 'stationPositions': X = X(stationNodeIds); Y = Y(stationNodeIds)
        std::vector<double> xs, ys;
        for (int id : stationNodeIds) { xs.push_back(X[id - 1]); ys.push_back(Y[id - 1]); }
        X = xs; Y = ys;
        matlabBlock = (int)X.size();
    }

    // SCALABILITY: nodes beyond the base layout (stationPositions: the station nodes, V2 = 10; referenceLayout: 50)
    // are drawn uniformly inside the same area from a dedicated MatlabTwister(extraTopoSeed) stream and appended in
    // draw order (base nodes are never moved or renumbered; exact duplicates and the BS position are rejected).
    // Every node is an ordinary sensing + forwarding node; its role comes only from the workload.
    numNodes = totalNodes;
    extraTopologySeed = extraTopoSeed;
    if (numNodes > (int)X.size()) {
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

uint32_t Scenario::channelSeed(int r) const
{
    // MATLAB: rng(seed + r). Run seed s+1 then reuses run s's stream shifted by one round, which is harmless
    // only while the topology changes with the seed. With a fixed topology use the independent mapping
    // 1000000*seed + r: distinct for every (seed, round) with round < 1e6, and disjoint from the topology,
    // agent and added-relay seeds (< 1e6).
    return independentChannel ? (uint32_t)(1000000u * (uint32_t)seed + (uint32_t)r) : (uint32_t)(seed + r);
}

void Scenario::channelForRound(int r, std::vector<unsigned char>& success, std::vector<double> *lqOut) const
{
    // generate_scenario.m, loop body for round r: rng(seed + r,'twister'); per-link lq; rand(n,n+1) < lq
    // Always the ORIGINAL 50-node block (nodes 1..50 + BS), whatever the network size.
    const int n = matlabBlock, m = matlabBlock + 1;   // V2: N = 10 nodes -> rand(10, 11) per round
    MatlabTwister rng(channelSeed(r));
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
    if (lqOut) *lqOut = lq;                 // diagnostics only (same draws, nothing else changes)
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

double Scenario::extraLinkLQ(int r, int i, int j) const
{
    // identical computation to extraLinkSuccess (u1 part only); used for diagnostics, never by routing
    if (i == j) return 0;
    uint64_t h = splitmix64(0x5CA1AB1E00000000ULL ^ (uint64_t)(uint32_t)seed);
    h = splitmix64(h ^ (uint64_t)r);
    h = splitmix64(h ^ (uint64_t)i);
    h = splitmix64(h ^ (uint64_t)j);
    double u1 = unitFromHash(splitmix64(h ^ 1));
    double dx, dy, base;
    if (j == numNodes + 1) { dx = X[i - 1] - bsX; dy = Y[i - 1] - bsY; base = 1.0 - (std::sqrt(dx * dx + dy * dy) / (riverLength * 1.2)); }
    else { dx = X[i - 1] - X[j - 1]; dy = Y[i - 1] - Y[j - 1]; base = 1.0 - (std::sqrt(dx * dx + dy * dy) / (riverLength * 0.8)); }
    return std::max(0.1, std::min(0.95, base + 0.3 * (u1 - 0.5)));
}

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

double Scenario::txEnergyBits(double k, double d) const
{
    // tx_energy.m: free space below d0, multipath at/above d0 (k bits)
    if (d < d0)
        return k * (Eelec + Efs * (d * d));
    return k * (Eelec + Emp * std::pow(d, 4));
}

double Scenario::distNode(int i, int j) const { return std::hypot(X[i] - X[j], Y[i] - Y[j]); }
double Scenario::distBS(int i) const { return std::hypot(X[i] - bsX, Y[i] - bsY); }

void Scenario::placeByProfile(const std::vector<std::string>& profile, uint32_t seed)
{
    // SYNTHETIC layouts in the same L x W area; the nodes 1..10 that replay the real KSPCB stations keep their positions.
    //   water_quality        along the river centreline, |y - W/2| <= W/10 (sondes moored in the channel)
    //   industrial_effluent  five outfall clusters on the near bank: +/-30 m along the bank around the outfall, y <= W/2
    //   air_quality          regular grid over the whole area (area coverage)
    //   soil_monitoring      regular grid over the near-bank half, y <= W/2 (field plots)
    // A grid holds the profile's nodes in id order (cell jitter +/-10 %). All draws: MatlabTwister(seed).
    MatlabTwister rng(seed);
    const double L = riverLength, W = riverWidth;
    std::map<std::string, std::vector<int>> members;
    for (int i = 0; i < numNodes; i++)
        if (!(i < 10 && profile[i] == "water_quality")) members[profile[i]].push_back(i);
    double outfall[5];
    for (int c = 0; c < 5; c++) outfall[c] = (c + 0.5) * L / 5 + (rng.rand() - 0.5) * L / 10;
    for (auto& pm : members) {
        const std::string& p = pm.first;
        const int k = (int)pm.second.size();
        const bool grid = p == "air_quality" || p == "soil_monitoring";
        const double h = p == "soil_monitoring" ? W / 2 : W;
        const int cols = grid ? (int)std::ceil(std::sqrt(k * L / h)) : 1, rows = (k + cols - 1) / cols;
        for (int m = 0; m < k; m++) {
            double x, y;
            if (p == "water_quality") { x = rng.rand() * L; y = W / 2 + (rng.rand() - 0.5) * W / 5; }
            else if (p == "industrial_effluent") { x = outfall[m % 5] + (rng.rand() - 0.5) * 60; y = rng.rand() * W / 2; }
            else if (grid) {
                x = (m % cols + 0.5 + (rng.rand() - 0.5) * 0.2) * L / cols;
                y = (m / cols + 0.5 + (rng.rand() - 0.5) * 0.2) * h / rows;
            }
            else throw std::runtime_error("placement scenario: no layout rule for sensor type " + p);
            X[pm.second[m]] = std::min(L, std::max(0.0, x));
            Y[pm.second[m]] = std::min(W, std::max(0.0, y));
        }
    }
    computePrior();
}

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
//
// Generic, configuration-driven workload. With the default configuration (PeriyarValidation.ned) it
// reproduces load_water_quality_data.m + create_periyar_workload_continuous.m exactly.
// Payload values are application data only: no routing code reads them.

namespace {

struct Row { std::string station, time; std::vector<double> v; int csvLine; };

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

std::string trim(const std::string& s)
{
    size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

std::vector<std::string> splitOn(const std::string& s, char c)
{
    std::vector<std::string> out;
    std::string cur;
    std::stringstream ss(s);
    while (std::getline(ss, cur, c)) { cur = trim(cur); if (!cur.empty()) out.push_back(cur); }
    return out;
}

double parseBound(const std::string& s, bool& exclusive)
{
    std::string t = trim(s);
    exclusive = !t.empty() && (t[0] == '>' || t[0] == '<');
    if (exclusive) t = trim(t.substr(1));
    if (t == "inf" || t == "+inf") return std::numeric_limits<double>::infinity();
    if (t == "-inf") return -std::numeric_limits<double>::infinity();
    double v = parseNum(t);
    require(!std::isnan(v), "bad bound '" + s + "'");
    return v;
}

bool inRange(double v, const PayloadField& f)
{
    if (std::isnan(v)) return false;
    bool lo = f.loExclusive ? v > f.lo : v >= f.lo;
    bool hi = f.hiExclusive ? v < f.hi : v <= f.hi;
    return lo && hi;
}

} // namespace

std::vector<PayloadField> parseDatasetFields(const std::string& spec)
{
    // "column|name|unit|lo|hi; ..."  bounds inclusive; prefix '>' or '<' = exclusive; inf / -inf allowed
    std::vector<PayloadField> out;
    for (auto& e : splitOn(spec, ';')) {
        auto p = splitOn(e, '|');
        require(p.size() == 5, "dataset field '" + e + "' must be column|name|unit|lo|hi");
        PayloadField f;
        f.column = p[0]; f.name = p[1]; f.unit = p[2]; f.origin = "dataset";
        f.lo = parseBound(p[3], f.loExclusive);
        f.hi = parseBound(p[4], f.hiExclusive);
        out.push_back(f);
    }
    return out;
}

std::vector<PayloadField> parseSyntheticFields(const std::string& spec)
{
    // "name|unit|mean|amplitude|noise; ..."
    // value = mean + amplitude*sin(2*pi*(r-1)/period + 2*pi*j/numSyntheticSources) + noise*(2u-1)
    std::vector<PayloadField> out;
    for (auto& e : splitOn(spec, ';')) {
        auto p = splitOn(e, '|');
        require(p.size() == 5, "synthetic field '" + e + "' must be name|unit|mean|amplitude|noise");
        PayloadField f;
        f.name = p[0]; f.unit = p[1]; f.origin = "SYNTHETIC";
        f.mean = parseNum(p[2]); f.amplitude = parseNum(p[3]); f.noise = parseNum(p[4]);
        require(!std::isnan(f.mean) && !std::isnan(f.amplitude) && !std::isnan(f.noise), "bad number in '" + e + "'");
        out.push_back(f);
    }
    return out;
}

std::vector<std::pair<std::string, int>> parseStationMap(const std::string& spec)
{
    // "station label=nodeId; ..."  (order = source order in the cluster phase)
    std::vector<std::pair<std::string, int>> out;
    for (auto& e : splitOn(spec, ';')) {
        size_t k = e.rfind('=');
        require(k != std::string::npos, "station map entry '" + e + "' must be label=nodeId");
        double id = parseNum(trim(e.substr(k + 1)));
        require(!std::isnan(id) && id >= 1, "bad node id in '" + e + "'");
        out.push_back({trim(e.substr(0, k)), (int)id});
    }
    return out;
}

std::vector<int> parseIntList(const std::string& spec)
{
    // "4, 8, 20-25"
    std::vector<int> out;
    for (auto& e : splitOn(spec, ',')) {
        auto r = splitOn(e, '-');
        require(!r.empty(), "bad node list entry '" + e + "'");
        double a = parseNum(r[0]), b = r.size() > 1 ? parseNum(r[1]) : a;
        require(!std::isnan(a) && !std::isnan(b) && a >= 1 && b >= a, "bad node list entry '" + e + "'");
        for (int i = (int)a; i <= (int)b; i++) out.push_back(i);
    }
    return out;
}

void Workload::build(const WorkloadConfig& cfg, int numRounds, int numNodes)
{
    const bool useDataset = cfg.mode == "dataset" || cfg.mode == "mixed";
    const bool useSynthetic = cfg.mode == "synthetic" || cfg.mode == "mixed";
    require(useDataset || useSynthetic, "workloadMode must be dataset, synthetic or mixed (got '" + cfg.mode + "')");
    require(cfg.reportInterval >= 1, "reportInterval must be >= 1");
    const int schedRounds = cfg.scheduleRounds < 0 ? numRounds : cfg.scheduleRounds;
    require(schedRounds >= numRounds, "scheduleRounds must be >= the simulated workload rounds");
    require(cfg.invalidRowPolicy == "drop" || cfg.invalidRowPolicy == "keepNaN", "invalidRowPolicy must be drop or keepNaN");
    require(cfg.holdPolicy == "sampleAndHold" || cfg.holdPolicy == "freshOnly", "holdPolicy must be sampleAndHold or freshOnly");

    // ---- payload fields: dataset fields first, then synthetic fields not already present (by name)
    fields.clear();
    if (useDataset) fields = cfg.datasetFields;
    std::vector<int> synthIndex;
    if (useSynthetic)
        for (auto& sf : cfg.syntheticFields) {
            int idx = -1;
            for (size_t i = 0; i < fields.size(); i++) if (fields[i].name == sf.name) idx = (int)i;
            if (idx < 0) { fields.push_back(sf); idx = (int)fields.size() - 1; }
            synthIndex.push_back(idx);
        }
    require(!fields.empty() && (int)fields.size() <= MAX_PAYLOAD_FIELDS,
            "1.." + std::to_string(MAX_PAYLOAD_FIELDS) + " payload fields required");
    const size_t nf = fields.size();
    const double NaN = std::numeric_limits<double>::quiet_NaN();

    // ---- sources: dataset stations (station map order), then synthetic sources
    stationNames.clear(); sensingNodes.clear();
    if (useDataset)
        for (auto& sm : cfg.stationMap) { stationNames.push_back(sm.first); sensingNodes.push_back(sm.second); }
    const int numDatasetSources = (int)sensingNodes.size();
    std::vector<int> obsOf(numDatasetSources);       // source -> station stream it reports
    std::iota(obsOf.begin(), obsOf.end(), 0);
    if (useDataset)
        for (auto& rp : cfg.replay) {
            require(rp.second >= 0 && rp.second < numDatasetSources, "replay station index out of range");
            stationNames.push_back("REPLAY-n" + std::to_string(rp.first) + ":" + cfg.stationMap[rp.second].first);
            sensingNodes.push_back(rp.first);
            obsOf.push_back(rp.second);
        }
    const int numDataSources = (int)sensingNodes.size();   // real stations + replay sources
    if (useSynthetic)
        for (int nd : cfg.syntheticSources) { stationNames.push_back("SYNTHETIC-n" + std::to_string(nd)); sensingNodes.push_back(nd); }
    require(!sensingNodes.empty(), "no report sources configured");
    std::set<int> seen;
    for (int nd : sensingNodes) {
        require(nd >= 1 && nd <= numNodes, "source node " + std::to_string(nd) + " outside 1.." + std::to_string(numNodes));
        require(seen.insert(nd).second, "node " + std::to_string(nd) + " is configured as a source twice");
    }

    // ---- dataset: read, keep NaN, stable sort by (time, station)   [load_water_quality_data.m]
    rawObservations = validObservations = uniqueDates = 0;
    rEvents.clear();
    struct Obs { std::string time; int milestone; std::vector<double> v; };
    std::vector<std::vector<Obs>> stationObs(numDatasetSources);
    if (useDataset) {
        std::ifstream in(cfg.datasetPath);
        require((bool)in, "cannot open " + cfg.datasetPath);
        std::string line;
        std::getline(in, line);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto header = splitCsv(line);
        auto colOf = [&](const std::string& name) {
            for (size_t i = 0; i < header.size(); i++) if (trim(header[i]) == name) return (int)i;
            require(false, "column '" + name + "' not in header: " + line);
            return -1;
        };
        int cTime = colOf(cfg.timeColumn), cStation = colOf(cfg.stationColumn);
        std::vector<int> cField;
        for (auto& f : cfg.datasetFields) cField.push_back(colOf(f.column));
        std::vector<Row> rows;
        int ln = 1;
        while (std::getline(in, line)) {
            ln++;
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;
            auto f = splitCsv(line);
            require(f.size() == header.size(), "line " + std::to_string(ln) + " does not have " + std::to_string(header.size()) + " fields");
            Row r{f[cStation], f[cTime], {}, ln};
            for (int c : cField) r.v.push_back(parseNum(f[c]));
            rows.push_back(r);
        }
        std::stable_sort(rows.begin(), rows.end(), [](const Row& a, const Row& b) {
            if (a.time != b.time) return a.time < b.time;     // ISO timestamps: lexical == chronological
            return a.station < b.station;
        });
        rawObservations = (int)rows.size();
        require(cfg.expectedRawRows < 0 || rawObservations == cfg.expectedRawRows,
                "expected " + std::to_string(cfg.expectedRawRows) + " raw observations, got " + std::to_string(rawObservations));

        // validity filter [create_periyar_workload_continuous.m]. drop: every field present and in range.
        // keepNaN: invalid fields become NaN; the row is kept if at least one field is valid.
        std::vector<Row> clean;
        for (auto& r : rows) {
            int ok = 0;
            for (size_t k = 0; k < r.v.size(); k++) {
                if (inRange(r.v[k], cfg.datasetFields[k])) ok++;
                else r.v[k] = NaN;
            }
            if (cfg.invalidRowPolicy == "drop" ? ok == (int)r.v.size() : ok > 0) clean.push_back(r);
        }
        validObservations = (int)clean.size();
        require(cfg.expectedValidRows < 0 || validObservations == cfg.expectedValidRows,
                "expected " + std::to_string(cfg.expectedValidRows) + " valid observations, got " + std::to_string(validObservations));

        std::set<std::string> timeSet;
        for (auto& r : clean) timeSet.insert(r.time);
        uniqueDates = (int)timeSet.size();
        require(cfg.expectedUniqueTimes < 0 || uniqueDates == cfg.expectedUniqueTimes,
                "expected " + std::to_string(cfg.expectedUniqueTimes) + " unique timestamps, got " + std::to_string(uniqueDates));
        require(uniqueDates >= 1, "no valid observations");

        // 'uniform' mapping: r_events = 1 + round((d_idx - 1) * ((numRounds - 1) / (num_dates - 1)))
        std::map<std::string, int> timeToRound;
        int k = 0;
        for (auto& d : timeSet) {
            int rr = uniqueDates == 1 ? 1 : 1 + (int)std::round(k * ((double)(schedRounds - 1) / (double)(uniqueDates - 1)));
            rEvents.push_back(rr);
            timeToRound[d] = rr;
            k++;
        }
        require(rEvents.front() == 1 && (uniqueDates == 1 || rEvents.back() == schedRounds), "milestones must span 1..scheduleRounds");
        require(std::set<int>(rEvents.begin(), rEvents.end()).size() == rEvents.size(),
                "milestones not unique (more unique timestamps than rounds)");

        for (int s = 0; s < numDatasetSources; s++) {
            for (auto& r : clean)
                if (r.station == stationNames[s])
                    stationObs[s].push_back({r.time, timeToRound[r.time], r.v});
            std::stable_sort(stationObs[s].begin(), stationObs[s].end(),
                             [](const Obs& a, const Obs& b) { return a.time < b.time; });
        }
    }

    // ---- schedule: every source has one slot in each due round (round 1, 1 + interval, ...)
    MatlabTwister srng(cfg.syntheticSeed);
    const int numSynth = (int)cfg.syntheticSources.size();
    totalScheduled = 0;
    scheduledPerRound.assign(numRounds, 0);
    reports.clear();
    roundObs.assign(numRounds, {});
    for (int r = 1; r <= numRounds; r++) {
        if ((r - 1) % cfg.reportInterval != 0) continue;
        for (int s = 0; s < (int)sensingNodes.size(); s++) {
            scheduledPerRound[r - 1]++;
            totalScheduled++;
            WorkloadReport w{(int)reports.size() + 1, r, sensingNodes[s], stationNames[s], "", std::vector<double>(nf, NaN)};
            if (s < numDataSources) {
                // causal sample-and-hold (LOCF, no report before the first observation) or fresh samples only;
                // a replay source reports exactly what its station stream reports in this round
                const std::vector<Obs>& so = stationObs[obsOf[s]];
                int active = -1;
                for (int q = 0; q < (int)so.size(); q++) {
                    int m = so[q].milestone;
                    if (cfg.holdPolicy == "sampleAndHold" ? m <= r : m == r) active = q;
                }
                if (active < 0) continue;                    // scheduled slot without data
                const Obs& o = so[active];
                w.date = o.time;
                for (size_t k = 0; k < o.v.size(); k++) w.values[k] = o.v[k];
            }
            else {
                // SYNTHETIC placeholder sample: deterministic, labelled, never presented as a measurement
                int j = s - numDataSources;
                w.date = "synthetic-r" + std::to_string(r);
                for (size_t k = 0; k < cfg.syntheticFields.size(); k++) {
                    const PayloadField& f = cfg.syntheticFields[k];
                    double phase = 2 * 3.14159265358979323846 * j / std::max(1, numSynth);
                    double u = srng.rand();
                    w.values[synthIndex[k]] = f.mean + f.noise * (2 * u - 1)
                        + f.amplitude * std::sin(2 * 3.14159265358979323846 * (r - 1) / std::max(1, cfg.syntheticPeriodRounds) + phase);
                }
            }
            roundObs[r - 1].push_back((int)reports.size());
            reports.push_back(w);
        }
    }
    totalAvailable = (int)reports.size();
    totalUnavailable = totalScheduled - totalAvailable;
}

void Workload::buildScenario(const std::string& path, const std::string& mode, int numRounds, int numNodes,
                             const std::string& frameBits)
{
    require(mode == "m1" || mode == "m2", "scenarioMode must be m1 or m2 (got '" + mode + "')");
    std::map<std::string, int> bitsOf;
    const bool bitsFromData = frameBits == "dataset";   // each report's own m2_frame_bits (only its present fields)
    if (!frameBits.empty() && !bitsFromData)
        for (auto& e : parseStationMap(frameBits)) bitsOf[e.first] = e.second;
    const std::string reportCol = mode + "_report";
    auto readHeader = [&](std::ifstream& in, const std::string& p) {
        require((bool)in, "cannot open " + p);
        std::string line;
        std::getline(in, line);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        return splitCsv(line);
    };
    auto col = [&](const std::vector<std::string>& h, const std::string& name, const std::string& p) {
        for (size_t i = 0; i < h.size(); i++) if (h[i] == name) return (int)i;
        require(false, "column '" + name + "' not in " + p);
        return -1;
    };
    // node -> dataset file: one observations.csv for every node, or a mixed node map
    std::vector<std::string> fileOf(numNodes, path);
    {
        std::ifstream in(path);
        auto h = readHeader(in, path);
        if (std::find(h.begin(), h.end(), "source_dataset") != h.end()) {
            std::string dir = path.substr(0, path.find_last_of("/\\") + 1) + "../";
            int cN = col(h, "node_id", path), cD = col(h, "source_dataset", path), cS = col(h, "source_node_id", path);
            std::vector<bool> seen(numNodes, false);
            std::string line;
            while (std::getline(in, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                if (line.empty()) continue;
                auto f = splitCsv(line);
                int nd = std::stoi(f[cN]);
                if (nd < 1 || nd > numNodes) continue;
                require(std::stoi(f[cS]) == nd, "node map: node " + f[cN] + " must read its own node_id");
                fileOf[nd - 1] = dir + f[cD];
                seen[nd - 1] = true;
            }
            require(std::count(seen.begin(), seen.end(), true) == numNodes, "node map does not cover nodes 1..N");
        }
    }
    struct Cell { bool present = false, report = false; int bits = 0, payloadBits = 0; std::string station, time; std::vector<double> v; };
    std::vector<Cell> cell((size_t)numNodes * numRounds);
    nodeProfile.assign(numNodes, "");
    sensingmJ.assign((size_t)numNodes * numRounds, 0.0);
    std::vector<std::string> names;            // value columns of the first file (payload layout)
    bool sameLayout = true;
    size_t maxValues = 0;
    rawObservations = 0;
    for (const std::string& file : std::set<std::string>(fileOf.begin(), fileOf.end())) {
        std::ifstream in(file);
        auto h = readHeader(in, file);
        int cN = col(h, "node_id", file), cR = col(h, "round", file), cT = col(h, "sensor_type", file);
        int cSt = col(h, "source_station", file), cE = col(h, "env_time", file), cRep = col(h, reportCol, file);
        int cMJ = col(h, "m2_sensing_mJ", file), cTrig = col(h, "m2_trigger", file);
        int cFB = bitsFromData ? col(h, "m2_frame_bits", file) : -1;
        int cPB = std::find(h.begin(), h.end(), "m2_payload_bytes") != h.end() ? col(h, "m2_payload_bytes", file) : -1;
        int v0 = col(h, "is_synthetic", file) + 1, v1 = col(h, "quality_flag", file);   // value columns lie between
        require(v1 > v0 && v1 - v0 <= MAX_PAYLOAD_FIELDS, "bad value columns in " + file);
        std::vector<std::string> nm(h.begin() + v0, h.begin() + v1);
        if (names.empty()) names = nm; else if (nm != names) sameLayout = false;
        maxValues = std::max(maxValues, nm.size());
        std::string line;
        while (std::getline(in, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;
            auto f = splitCsv(line);
            require(f.size() == h.size(), file + ": row with " + std::to_string(f.size()) + " fields");
            int nd = std::stoi(f[cN]), r = std::stoi(f[cR]);
            if (nd < 1 || nd > numNodes || r < 1 || r > numRounds || fileOf[nd - 1] != file) continue;
            Cell& c = cell[(size_t)(nd - 1) * numRounds + (r - 1)];
            require(!c.present, file + ": node " + f[cN] + " round " + f[cR] + " twice");
            c.present = true;
            c.report = f[cRep] == "1";
            if (cPB >= 0) c.payloadBits = 8 * std::stoi(f[cPB]);
            if (bitsFromData) {
                c.bits = std::stoi(f[cFB]);
                require(!c.report || c.bits > 0, file + ": node " + f[cN] + " round " + f[cR] + " reports without frame bits");
            }
            else if (!bitsOf.empty()) {                // profile frame; soil chemistry rounds carry the larger frame
                std::string key = f[cT] + (f[cTrig].find("+chem") != std::string::npos ? "+chem" : "");
                require(bitsOf.count(key) > 0, "scenarioFrameBits has no entry for '" + key + "'");
                c.bits = bitsOf[key];
            }
            c.station = f[cT] + ":" + f[cSt];
            c.time = f[cE];
            for (int k = v0; k < v1; k++) c.v.push_back(parseNum(f[k]));
            nodeProfile[nd - 1] = f[cT];
            sensingmJ[(size_t)(nd - 1) * numRounds + (r - 1)] = parseNum(f[cMJ]);
            rawObservations++;
        }
    }
    require(rawObservations == numNodes * numRounds, "dataset does not cover every node and round");
    fields.clear();
    for (size_t k = 0; k < maxValues; k++) {
        PayloadField pf;
        pf.name = sameLayout ? names[k] : "value" + std::to_string(k + 1);   // mixed: each profile keeps its own order
        pf.unit = sameLayout ? "see metadata.json" : "per profile (sensor_profiles.json)";
        pf.origin = "scenario";
        pf.column = pf.name;
        fields.push_back(pf);
    }
    stationNames.clear(); sensingNodes.clear(); rEvents.clear();
    for (int nd = 1; nd <= numNodes; nd++) {        // same source order as V2_200Node: stations 1..10, then 11..N
        sensingNodes.push_back(nd);
        stationNames.push_back(cell[(size_t)(nd - 1) * numRounds].station);
    }
    uniqueDates = 0;
    totalScheduled = 0;
    scheduledPerRound.assign(numRounds, 0);
    reports.clear();
    roundObs.assign(numRounds, {});
    for (int r = 1; r <= numRounds; r++)
        for (int nd = 1; nd <= numNodes; nd++) {
            const Cell& c = cell[(size_t)(nd - 1) * numRounds + (r - 1)];
            if (mode == "m1" || c.report) { scheduledPerRound[r - 1]++; totalScheduled++; }
            if (!c.report) continue;
            WorkloadReport w{(int)reports.size() + 1, r, nd, c.station, c.time, c.v, c.bits, c.payloadBits};
            w.values.resize(maxValues, std::numeric_limits<double>::quiet_NaN());
            roundObs[r - 1].push_back((int)reports.size());
            reports.push_back(w);
        }
    validObservations = totalAvailable = (int)reports.size();
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
