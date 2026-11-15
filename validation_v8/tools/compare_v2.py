#!/usr/bin/env python3
"""Compare OMNeT++ (config V2_10Node / V2_10Node_Smoke) with the MATLAB V2 10-node RL-Hybrid export.

Usage: python3 tools/compare_v2.py <Config> <seed> [<seed> ...]
Reference: matlab_reference/data_v2 (written by matlab_reference/scripts/export_reference_v2.m from
<USER_HOME>\\Documents\\MATLAB\\RL_WSN_Periyar_V2_10Nodes, rounds 1-500, seeds 42-46).
Only the rounds OMNeT++ simulated are compared (a smoke run covers the first rounds only).
Exact comparisons are exact (==) unless a tolerance is printed; nothing is rounded before comparing.
"""
import csv, glob, math, os, statistics as st, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
cfg, seeds = sys.argv[1], [int(s) for s in sys.argv[2:]]
REF = os.path.join("matlab_reference", "data_v2")
RES = os.environ.get("V2_RES", "results_v2_10node")   # result folder (env V2_RES overrides)
fails, lines = [], []
summary = defaultdict(lambda: defaultdict(list))   # metric -> side -> values


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


def same(a, b, tol=0.0):
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tol * max(1.0, abs(b))


def first_round(mask_rows, cond):
    for r in mask_rows:
        if cond(r):
            return int(r["round"])
    return math.nan


