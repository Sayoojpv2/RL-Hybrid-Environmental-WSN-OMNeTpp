#!/usr/bin/env python3
"""Verify and summarise the configurable-size V2 runs (config V2_ScalingSweep / V2_Scalable).

Usage: python3 tools/v2_scaling.py <result dir> <config> <N list> <seed list> [--table] [--plot out.png]
   e.g. python3 tools/v2_scaling.py results_v2_scaling V2_ScalingSweep 10,20,50,100,200,500 42,43,44,45,46 --table --plot g.png
Checks per run (PASS/FAIL):
  S1 exactly N node modules (node[0..N-1]) + 1 BS; per-node energy closes (tx + rx + aggregation = 2 J - residual)
  S2 N positions, all inside the area, pairwise distinct, none at the BS; nodes 1-10 = the MATLAB V2 station positions
  S3 workload: nodes 1-10 carry exactly the real KSPCB reports of MATLAB V2; nodes 11-N carry SYNTHETIC reports
     (label SYNTHETIC-n<id>, date synthetic-r<round>, finite values), one per node per round; every node is a source
  S4 accounting and invariants (the simulation's own end-of-run checks) passed
Reported, not asserted: how many nodes received frames from other nodes (forwarding / aggregation) and
Q-table entries. Metrics are mean +/- sample sd over seeds.
"""
import csv, glob, math, os, statistics as st, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
rd, cfg = sys.argv[1], sys.argv[2]
Ns = [int(x) for x in sys.argv[3].split(",")]
seeds = [int(x) for x in sys.argv[4].split(",")]
REF = os.path.join("matlab_reference", "data_v2")
E0, L, W, BS = 2.0, 600.0, 50.0, (600.0, 25.0)
fails, lines = [], []
M = defaultdict(lambda: defaultdict(list))


def check(ok, msg):
    lines.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def num(s):
    s = (s or "").strip()
    return math.nan if s in ("", "NaN", "nan") else float(s)


perf = {}
if os.path.exists("logs_v2/performance_v2.csv"):
    for r in rows("logs_v2/performance_v2.csv"):
        perf[(r["config"], r["run"])] = (float(r["wallSeconds"]), float(r["peakWorkingSetMiB"]))
runmap = {}
if os.path.exists(os.path.join(rd, "runmap.csv")):
    for r in rows(os.path.join(rd, "runmap.csv")):
        runmap[(int(r["N"]), int(r["seed"]))] = r["run"]
wm = rows(os.path.join(REF, "workload_matlab.csv"))

