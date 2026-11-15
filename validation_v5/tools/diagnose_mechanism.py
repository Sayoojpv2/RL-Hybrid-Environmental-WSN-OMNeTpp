#!/usr/bin/env python3
"""v2 mechanism probes for the PDR decline (controlled design, read-only analysis of logged runs).

Usage: python3 tools/diagnose_mechanism.py   -> reports_v2/04b_mechanism_probes.md (+ data/mechanism_per_seed.csv)

Probes (all from decisions.csv / hops.csv / nodes.csv; nothing is re-simulated):
  P1 cluster phase: progress of the source -> cluster-head hop towards the BS (negative = cluster head upstream)
  P2 where routes start: distance of the cluster head (route origin) to the BS
  P3 novelty of GREEDY decisions: share choosing a (node, state, action) never chosen before by that node.
     Untried actions have Q = 0; a failed action gets a negative Q (reward -1), so greedy selection moves to
     untried actions after failures. A larger action space supplies more untried actions.
  P4 the first route hop (hop index 1): distance, true LQ, progress, share exploratory, share novel
  P5 success of greedy hops that were novel vs previously tried
"""
import csv, glob, math, os, statistics as st, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
SEEDS = [42, 43, 44, 45, 46]
SIZES = [50, 100, 250, 500]
BS = (600.0, 25.0)
OUT = "reports_v2"


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def ms(v, fmt="%.3f"):
    return (fmt % st.mean(v)) + " ± " + (fmt % st.stdev(v)) if len(v) > 1 else fmt % v[0]


def probe(pre, N):
    xy = {int(r["node"]): (float(r["x"]), float(r["y"])) for r in rows(pre + "-nodes.csv")}
    dbs = {k: math.hypot(x - BS[0], y - BS[1]) for k, (x, y) in xy.items()}
    dbs[N + 1] = 0.0
    dec = rows(pre + "-decisions.csv")
    hops = rows(pre + "-hops.csv")
    tried = set()
    novel_flag = []                   # per decision: was (actor, state, target) new at decision time?
    for r in dec:
        key = (r["actor"], r["state"], r["target"])
        novel_flag.append(key not in tried)
        tried.add(key)
    a = {}
    mem = [r for r in dec if r["hopType"] == "1"]
    prog = [dbs[int(r["actor"])] - dbs[int(r["target"])] for r in mem]
    a["P1_memberProgress"] = st.mean(prog)
    a["P1_upstreamShare"] = sum(1 for p in prog if p < 0) / len(prog)
    a["P1_memberDist"] = st.mean(math.dist(xy[int(r["actor"])], xy[int(r["target"])]) for r in mem)
    src_d = [dbs[int(r["actor"])] for r in mem]
    a["P2_sourceDBS"] = st.mean(src_d)
    starts = [r for r in hops if r["hop"] == "1"]
    a["P2_routeStartDBS"] = st.mean(dbs[int(r["actor"])] for r in starts)
    for lab, types in [("route", ("2", "3")), ("cluster", ("0", "1"))]:
        g = [i for i, r in enumerate(dec) if r["hopType"] in types and r["explored"] == "0"]
        a[f"P3_greedyNovel_{lab}"] = sum(1 for i in g if novel_flag[i]) / len(g)
        e = [i for i, r in enumerate(dec) if r["hopType"] in types and r["explored"] == "1"]
        a[f"P3_exploredNovel_{lab}"] = sum(1 for i in e if novel_flag[i]) / len(e)
    # per-transmission join: hops.csv rows are the decisions with target != actor, in the same order
    tx_idx = [i for i, r in enumerate(dec) if r["target"] != r["actor"]]
    assert len(tx_idx) == len(hops)
    h1 = [(hops[k], tx_idx[k]) for k in range(len(hops)) if hops[k]["hop"] == "1"]
    a["P4_hop1Dist"] = st.mean(float(h["distanceM"]) for h, _ in h1)
    a["P4_hop1LQ"] = st.mean(float(h["trueLQ"]) for h, _ in h1)
    a["P4_hop1Succ"] = sum(1 for h, _ in h1 if float(h["outcome"]) == 1) / len(h1)
    a["P4_hop1Prog"] = st.mean(dbs[int(h["actor"])] - dbs[int(h["target"])] for h, _ in h1)
    a["P4_hop1Expl"] = sum(1 for h, _ in h1 if h["explored"] == "1") / len(h1)
    a["P4_hop1Novel"] = sum(1 for _, i in h1 if novel_flag[i]) / len(h1)
    gr = [(hops[k], tx_idx[k]) for k in range(len(hops)) if hops[k]["hopType"] in ("2", "3") and hops[k]["explored"] == "0"]
    nov = [h for h, i in gr if novel_flag[i]]
    old = [h for h, i in gr if not novel_flag[i]]
    a["P5_succGreedyNovel"] = sum(1 for h in nov if float(h["outcome"]) == 1) / len(nov)
    a["P5_succGreedyTried"] = sum(1 for h in old if float(h["outcome"]) == 1) / len(old)
    a["P5_lqGreedyNovel"] = st.mean(float(h["trueLQ"]) for h in nov)
    a["P5_lqGreedyTried"] = st.mean(float(h["trueLQ"]) for h in old)
    a["P5_progGreedyNovel"] = st.mean(dbs[int(h["actor"])] - dbs[int(h["target"])] for h in nov)
    a["P5_progGreedyTried"] = st.mean(dbs[int(h["actor"])] - dbs[int(h["target"])] for h in old)
    a["distinctTried"] = len(tried)
    return a