for seed in seeds:
    pre = os.path.join(RES, f"{cfg}-seed{seed}")
    per_o = rows(pre + "-per_round.csv")
    R = len(per_o)
    per_m = [r for r in rows(os.path.join(REF, f"per_round_matlab_seed{seed}.csv")) if int(r["round"]) <= R]
    N = 10

    # 1. topology and channel
    no, nm = rows(pre + "-nodes.csv"), rows(os.path.join(REF, f"nodes_seed{seed}.csv"))
    check(len(no) == len(nm) == N and all(num(a["x"]) == num(b["x"]) and num(a["y"]) == num(b["y"]) for a, b in zip(no, nm)),
          f"seed {seed}: 10 node positions identical to MATLAB generate_scenario(seed, cfg) 'stationPositions'")
    so = open(pre + "-success.bin", "rb").read()
    sm = open(os.path.join(REF, f"success_seed{seed}.bin"), "rb").read()
    blk = N * (N + 1)
    check(so[:blk * R] == sm[:blk * R], f"seed {seed}: channel success bits rounds 1-{R} identical ({blk * R} links)")

    # 2. workload (generated reports per round and payload)
    wo = rows(pre + "-workload.csv")
    wm = rows(os.path.join(REF, "workload_matlab.csv"))
    keys = ["reportIndex", "round", "sourceNode", "station", "date"]
    vals = ["temperature", "pH", "conductivity", "TDS"]
    check(len(wo) == len(wm) and all(a[k] == b[k] for a, b in zip(wo, wm) for k in keys)
          and all(num(a[v]) == num(b[v]) for a, b in zip(wo, wm) for v in vals),
          f"seed {seed}: workload identical ({len(wm)} reports with data in rounds 1-500, stations on nodes 1-10, payload values)")

    # 3. routing decisions and Q-learning (decision log columns shared with MATLAB)
    do = [r for r in rows(pre + "-decisions.csv")]
    dm = [r for r in rows(os.path.join(REF, f"decisions_matlab_seed{seed}.csv")) if int(r["round"]) <= R]
    cols = ["round", "hopType", "actor", "target", "reports", "qHat", "prior", "attemptsBefore", "successesBefore",
            "actorE", "targetE", "outcome"]
    # integer columns exactly; floating-point columns within 1e-9 relative (as the original 50-node validation)
    exact = ["round", "hopType", "actor", "target", "reports", "attemptsBefore", "successesBefore", "outcome"]
    flt = ["qHat", "prior", "actorE", "targetE"]
    n_same, first_diff, max_fd, n_bitexact = 0, None, 0.0, 0
    for i, (a, b) in enumerate(zip(do, dm)):
        ok = all(same(num(a[c]), num(b[c])) for c in exact) and all(same(num(a[c]), num(b[c]), 1e-9) for c in flt)
        for c in flt:
            x, y = num(a[c]), num(b[c])
            if not (math.isnan(x) and math.isnan(y)):
                max_fd = max(max_fd, abs(x - y))
        n_bitexact += all(same(num(a[c]), num(b[c])) for c in exact + flt)
        if ok:
            n_same += 1
        elif first_diff is None:
            first_diff = (i + 1, {c: (a[c], b[c]) for c in exact + flt if not same(num(a[c]), num(b[c]), 1e-9)})
    check(len(do) == len(dm) and n_same == len(dm),
          f"seed {seed}: decisions {n_same}/{len(dm)} identical (OMNeT++ {len(do)}) - round, type, actor, chosen target, "
          f"reports, link history and outcome exactly; q-estimate, prior and energies within 1e-9 "
          f"(bit-identical rows {n_bitexact}; largest floating difference {max_fd:.2g})"
          + (f"; first difference at decision {first_diff[0]}: {first_diff[1]}" if first_diff else ""))

    # 4. per-round series
    pairs = [("delivered", "delivered", 0), ("aliveCount", "aliveCount", 0), ("residualJ", "residualJ", 1e-12),
             ("qUpdates", "qUpdates", 0), ("explorations", "explorations", 0), ("epsilon", "epsilon", 0),
             ("scheduled", "scheduled", 0), ("sourceAvailable", "sourceAvailable", 0), ("attempts", "attempts", 0),
             ("stageLoss", "stageLoss", 0), ("unattempted", "unattempted", 0)]
    for co, cm, tol in pairs:
        bad = [int(a["round"]) for a, b in zip(per_o, per_m) if not same(num(a[co]), num(b[cm]), tol)]
        check(len(per_o) == len(per_m) and not bad,
              f"seed {seed}: per-round {co} identical in all {R} rounds" + (f" (tolerance {tol:g} relative)" if tol else "")
              + (f"; differs in {len(bad)} rounds, first {bad[0]}" if bad else ""))
    spent_o = [num(a["txJ"]) + num(a["rxJ"]) + num(a["aggJ"]) for a in per_o]
    bad = [i + 1 for i, (x, b) in enumerate(zip(spent_o, per_m)) if not same(x, num(b["spentJ"]), 1e-12)]
    check(not bad, f"seed {seed}: per-round energy spent equal within 1e-12 relative" + (f"; first difference round {bad[0]}" if bad else ""))

    # 5. per-node residual energy and survival (end of the simulated rounds; full runs only)
    if R == 500:
        vals_sca = {}
        for line in open(glob.glob(os.path.join(RES, f"{cfg}-seed={seed}-#*.sca"))[0]):
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar" and p[2] == "residualEnergy" and ".node[" in p[1]:   # node[k] = id k+1
                vals_sca[int(p[1].split(".node[")[1].rstrip("]")) + 1] = float(p[3])
            elif len(p) >= 4 and p[0] == "scalar" and p[2] == "residualEnergy" and ".n" in p[1]:    # older nK naming
                vals_sca[int(p[1].rsplit(".n", 1)[1])] = float(p[3])
        ne = rows(os.path.join(REF, f"node_energy_matlab_seed{seed}.csv"))
        un = {int(r["node"]): r for r in rows(pre + "-unavailability.csv")}
        e_ok = all(same(vals_sca[int(r["node"])], num(r["residualJ"]), 1e-12) for r in ne)
        s_ok = all(same(num(un[int(r["node"])]["firstUnavailableRound"]), num(r["firstUnavailableRound"]))
                   and un[int(r["node"])]["reason"] == r["reason"] for r in ne)
        check(e_ok and s_ok, f"seed {seed}: residual energy of each of the 10 nodes equal within 1e-12 relative; "
                             f"unavailability round and reason identical per node")

    # 6. headline metrics (computed the MATLAB way from both sides' series)
    def metrics(per, deliv_delays):
        d = sum(num(r["delivered"]) for r in per)
        sched = sum(num(r["scheduled"]) for r in per)
        gen = sum(num(r["sourceAvailable"]) for r in per)
        alive = [num(r["aliveCount"]) for r in per]
        m = dict(delivered=d, generated=gen, scheduled=sched, PDR=100 * d / sched, sourcePDR=100 * d / gen,
                 finalAlive=alive[-1], residualJ=num(per[-1]["residualJ"]))
        m["FND"] = first_round(per, lambda r: num(r["aliveCount"]) < N)
        m["HND"] = first_round(per, lambda r: num(r["aliveCount"]) <= N / 2)
        m["LND"] = first_round(per, lambda r: num(r["aliveCount"]) == 0)
        m.update(deliv_delays)
        return m

    rep = rows(pre + "-reports.csv")
    by_round = defaultdict(list)
    for r in rep:
        if r["fate"] == "delivered":
            by_round[int(r["resolvedRound"])].append(num(r["pathDelayS"]))
    allpd = [x for v in by_round.values() for x in v]
    mo = metrics(per_o, dict(meanDelayRound=st.mean(st.mean(v) for v in by_round.values()), meanDelayPacket=st.mean(allpd)))
    dm_round = [num(r["meanDelayS"]) for r in per_m if num(r["delivered"]) > 0]
    dsum = sum(num(r["meanDelayS"]) * num(r["delivered"]) for r in per_m)
    mm = metrics(per_m, dict(meanDelayRound=st.mean(dm_round), meanDelayPacket=dsum / sum(num(r["delivered"]) for r in per_m)))
    avail = sum(num(r["workloadAvailable"]) for r in per_o)
    mo["validPDR"] = 100 * mo["delivered"] / avail
    mm["validPDR"] = 100 * mm["delivered"] / avail
    spent_m = sum(num(r["spentJ"]) for r in per_m)
    mo["energyPerDeliveredJ"] = sum(spent_o) / max(1, mo["delivered"])
    mm["energyPerDeliveredJ"] = spent_m / max(1, mm["delivered"])
    for k in ["generated", "delivered", "PDR", "validPDR", "sourcePDR", "FND", "HND", "LND", "finalAlive", "residualJ",
              "energyPerDeliveredJ", "meanDelayRound", "meanDelayPacket"]:
        summary[k]["omnet"].append(mo[k]); summary[k]["matlab"].append(mm[k])
    if R == 500:
        ref = {r["seed"]: r for r in rows(os.path.join(REF, "reference_metrics_matlab.csv"))}[str(seed)]
        check(int(ref["matchesPublished"]) == 1, f"seed {seed}: the MATLAB rerun equals the published results_500rounds.mat")
        tol_ok = all(same(mo[k], num(ref[c]), 1e-9) for k, c in [("delivered", "delivered"), ("PDR", "PDR"),
                     ("sourcePDR", "sourcePDR"), ("validPDR", "validPDR"), ("residualJ", "residualJ"),
                     ("energyPerDeliveredJ", "energyPerDeliveredJ"), ("meanDelayRound", "meanDelayRoundS"),
                     ("meanDelayPacket", "meanDelayPacketS")])
        fnd_ok = all(same(mo[k], num(ref[k])) for k in ["FND", "HND", "LND"])
        check(tol_ok and fnd_ok, f"seed {seed}: delivered, PDR, valid-report and source-packet PDR, residual, energy/report, "
                                 f"delays (1e-9 relative) and FND/HND/LND equal to MATLAB extract_metrics")

print("\n".join(lines))
print()
print("| Metric (mean over seeds " + ",".join(map(str, seeds)) + ") | MATLAB V2 | OMNeT++ | max abs difference per seed |")
print("|---|---|---|---|")
for k, v in summary.items():
    a, b = v["matlab"], v["omnet"]
    fin = [(x, y) for x, y in zip(a, b) if not (math.isnan(x) and math.isnan(y))]
    diff = max((abs(x - y) for x, y in fin), default=0.0)
    fmt = (lambda xs: "%.6g" % st.mean([x for x in xs if not math.isnan(x)]) if any(not math.isnan(x) for x in xs) else "none")
    print(f"| {k} | {fmt(a)} | {fmt(b)} | {diff:.3g} |")
print(f"\n{len(lines)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
