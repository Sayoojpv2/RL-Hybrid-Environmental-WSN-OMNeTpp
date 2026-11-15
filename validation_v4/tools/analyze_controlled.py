#!/usr/bin/env python3
"""v2 analysis of the controlled design (results_controlled/) and the placement runs (results_placement/).

Usage: python3 tools/analyze_controlled.py      (run from the project folder)
Writes reports_v2/02_controlled_results.md, 03_first_unavailability.md, 04_routing_diagnostics.md,
05_placement_sensitivity.md and the per-seed CSV files in reports_v2/data/.
Statistics: mean ± sample sd (n - 1) over the five run seeds 42-46. Nothing here changes any simulation.
"""
import csv, glob, math, os, statistics as st, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
SEEDS = [42, 43, 44, 45, 46]
SIZES = [50, 100, 250, 500]
STATIONS = {4, 8, 12, 18, 22, 28, 32, 38, 42, 48}
BS = (600.0, 25.0)
OUT = "reports_v2"
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def scalars(sca):
    vals = {}
    for line in open(sca):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar":
            vals[(p[1], p[2])] = float(p[3])
    return vals


def ms(v, fmt="%.2f"):
    v = [x for x in v if x is not None]
    if not v:
        return "–"
    if len(v) == 1:
        return fmt % v[0]
    return (fmt % st.mean(v)) + " ± " + (fmt % st.stdev(v))


def quant(v, q):
    s = sorted(v)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


perf = {}
for r in rows("logs_v2/performance_v2.csv"):
    perf[(r["config"], int(r["run"]))] = (float(r["wallSeconds"]), float(r["peakWorkingSetMiB"]), int(r["exitCode"]))