for N in Ns:
    for seed in seeds:
        tag = f"N={N} seed {seed}"
        pre = os.path.join(rd, f"{cfg}-N{N}-seed{seed}")
        sca = glob.glob(os.path.join(rd, f"{cfg}-N={N},seed={seed}-#*.sca"))[0]
        vals = defaultdict(dict)
        for line in open(sca):
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar":
                vals[p[1]][p[2]] = float(p[3])
        mods = sorted((m for m in vals if ".node[" in m), key=lambda m: int(m.split("[")[1].rstrip("]")))
        worst = max(abs((E0 - vals[m]["residualEnergy"]) - (vals[m]["txEnergy"] + vals[m]["rxEnergy"] + vals[m]["aggregationEnergy"])) for m in mods)
        check(len(mods) == N and "PeriyarRiverNetwork.BS" in vals and worst < 1e-9,
              f"{tag}: S1 {len(mods)} node modules + 1 BS; per-node energy closes (max error {worst:.1e} J)")

        nodes = rows(pre + "-nodes.csv")
        pts = [(num(r["x"]), num(r["y"])) for r in nodes]
        ref10 = [(num(r["x"]), num(r["y"])) for r in rows(os.path.join(REF, f"nodes_seed{seed}.csv"))]
        check(len(pts) == N and all(0 < x < L and 0 < y < W for x, y in pts) and len(set(pts)) == N and BS not in pts
              and pts[:10] == ref10, f"{tag}: S2 {N} positions inside 600 x 50 m, distinct; nodes 1-10 = MATLAB V2 positions")

        wl = rows(pre + "-workload.csv")
        real = [r for r in wl if int(r["sourceNode"]) <= 10]
        syn = [r for r in wl if int(r["sourceNode"]) > 10]
        real_ok = len(real) == len(wm) and all(a["round"] == b["round"] and a["sourceNode"] == b["sourceNode"] and
                                               a["station"] == b["station"] and a["date"] == b["date"] and
                                               all(num(a[k]) == num(b[k]) for k in ("temperature", "pH", "conductivity", "TDS"))
                                               for a, b in zip(real, wm))
        rounds = len(rows(pre + "-per_round.csv"))
        syn_ok = (len(syn) == (N - 10) * 500 and all(r["station"] == "SYNTHETIC-n" + r["sourceNode"] and r["date"] == "synthetic-r" + r["round"]
                                                     and all(math.isfinite(num(r[k])) for k in ("temperature", "pH", "conductivity", "TDS")) for r in syn))
        srcs = {int(r["sourceNode"]) for r in wl}
        check(real_ok and syn_ok and srcs == set(range(1, N + 1)),
              f"{tag}: S3 nodes 1-10 = the {len(wm)} real KSPCB reports of MATLAB V2; {len(syn)} SYNTHETIC-labelled reports "
              f"for nodes 11-{N}; all {N} nodes are report sources")

        summ = open(pre + "-summary.txt").read()
        check("energy closes OK; slot accounting OK; per-round MATLAB invariants OK" in summ,
              f"{tag}: S4 end-of-run accounting and per-round invariants OK ({rounds} rounds)")

        met = rows(pre + "-metrics.csv")[0]
        per = rows(pre + "-per_round.csv")
        rep = rows(pre + "-reports.csv")
        dl = [r for r in rep if r["fate"] == "delivered"]
        by_round = defaultdict(list)
        for r in dl:
            by_round[int(r["resolvedRound"])].append(num(r["pathDelayS"]))
        alive = [int(r["aliveCount"]) for r in per]
        fnd = next((int(r["round"]) for r in per if int(r["aliveCount"]) < N), None)
        m = M[N]
        m["finalAlive"].append(alive[-1]); m["finalAlivePct"].append(100 * alive[-1] / N)
        m["residualJ"].append(num(met["residualJ"])); m["residualPct"].append(100 * num(met["residualJ"]) / (E0 * N))
        m["generated"].append(num(met["sourceAvailable"])); m["delivered"].append(num(met["delivered"]))
        m["realDelivered"].append(sum(1 for r in dl if int(r["sourceNode"]) <= 10))
        m["validPDR"].append(100 * num(met["delivered"]) / num(met["workloadAvailable"]))
        m["sourcePDR"].append(100 * num(met["delivered"]) / max(1, num(met["sourceAvailable"])))
        m["schedPDR"].append(num(met["PDR"]))
        m["delayPacketMs"].append(1000 * st.mean(num(r["pathDelayS"]) for r in dl) if dl else math.nan)
        m["delayRoundMs"].append(1000 * st.mean(st.mean(v) for v in by_round.values()) if dl else math.nan)
        m["meanHops"].append(num(met["meanHops"]))
        m["FND"].append(fnd if fnd else math.nan)
        m["forwarders"].append(sum(1 for mm in mods if vals[mm].get("rxFrames", 0) > 0))
        m["qEntries"].append(sum(vals[mm].get("qTableNonZeroEntries", 0) for mm in mods))
        run = runmap.get((N, seed))
        if run is not None and (cfg, run) in perf:
            m["wallS"].append(perf[(cfg, run)][0]); m["peakMiB"].append(perf[(cfg, run)][1])

print("\n".join(lines))
print(f"\n{len(lines)} checks, {len(fails)} failed\n")


