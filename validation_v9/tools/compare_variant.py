#!/usr/bin/env python3
"""Paired per-seed comparison of an experimental RL-Hybrid variant against the V2 10-node baseline.

Usage: python3 tools/compare_variant.py <baseline dir> <baseline config> <variant dir> <variant config> <seed> [<seed> ...]
   e.g. python3 tools/compare_variant.py results_v2_10node V2_10Node results_v2_10node_retx1 V2_10Node_Retx1 42 43 44 45 46
Integrity checks on the variant (PASS/FAIL): one fate per report, BS deliveries = delivered fates, end-of-run
energy/slot/invariant checks, and (if retransmission scalars exist) observed decoded retries vs the expected
sum of link qualities. Metrics follow MATLAB extract_metrics; differences are variant - baseline, paired by seed.
"""
import csv, glob, math, os, statistics as st, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
bdir, bcfg, vdir, vcfg = sys.argv[1:5]
seeds = [int(s) for s in sys.argv[5:]]
rows = lambda p: list(csv.DictReader(open(p, newline="")))
num = lambda s: math.nan if (s or "").strip() in ("", "NaN", "nan") else float(s)
fails, lines = [], []


def check(ok, msg):
    lines.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def scalars(d, cfg, s):
    v = {}
    for line in open(glob.glob(os.path.join(d, f"{cfg}-seed={s}-#*.sca"))[0]):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar":
            v[(p[1], p[2])] = float(p[3])
    return v


def metrics(d, cfg, s):
    pre = os.path.join(d, f"{cfg}-seed{s}")
    per, rep = rows(pre + "-per_round.csv"), rows(pre + "-reports.csv")
    sc = scalars(d, cfg, s)
    N = len(rows(pre + "-nodes.csv"))   # network size from the run itself
    dl = [r for r in rep if r["fate"] == "delivered"]
    byr = defaultdict(list)
    for r in dl:
        byr[int(r["resolvedRound"])].append(num(r["pathDelayS"]))
    spent = sum(num(r["txJ"]) + num(r["rxJ"]) + num(r["aggJ"]) for r in per)
    d_ = sum(int(r["delivered"]) for r in per)
    g = sum(int(r["sourceAvailable"]) for r in per)
    m = dict(generated=g, delivered=d_,
             validPDR=100 * d_ / sum(int(r["workloadAvailable"]) for r in per),
             schedPDR=100 * d_ / sum(int(r["scheduled"]) for r in per), sourcePDR=100 * d_ / g,
             residualJ=num(per[-1]["residualJ"]), eprMJ=1000 * spent / d_, alive=int(per[-1]["aliveCount"]),
             FND=next((int(r["round"]) for r in per if int(r["aliveCount"]) < N), math.nan),
             delayPacketMs=1000 * st.mean(num(r["pathDelayS"]) for r in dl),
             delayRoundMs=1000 * st.mean(st.mean(v) for v in byr.values()),
             frames=sum(int(r["physicalFrames"]) for r in per),
             lossChannel=sum(int(r["lossChannel"]) for r in per), lossNoCand=sum(int(r["lossNoCandidate"]) for r in per),
             unattempted=sum(int(r["unattempted"]) for r in per),
             sourceDown=sum(int(r["workloadAvailable"]) - int(r["sourceAvailable"]) for r in per),
             retxSent=sc.get(("PeriyarRiverNetwork.controller", "retransmissionsSent"), 0.0),
             retxDecoded=sc.get(("PeriyarRiverNetwork.controller", "retransmissionsDecoded"), 0.0))
    # integrity
    idx = [r["reportIndex"] for r in rep]
    fates_ok = len(idx) == len(set(idx)) and sc[("PeriyarRiverNetwork.BS", "deliveredReports")] == len(dl) == d_
    summ = open(pre + "-summary.txt").read()
    inv_ok = "energy closes OK; slot accounting OK; per-round MATLAB invariants OK" in summ
    exp = sc.get(("PeriyarRiverNetwork.controller", "retransmissionsExpectedDecoded"))
    var = sc.get(("PeriyarRiverNetwork.controller", "retransmissionsDecodedVariance"))
    return m, fates_ok, inv_ok, exp, var


B, V = {}, {}
for s in seeds:
    B[s], bf, bi, _, _ = metrics(bdir, bcfg, s)
    V[s], vf, vi, exp, var = metrics(vdir, vcfg, s)
    check(vf and vi and bf and bi, f"seed {s}: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)")
    if exp is not None:
        z = (V[s]["retxDecoded"] - exp) / math.sqrt(var) if var else 0
        check(abs(z) < 4 and V[s]["retxDecoded"] <= V[s]["retxSent"], f"seed {s}: {V[s]['retxDecoded']:.0f} of {V[s]['retxSent']:.0f} retries decoded (must be <= sent); expected "
                          f"{exp:.1f} from the link qualities (z = {z:+.2f})")

keys = [("generated", "%.0f"), ("delivered", "%.0f"), ("validPDR", "%.2f"), ("schedPDR", "%.2f"), ("sourcePDR", "%.2f"),
        ("residualJ", "%.3f"), ("eprMJ", "%.3f"), ("FND", "%.0f"), ("alive", "%.0f"), ("delayPacketMs", "%.2f"),
        ("delayRoundMs", "%.2f"), ("frames", "%.0f"), ("retxSent", "%.0f"), ("lossChannel", "%.0f"), ("lossNoCand", "%.0f"),
        ("unattempted", "%.0f"), ("sourceDown", "%.0f")]
print("\n".join(lines))
print(f"\n{len(lines)} checks, {len(fails)} failed\n")
print("| Metric | " + " | ".join(f"seed {s} (base / var / diff)" for s in seeds) + " | mean base | mean variant | paired diff mean ± sd | seeds improved* |")
print("|---" * (len(seeds) + 5) + "|")
better_high = {"generated", "delivered", "validPDR", "schedPDR", "sourcePDR", "residualJ", "FND", "alive"}
better_low = {"eprMJ", "delayPacketMs", "delayRoundMs", "lossChannel", "lossNoCand", "unattempted", "sourceDown"}
for k, f in keys:
    cells = []
    diffs = []
    for s in seeds:
        a, b = B[s][k], V[s][k]
        diffs.append(b - a)
        cells.append(f"{f % a} / {f % b} / {('%+' + f[1:]) % (b - a)}")
    mb, mv = st.mean(B[s][k] for s in seeds), st.mean(V[s][k] for s in seeds)
    imp = ("%d/5" % sum(1 for x in diffs if (x > 0 if k in better_high else x < 0))) if (k in better_high or k in better_low) else "–"
    print(f"| {k} | " + " | ".join(cells) + f" | {f % mb} | {f % mv} | {('%+' + f[1:]) % st.mean(diffs)} ± {f % st.stdev(diffs)} | {imp} |")
print("\n* seeds where the variant is better (higher for delivery/energy left/FND/alive, lower for energy per report, delay, losses)")
sys.exit(1 if fails else 0)