def analyse(pre, sca, N):
    """Every per-run quantity used in the reports, from one run's output files."""
    m = rows(pre + "-metrics.csv")[0]
    vals = scalars(sca)
    nodes = rows(pre + "-nodes.csv")
    xy = {int(r["node"]): (float(r["x"]), float(r["y"])) for r in nodes}
    dbs = {k: math.hypot(x - BS[0], y - BS[1]) for k, (x, y) in xy.items()}
    rep = rows(pre + "-reports.csv")
    hops = rows(pre + "-hops.csv")
    dec = rows(pre + "-decisions.csv")
    a = {}
    a["N"] = N
    a["scheduled"] = int(m["scheduled"])
    a["validData"] = int(m["workloadAvailable"])
    a["emitted"] = int(m["sourceAvailable"])
    a["delivered"] = int(m["delivered"])
    a["PDR"] = float(m["PDR"])
    a["delivEmit"] = 100.0 * a["delivered"] / a["emitted"]
    a["sourceUnavailable"] = a["validData"] - a["emitted"]
    a["lossChannel"] = int(m["lossChannel"]); a["lossEnergy"] = int(m["lossEnergy"])
    a["lossNoCand"] = int(m["lossNoCandidate"]); a["lossTTL"] = int(m["lossTTL"]); a["unattempted"] = int(m["unattempted"])
    a["FND"] = int(float(m["FND"]))
    a["finalAlive"] = int(m["finalAlive"])
    a["residualJ"] = float(m["residualJ"]); a["spentJ"] = float(m["spentJ"])
    a["residualPct"] = 100 * a["residualJ"] / (2.0 * N)
    a["energyPerDelivered"] = float(m["energyPerDeliveredJ"])
    a["meanHops"] = float(m["meanHops"])
    a["meanDelayS"] = float(m["meanDelayS"])
    a["qUpdates"] = int(m["qUpdates"]); a["explorations"] = int(m["explorations"])
    dh = [int(r["hops"]) for r in rep if r["fate"] == "delivered"]
    a["hopsMedian"] = st.median(dh); a["hopsP90"] = quant(dh, 0.9); a["hopsMax"] = max(dh)
    a["hopHist"] = Counter(dh)
    # transmissions (each logged transmission = one physical frame attempt)
    a["tx"] = len(hops)
    a["txFailed"] = sum(1 for h in hops if float(h["outcome"]) == 0)
    a["txPerDelivered"] = a["tx"] / a["delivered"]
    a["failedTxPerDelivered"] = a["txFailed"] / a["delivered"]
    a["txSuccessRate"] = 1 - a["txFailed"] / a["tx"]
    lqs = [float(h["trueLQ"]) for h in hops]
    a["lqMean"] = st.mean(lqs); a["lqMedian"] = st.median(lqs); a["lqP10"] = quant(lqs, 0.1)
    a["lqAt095"] = sum(1 for x in lqs if x >= 0.95 - 1e-12) / len(lqs)
    dist = [float(h["distanceM"]) for h in hops]
    a["distMean"] = st.mean(dist); a["distMedian"] = st.median(dist)
    # by hop type: 1 = source -> cluster head, 2 = relay hop, 3 = hop into the BS
    for t, name in [("1", "member"), ("2", "relay"), ("3", "toBS")]:
        hs = [h for h in hops if h["hopType"] == t]
        a[f"n_{name}"] = len(hs)
        a[f"succ_{name}"] = sum(1 for h in hs if float(h["outcome"]) == 1) / len(hs) if hs else float("nan")
        a[f"lq_{name}"] = st.mean(float(h["trueLQ"]) for h in hs) if hs else float("nan")
        a[f"dist_{name}"] = st.mean(float(h["distanceM"]) for h in hs) if hs else float("nan")
    # route transmissions (hop >= 1): progress towards the BS, explored vs exploited
    route = [h for h in hops if h["hopType"] in ("2", "3")]
    def prog(h):
        s, t = int(h["actor"]), int(h["target"])
        return dbs[s] - (0.0 if t == N + 1 else dbs[t])
    for lab, sel in [("expl", "1"), ("expt", "0")]:
        hs = [h for h in route if h["explored"] == sel]
        a[f"share_{lab}"] = len(hs) / len(route)
        a[f"prog_{lab}"] = st.mean(prog(h) for h in hs) if hs else float("nan")
        a[f"lq_{lab}"] = st.mean(float(h["trueLQ"]) for h in hs) if hs else float("nan")
        a[f"succ_{lab}"] = sum(1 for h in hs if float(h["outcome"]) == 1) / len(hs) if hs else float("nan")
    a["progMean"] = st.mean(prog(h) for h in route)
    # report-level loss by hop index (sum of reports carried by failed transmissions)
    lossByHop = Counter(); carriedByHop = Counter()
    for h in hops:
        k = int(h["hop"]); r = int(h["reports"])
        carriedByHop[k] += r
        if float(h["outcome"]) == 0:
            lossByHop[k] += r
    a["lossByHop"] = lossByHop; a["carriedByHop"] = carriedByHop
    a["lossCheck"] = sum(lossByHop.values()) == a["lossChannel"]
    # routes: number of transmissions from the cluster head onward, per route attempt (first route hop = hop 1)
    a["routeTx"] = len(route)
    a["routes"] = sum(1 for h in route if h["hop"] == "1")
    # candidate counts (decisions.csv: every decision, including self-head)
    cl = [int(r["numCandidates"]) for r in dec if r["hopType"] in ("0", "1")]
    rt = [int(r["numCandidates"]) for r in dec if r["hopType"] in ("2", "3")]
    a["candCluster"] = st.mean(cl); a["candRoute"] = st.mean(rt); a["candRouteMedian"] = st.median(rt)
    a["selfHeadShare"] = sum(1 for r in dec if r["hopType"] == "0") / len(cl)
    a["routeDecisions"] = len(rt)
    a["memberToAdded"] = sum(1 for h in hops if h["hopType"] == "1" and h["targetAdded"] == "1") / max(1, a["n_member"])
    # added relays actually selected
    a["txToAdded"] = sum(1 for h in hops if h["targetAdded"] == "1") / len(hops)
    a["addedUsed"] = len({int(h["target"]) for h in hops if h["targetAdded"] == "1"})
    a["addedTotal"] = N - 50
    # energy by role
    eg = defaultdict(float)
    for (mod, k), v in vals.items():
        if k in ("txEnergy", "rxEnergy", "aggregationEnergy") and (".n" in mod or ".relay[" in mod):
            if ".relay[" in mod:
                role = "added"
            else:
                nid = int(mod.rsplit(".n", 1)[1])
                role = "source" if nid in STATIONS else "origRelay"
            eg[role] += v
    a["E_source"] = eg["source"]; a["E_origRelay"] = eg["origRelay"]; a["E_added"] = eg["added"]
    a["E_total"] = eg["source"] + eg["origRelay"] + eg["added"]
    a["E_source_per_node"] = eg["source"] / 10; a["E_relay_per_node"] = (eg["origRelay"] + eg["added"]) / (N - 10)
    a["latency"] = vals.get(("PeriyarRiverNetwork.BS", "latency:mean"), float("nan"))
    # topology characteristics
    pts = sorted(xy.values())
    nn = []
    for k, (x, y) in xy.items():
        nn.append(min(math.hypot(x - u, y - v) for j, (u, v) in xy.items() if j != k))
    xs = sorted([p[0] for p in pts] + [600.0])
    a["topo_meanNN"] = st.mean(nn)
    a["topo_maxXGap"] = max(b - c for b, c in zip(xs[1:], xs[:-1]))
    a["topo_within100BS"] = sum(1 for k in xy if dbs[k] <= 100)
    a["topo_addedMeanDBS"] = st.mean(dbs[k] for k in xy if k > 50) if N > 50 else float("nan")
    a["topo_stationNN"] = st.mean(min(math.hypot(xy[s][0] - u, xy[s][1] - v) for j, (u, v) in xy.items() if j != s) for s in STATIONS)
    return a