def ms(v, f="%.2f"):
    v = [x for x in v if not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return "–"
    return (f % st.mean(v)) + (" ± " + (f % st.stdev(v)) if len(v) > 1 else "")


if "--table" in sys.argv:
    spec = [("Operational nodes at end", "finalAlive", "%.1f"), ("  (% of N)", "finalAlivePct", "%.1f"),
            ("Residual energy (J)", "residualJ", "%.2f"), ("  (% of initial 2N J)", "residualPct", "%.1f"),
            ("Generated reports", "generated", "%.0f"), ("Delivered reports", "delivered", "%.0f"),
            ("  of which real KSPCB (nodes 1-10)", "realDelivered", "%.0f"),
            ("Valid-report delivery ratio (%)", "validPDR", "%.2f"), ("Source-packet PDR (%)", "sourcePDR", "%.2f"),
            ("Delivered / scheduled (%)", "schedPDR", "%.2f"), ("Mean delay per report (ms)", "delayPacketMs", "%.1f"),
            ("Mean delay, round-weighted (ms)", "delayRoundMs", "%.1f"), ("Mean delivered hops", "meanHops", "%.2f"),
            ("First node failure (round)", "FND", "%.1f"), ("Nodes that received frames from others", "forwarders", "%.1f"),
            ("Q-table entries, all nodes", "qEntries", "%.0f"), ("Runtime per run (s)", "wallS", "%.1f"),
            ("Peak memory per run (MiB)", "peakMiB", "%.0f")]
    print("| Metric | " + " | ".join(f"N = {n}" for n in Ns) + " |")
    print("|---" * (len(Ns) + 1) + "|")
    for lab, k, f in spec:
        cells = []
        for n in Ns:
            c = ms(M[n][k], f)
            if k == "FND":
                cen = sum(1 for x in M[n][k] if isinstance(x, float) and math.isnan(x))
                if cen:
                    c += f" ({cen} run(s) without failure)"
            cells.append(c)
        print(f"| {lab} | " + " | ".join(cells) + " |")

if "--plot" in sys.argv:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = sys.argv[sys.argv.index("--plot") + 1]
    panels = [("Valid-report delivery ratio and source-packet PDR (%)", [("validPDR", "valid-report delivery ratio"), ("sourcePDR", "source-packet PDR")]),
              ("Delivered reports", [("delivered", "all nodes"), ("realDelivered", "real KSPCB stations (nodes 1-10)")]),
              ("Operational nodes at round 500 (% of N)", [("finalAlivePct", "operational")]),
              ("Residual energy (% of initial 2N J)", [("residualPct", "residual")]),
              ("Mean end-to-end delay (ms)", [("delayPacketMs", "per delivered report")]),
              ("First node failure (round)", [("FND", "FND")])]
    fig, axs = plt.subplots(2, 3, figsize=(15, 8.5))
    for ax, (title, series) in zip(axs.flat, panels):
        for k, lab in series:
            mean = [st.mean([x for x in M[n][k] if not math.isnan(x)]) if any(not math.isnan(x) for x in M[n][k]) else math.nan for n in Ns]
            sd = [st.stdev([x for x in M[n][k] if not math.isnan(x)]) if sum(not math.isnan(x) for x in M[n][k]) > 1 else 0 for n in Ns]
            ax.errorbar(Ns, mean, yerr=sd, marker="o", capsize=3, label=lab)
        ax.set_xscale("log"); ax.set_xticks(Ns); ax.set_xticklabels([str(n) for n in Ns])
        ax.set_title(title, fontsize=10); ax.set_xlabel("number of nodes N (all sense + forward)"); ax.grid(alpha=0.3)
        if len(series) > 1:
            ax.legend(fontsize=8)
    fig.suptitle("OMNeT++ RL-Hybrid (MATLAB V2 model), fixed 600 m x 50 m area, 500 rounds, mean ± sd over seeds "
                 + ",".join(map(str, seeds)) + "\nLarger N = higher node density AND more offered traffic "
                 "(nodes 11-N report SYNTHETIC placeholder data every round)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=130)
    print(f"graph: {out}")
sys.exit(1 if fails else 0)