R = {(N, s): probe(f"results_controlled/Ctrl{N}-seed{s}", N) for N in SIZES for s in SEEDS}
keys = list(R[(50, 42)])
with open(os.path.join(OUT, "data", "mechanism_per_seed.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["N", "runSeed"] + keys)
    for N in SIZES:
        for s in SEEDS:
            w.writerow([N, s] + [R[(N, s)][k] for k in keys])

labels = [("P1 source→cluster-head progress towards BS (m; negative = upstream)", "P1_memberProgress", "%.1f"),
          ("P1 share of source→cluster-head hops going upstream", "P1_upstreamShare", "%.3f"),
          ("P1 source→cluster-head distance (m)", "P1_memberDist", "%.1f"),
          ("P2 mean source distance to BS (m)", "P2_sourceDBS", "%.1f"),
          ("P2 mean route-origin (cluster head) distance to BS (m)", "P2_routeStartDBS", "%.1f"),
          ("P3 greedy ROUTE decisions choosing a never-tried (node, state, action)", "P3_greedyNovel_route", "%.3f"),
          ("P3 exploratory ROUTE decisions choosing a never-tried action", "P3_exploredNovel_route", "%.3f"),
          ("P3 greedy CLUSTER decisions choosing a never-tried action", "P3_greedyNovel_cluster", "%.3f"),
          ("P4 first route hop: distance (m)", "P4_hop1Dist", "%.1f"), ("P4 first route hop: true LQ", "P4_hop1LQ", "%.4f"),
          ("P4 first route hop: success", "P4_hop1Succ", "%.4f"), ("P4 first route hop: progress (m)", "P4_hop1Prog", "%.1f"),
          ("P4 first route hop: share exploratory", "P4_hop1Expl", "%.3f"), ("P4 first route hop: share never-tried", "P4_hop1Novel", "%.3f"),
          ("P5 greedy route hops, never-tried: success", "P5_succGreedyNovel", "%.4f"),
          ("P5 greedy route hops, previously tried: success", "P5_succGreedyTried", "%.4f"),
          ("P5 greedy route hops, never-tried: true LQ", "P5_lqGreedyNovel", "%.4f"),
          ("P5 greedy route hops, previously tried: true LQ", "P5_lqGreedyTried", "%.4f"),
          ("P5 greedy route hops, never-tried: progress (m)", "P5_progGreedyNovel", "%.1f"),
          ("P5 greedy route hops, previously tried: progress (m)", "P5_progGreedyTried", "%.1f"),
          ("Distinct (node, state, action) pairs chosen in 1000 rounds", "distinctTried", "%.0f")]
lines = ["# Mechanism probes for the PDR decline (controlled design, run seeds 42–46)", "",
         "Read-only analysis of the logged runs (`tools/diagnose_mechanism.py`). Mean ± sample sd over run seeds. "
         "“Never-tried” = the node had not chosen this (state, action) before in that run, i.e. its Q-value was still the "
         "initial 0 when chosen.", "",
         "| Probe | " + " | ".join(f"N = {N}" for N in SIZES) + " |", "|---" * (len(SIZES) + 1) + "|"]
for lab, k, fmt in labels:
    lines.append(f"| {lab} | " + " | ".join(ms([R[(N, s)][k] for s in SEEDS], fmt) for N in SIZES) + " |")
open(os.path.join(OUT, "04b_mechanism_probes.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
for lab, k, fmt in labels:
    print(lab, " | ".join(ms([R[(N, s)][k] for s in SEEDS], fmt) for N in SIZES))