R = {}
for N in SIZES:
    for i, s in enumerate(SEEDS):
        pre = f"results_controlled/Ctrl{N}-seed{s}"
        sca = glob.glob(f"results_controlled/Ctrl{N}-seed={s}-#*.sca")[0]
        a = analyse(pre, sca, N)
        w, mem, ec = perf[(f"Ctrl{N}", i)]
        a["wall"] = w; a["peakMiB"] = mem; a["exit"] = ec
        R[(N, s)] = a
P = {}
TOPOS = [900042, 910001, 910002, 910003, 910004]
for i, e in enumerate(TOPOS):
    pre = f"results_placement/Place250-topo{e}-seed42"
    sca = glob.glob(f"results_placement/Place250-seed=42,topo={e}-#*.sca")[0]
    a = analyse(pre, sca, 250)
    a["wall"], a["peakMiB"], a["exit"] = perf[("Place250", i)]
    P[e] = a

# ------------------------------------------------------------------ per-seed CSV (all scalar fields)
scal = [k for k, v in R[(50, 42)].items() if isinstance(v, (int, float))]
with open(os.path.join(OUT, "data", "controlled_per_seed.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["N", "runSeed"] + scal)
    for N in SIZES:
        for s in SEEDS:
            w.writerow([N, s] + [R[(N, s)][k] for k in scal])
with open(os.path.join(OUT, "data", "placement_250_per_topology.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["extraTopologySeed"] + scal)
    for e in TOPOS:
        w.writerow([e] + [P[e][k] for k in scal])


def col(N, k):
    return [R[(N, s)][k] for s in SEEDS]


def table(spec, title=None):
    lines = []
    if title:
        lines.append(title)
    lines.append("| Metric | " + " | ".join(f"N = {N}" for N in SIZES) + " |")
    lines.append("|---" * (len(SIZES) + 1) + "|")
    for label, k, fmt in spec:
        lines.append(f"| {label} | " + " | ".join(ms(col(N, k), fmt) for N in SIZES) + " |")
    return "\n".join(lines)


def fnd_cell(N):
    obs = [R[(N, s)]["FND"] for s in SEEDS if R[(N, s)]["FND"] > 0]
    cen = sum(1 for s in SEEDS if R[(N, s)]["FND"] <= 0)
    if cen == 0:
        return f"{ms(obs, '%.1f')} (all 5 observed)"
    cond = f"conditional mean of {len(obs)} observed: {ms(obs, '%.1f')}" if obs else "no observed failure"
    return f"{cen} of 5 runs censored (> 1000); {cond}"


# ------------------------------------------------------------------ 02 controlled results
main = [("Scheduled report slots", "scheduled", "%.0f"), ("Slots with valid data", "validData", "%.0f"),
        ("Reports emitted (source available)", "emitted", "%.1f"), ("Reports delivered", "delivered", "%.1f"),
        ("**Scheduled-slot PDR = delivered / scheduled (%)**", "PDR", "%.2f"),
        ("Emission-conditional delivery = delivered / emitted (%)", "delivEmit", "%.2f"),
        ("Slots lost: source unavailable", "sourceUnavailable", "%.1f"),
        ("Losses: channel", "lossChannel", "%.1f"), ("Losses: energy", "lossEnergy", "%.1f"),
        ("Losses: no feasible candidate", "lossNoCand", "%.1f"), ("Losses: TTL", "lossTTL", "%.1f"),
        ("Unattempted", "unattempted", "%.1f"),
        ("Mean delivered hops", "meanHops", "%.2f"), ("Median delivered hops", "hopsMedian", "%.1f"),
        ("Mean path delay (s, MATLAB definition)", "meanDelayS", "%.4f"),
        ("Energy per delivered report (J)", "energyPerDelivered", "%.5f"),
        ("Residual energy (J, of 2N J)", "residualJ", "%.2f"), ("Residual energy (% of initial)", "residualPct", "%.2f"),
        ("Energy spent (J)", "spentJ", "%.3f"),
        ("Operational nodes at end", "finalAlive", "%.2f"),
        ("Q-updates", "qUpdates", "%.1f"), ("Exploratory decisions", "explorations", "%.1f"),
        ("Wall time per run (s)", "wall", "%.2f"), ("Peak working set per run (MiB)", "peakMiB", "%.1f")]
for N in SIZES:
    for s in SEEDS:
        R[(N, s)]["energyPerDelivered"] = R[(N, s)]["energyPerDelivered"]
lines = ["# Controlled 50 / 100 / 250 / 500-node comparison (v2)", "",
         "Design: fixed topology per node count for all run seeds (nodes 1..50 = MATLAB layout of seed 42; relays 51..N "
         "from extraTopologySeed 900042, nested), independent channel stream per run (rng(1000000·runSeed + r)), RL agent "
         "stream rng(runSeed), run seeds 42–46, 1000 rounds each, the same 10 real Periyar sources and workload. "
         "Mean ± sample sd (n − 1) over the five run seeds. Generated by `tools/analyze_controlled.py`; per-seed values in "
         "`data/controlled_per_seed.csv`. Energy per delivered report is in **J** (×1000 for mJ).", "",
         table(main), "",
         "| First node unavailable (FND) | " + " | ".join(fnd_cell(N) for N in SIZES) + " |", "",
         "FND per seed and the censoring rule: `03_first_unavailability.md`.", "",
         "## Paired differences against N = 50 (same run seed; mean ± sd of the 5 per-seed differences)", "",
         "| Quantity | " + " | ".join(f"{N} − 50" for N in SIZES[1:]) + " |", "|---" * len(SIZES) + "|"]
for label, k, fmt in [("PDR (pp)", "PDR", "%+.2f"), ("Delivered / emitted (pp)", "delivEmit", "%+.2f"),
                      ("Delivered reports", "delivered", "%+.1f"), ("Emitted reports", "emitted", "%+.1f"),
                      ("Mean delivered hops", "meanHops", "%+.2f"), ("Energy per delivered report (mJ)", "energyPerDelivered", "%+.2f")]:
    cells = []
    for N in SIZES[1:]:
        dif = [(R[(N, s)][k] - R[(50, s)][k]) * (1000 if k == "energyPerDelivered" else 1) for s in SEEDS]
        lower = sum(1 for x in dif if x < 0)
        cells.append(ms(dif, fmt).replace("± +", "± ") + f" ({lower}/5 seeds lower)")
    lines.append(f"| {label} | " + " | ".join(cells) + " |")
lines += ["", "## Per seed", "", "| N | run seed | PDR % | delivered | emitted | deliv/emit % | mean hops | energy/report (mJ) | "
          "residual J | operational at end | FND | wall s | peak MiB |", "|---" * 13 + "|"]
for N in SIZES:
    for s in SEEDS:
        a = R[(N, s)]
        f = str(a["FND"]) if a["FND"] > 0 else "none within 1000 rounds"
        lines.append(f"| {N} | {s} | {a['PDR']:.2f} | {a['delivered']} | {a['emitted']} | {a['delivEmit']:.2f} | {a['meanHops']:.2f} | "
                     f"{1000 * a['energyPerDelivered']:.2f} | {a['residualJ']:.2f} | {a['finalAlive']} | {f} | {a['wall']:.2f} | {a['peakMiB']:.1f} |")
open(os.path.join(OUT, "02_controlled_results.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

# ------------------------------------------------------------------ 03 FND
lines = ["# First node unavailable (FND), corrected reporting", "",
         "FND = first round in which fewer than N nodes are operational (MATLAB definition). A run in which no node "
         "became unavailable within the 1000-round horizon is **right-censored**: its FND is only known to be > 1000. "
         "No run is dropped. The aggregate states how many runs were censored; any mean is explicitly the "
         "**conditional mean over runs with an observed failure** and is not an unconditional estimate.", "",
         "## Controlled design (v2)", "", "| N | " + " | ".join(f"seed {s}" for s in SEEDS) + " | runs censored | conditional mean (observed only) | median over all 5 |",
         "|---" * 9 + "|"]


def fnd_row(vals):
    cells = [str(v) if v > 0 else "No node became unavailable within 1,000 rounds" for v in vals]
    obs = [v for v in vals if v > 0]
    cen = len(vals) - len(obs)
    srt = sorted(v if v > 0 else math.inf for v in vals)
    med = srt[len(srt) // 2]
    medtxt = "> 1000 (censored)" if med == math.inf else str(med)
    cond = (ms(obs, "%.1f") + f" (n = {len(obs)})") if obs else "–"
    return cells, cen, cond, medtxt


for N in SIZES:
    cells, cen, cond, med = fnd_row([R[(N, s)]["FND"] for s in SEEDS])
    lines.append(f"| {N} | " + " | ".join(cells) + f" | {cen} of 5 | {cond} | {med} |")
lines += ["", "The median over all five runs is well defined even with censoring as long as fewer than half the runs are censored.", "",
          "## v1 relay-scaling runs (topology varied with the seed), re-reported with the corrected rule", "",
          "| Config | " + " | ".join(f"seed {s}" for s in SEEDS) + " | runs censored | conditional mean (observed only) | median over all 5 |",
          "|---" * 9 + "|"]
for cfg in ["Periyar50_Baseline", "Periyar100_RelayScaling", "Periyar250_RelayScaling", "Periyar500_RelayScaling"]:
    vals = []
    for s in SEEDS:
        p = f"results/{cfg}-seed{s}-metrics.csv"
        vals.append(int(float(rows(p)[0]["FND"])) if os.path.exists(p) else None)
    have = [v for v in vals if v is not None]
    cells, cen, cond, med = fnd_row(have)
    cells_all = []
    it = iter(cells)
    for v in vals:
        cells_all.append(next(it) if v is not None else "not run")
    lines.append(f"| {cfg} | " + " | ".join(cells_all) + f" | {cen} of {len(have)} | {cond} | {med if len(have) == 5 else 'n/a (1 run)'} |")
lines += ["", "**Correction to the v1 report:** v1 printed “664.5 ± 103.0 (+1 seed with none)” (100 nodes) and “787.8 ± 141.1 (+1 seed with none)” "
          "(250 nodes). Those numbers were conditional means over 4 runs; they must not be read as five-run means."]
open(os.path.join(OUT, "03_first_unavailability.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

# ------------------------------------------------------------------ 04 diagnostics
diag = [("Transmissions (physical frames) per run", "tx", "%.0f"),
        ("Transmissions per delivered report", "txPerDelivered", "%.3f"),
        ("Failed transmissions per delivered report", "failedTxPerDelivered", "%.3f"),
        ("Transmission success rate (all hops)", "txSuccessRate", "%.4f"),
        ("True link quality of chosen hops: mean", "lqMean", "%.4f"),
        ("True link quality: median", "lqMedian", "%.4f"),
        ("True link quality: 10th percentile", "lqP10", "%.4f"),
        ("Share of chosen hops at the 0.95 cap", "lqAt095", "%.4f"),
        ("Hop distance (m): mean", "distMean", "%.1f"), ("Hop distance (m): median", "distMedian", "%.1f"),
        ("Source→cluster-head transmissions", "n_member", "%.0f"), ("  success rate", "succ_member", "%.4f"),
        ("  mean true LQ", "lq_member", "%.4f"), ("  mean distance (m)", "dist_member", "%.1f"),
        ("  share targeting an added relay", "memberToAdded", "%.3f"),
        ("Relay hops (node→node, hop ≥ 1)", "n_relay", "%.0f"), ("  success rate", "succ_relay", "%.4f"),
        ("  mean true LQ", "lq_relay", "%.4f"), ("  mean distance (m)", "dist_relay", "%.1f"),
        ("Hops into the BS", "n_toBS", "%.0f"), ("  success rate", "succ_toBS", "%.4f"),
        ("  mean true LQ", "lq_toBS", "%.4f"), ("  mean distance (m)", "dist_toBS", "%.1f"),
        ("Route transmissions (hop ≥ 1)", "routeTx", "%.0f"), ("Routes started (first route hop)", "routes", "%.0f"),
        ("Mean progress towards BS per route hop (m)", "progMean", "%.1f"),
        ("Route hops that were exploratory (share)", "share_expl", "%.3f"),
        ("  progress (m): exploratory", "prog_expl", "%.1f"), ("  progress (m): greedy", "prog_expt", "%.1f"),
        ("  true LQ: exploratory", "lq_expl", "%.4f"), ("  true LQ: greedy", "lq_expt", "%.4f"),
        ("  success: exploratory", "succ_expl", "%.4f"), ("  success: greedy", "succ_expt", "%.4f"),
        ("Feasible candidates per cluster decision (incl. self)", "candCluster", "%.1f"),
        ("Feasible candidates per route decision: mean", "candRoute", "%.1f"),
        ("Feasible candidates per route decision: median", "candRouteMedian", "%.1f"),
        ("Self-head share of cluster decisions", "selfHeadShare", "%.3f"),
        ("Route decisions", "routeDecisions", "%.0f"),
        ("Delivered hops: median", "hopsMedian", "%.1f"), ("Delivered hops: 90th percentile", "hopsP90", "%.1f"),
        ("Delivered hops: max", "hopsMax", "%.0f"),
        ("Share of transmissions to added relays", "txToAdded", "%.3f"),
        ("Distinct added relays selected (of N − 50)", "addedUsed", "%.1f"),
        ("Energy spent by the 10 sources (J)", "E_source", "%.3f"),
        ("Energy spent by the 40 original relays (J)", "E_origRelay", "%.3f"),
        ("Energy spent by added relays (J)", "E_added", "%.3f"), ("Energy spent, total (J)", "E_total", "%.3f"),
        ("Energy per source node (J)", "E_source_per_node", "%.4f"), ("Energy per relay node (J)", "E_relay_per_node", "%.4f")]
lines = ["# Routing and packet-loss diagnostics (controlled design, run seeds 42–46)", "",
         "Source: `<run>-hops.csv` (one row per real transmission, written after its outcome; it records the true link "
         "quality that generated the outcome, which the routing agent never sees), `decisions.csv`, `reports.csv` and the scalar file. "
         "Mean ± sample sd over run seeds. Hop types: source→cluster head (hop index 0), relay hop node→node, hop into the BS.", "",
         table(diag), "",
         "Consistency: for every run, the reports carried by failed transmissions add up exactly to the channel-loss count "
         f"({'yes' if all(R[k]['lossCheck'] for k in R) else 'NO'} for all 20 runs).", "",
         "## Report-level loss by hop index (sum over the five run seeds)", "",
         "Reports carried into a transmission at hop index h, and the share of those lost on that transmission "
         "(h = 0: source→cluster head; h ≥ 1: route hops from the cluster head).", "",
         "| hop index | " + " | ".join(f"N = {N}: carried / lost % " for N in SIZES) + " |", "|---" * (len(SIZES) + 1) + "|"]
maxh = max(max(R[(N, s)]["carriedByHop"]) for N in SIZES for s in SEEDS)
for h in range(0, maxh + 1):
    cells = []
    for N in SIZES:
        c = sum(R[(N, s)]["carriedByHop"].get(h, 0) for s in SEEDS)
        l = sum(R[(N, s)]["lossByHop"].get(h, 0) for s in SEEDS)
        cells.append(f"{c} / {100 * l / c:.1f}" if c else "–")
    lines.append(f"| {h} | " + " | ".join(cells) + " |")
lines += ["", "## Distribution of delivered hop counts (share of delivered reports, all five run seeds pooled)", "",
          "| hops | " + " | ".join(f"N = {N}" for N in SIZES) + " |", "|---" * (len(SIZES) + 1) + "|"]
maxd = max(max(R[(N, s)]["hopHist"]) for N in SIZES for s in SEEDS)
for h in range(1, maxd + 1):
    cells = []
    for N in SIZES:
        tot = sum(sum(R[(N, s)]["hopHist"].values()) for s in SEEDS)
        c = sum(R[(N, s)]["hopHist"].get(h, 0) for s in SEEDS)
        cells.append(f"{100 * c / tot:.1f} %")
    lines.append(f"| {h} | " + " | ".join(cells) + " |")
lines += ["", "## Per-seed key diagnostics", "",
          "| N | seed | PDR % | mean hops | tx / delivered | tx success | mean true LQ | route hops exploratory | mean candidates (route) | progress/hop m |",
          "|---" * 10 + "|"]
for N in SIZES:
    for s in SEEDS:
        a = R[(N, s)]
        lines.append(f"| {N} | {s} | {a['PDR']:.2f} | {a['meanHops']:.2f} | {a['txPerDelivered']:.2f} | {a['txSuccessRate']:.4f} | "
                     f"{a['lqMean']:.4f} | {a['share_expl']:.3f} | {a['candRoute']:.1f} | {a['progMean']:.1f} |")
open(os.path.join(OUT, "04_routing_diagnostics.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

# ------------------------------------------------------------------ 05 placement
pl = [("PDR (%)", "PDR", "%.2f"), ("Delivered / emitted (%)", "delivEmit", "%.2f"), ("Delivered", "delivered", "%d"),
      ("Emitted", "emitted", "%d"), ("Mean delivered hops", "meanHops", "%.2f"),
      ("Energy per delivered report (mJ)", "energyPerDelivered", "%.2f"), ("Transmission success rate", "txSuccessRate", "%.4f"),
      ("Mean true LQ of chosen hops", "lqMean", "%.4f"), ("Mean progress per route hop (m)", "progMean", "%.1f"),
      ("Mean feasible candidates per route decision", "candRoute", "%.1f"),
      ("FND", "FND", "%d"), ("Operational at end", "finalAlive", "%d"),
      ("Topology: mean nearest-neighbour distance, all 250 nodes (m)", "topo_meanNN", "%.2f"),
      ("Topology: largest gap along the river, incl. BS at x = 600 (m)", "topo_maxXGap", "%.2f"),
      ("Topology: nodes within 100 m of the BS", "topo_within100BS", "%d"),
      ("Topology: mean distance of added relays to the BS (m)", "topo_addedMeanDBS", "%.1f"),
      ("Topology: mean distance from a station to its nearest node (m)", "topo_stationNN", "%.2f"),
      ("Wall time (s)", "wall", "%.2f")]
lines = ["# 250-node relay-placement sensitivity (separate experiment)", "",
         "Run seed fixed at 42 (channel stream rng(1000000·42 + r), agent stream rng(42)); nodes 1..50 fixed at the MATLAB "
         "layout of seed 42; only the 200 added relays are re-placed, from the documented extraTopologySeed values below. "
         "Everything else is identical. These five values are **not** part of the five-run-seed standard deviation in "
         "`02_controlled_results.md`; they describe how much a single run changes when only the relay placement changes. "
         "Placement 900042 is the placement of the controlled design (byte-identical to Ctrl250 run seed 42). "
         "", "",
         "| Metric | " + " | ".join(f"topo {e}" for e in TOPOS) + " | range (max − min) |", "|---" * (len(TOPOS) + 2) + "|"]
for label, k, fmt in pl:
    if k == "FND":   # censored runs are reported as such, never as -1 and never folded into a range
        cells = [str(P[e]["FND"]) if P[e]["FND"] > 0 else "none within 1000 rounds" for e in TOPOS]
        cen = sum(1 for e in TOPOS if P[e]["FND"] <= 0)
        lines.append(f"| FND (first node unavailable) | " + " | ".join(cells) + f" | {cen} of 5 censored |")
        continue
    v = [P[e][k] * (1000 if k == "energyPerDelivered" else 1) for e in TOPOS]
    cells = [fmt % (int(x) if fmt == "%d" else x) for x in v]
    rng = (max(v) - min(v))
    lines.append(f"| {label} | " + " | ".join(cells) + f" | {rng:.4g} |")
ctrl_sd = st.stdev(col(250, "PDR"))
pl_sd = st.stdev([P[e]["PDR"] for e in TOPOS])
lines += ["", f"PDR spread: placement-only sd over 5 placements (run seed 42) = {pl_sd:.2f} pp; run-seed-only sd over 5 run seeds "
          f"(placement 900042) = {ctrl_sd:.2f} pp."]
order_pdr = sorted(TOPOS, key=lambda e: -P[e]["PDR"])
order_iso = sorted(TOPOS, key=lambda e: P[e]["topo_stationNN"])
lines += ["", "Observation (5 placements only, not a tested relationship): the PDR rank order "
          + ("coincides exactly with" if order_pdr == order_iso else "does NOT coincide with")
          + " the inverse rank of the mean station-to-nearest-node distance "
          f"({min(P[e]['topo_stationNN'] for e in TOPOS):.2f} → {max(P[e]['topo_stationNN'] for e in TOPOS):.2f} m). "
          "Part of the PDR spread comes from emission (node failures of sources); compare the delivered/emitted row."]
open(os.path.join(OUT, "05_placement_sensitivity.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

# ------------------------------------------------------------------ console summary
for N in SIZES:
    print(f"N={N}: PDR {ms(col(N, 'PDR'))}, deliv/emit {ms(col(N, 'delivEmit'))}, hops {ms(col(N, 'meanHops'))}, "
          f"tx/deliv {ms(col(N, 'txPerDelivered'), '%.2f')}, txSucc {ms(col(N, 'txSuccessRate'), '%.4f')}, "
          f"LQ {ms(col(N, 'lqMean'), '%.4f')}, candRoute {ms(col(N, 'candRoute'), '%.1f')}, prog {ms(col(N, 'progMean'), '%.1f')}, "
          f"FND {[R[(N, s)]['FND'] for s in SEEDS]}")
for e in TOPOS:
    print(f"topo {e}: PDR {P[e]['PDR']:.2f}, hops {P[e]['meanHops']:.2f}, maxGap {P[e]['topo_maxXGap']:.1f}, within100 {P[e]['topo_within100BS']}")
print(f"placement sd {pl_sd:.2f} vs run-seed sd {ctrl_sd:.2f}")
