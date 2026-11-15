#!/usr/bin/env python3
"""Stage B: compare the OMNeT++ workload / topology / channel with the frozen MATLAB export.

Usage: python3 tools/compare_reference.py [resultsDir] [matlabDataDir]
Exact comparisons: every workload field (numbers compared as IEEE doubles), every node
coordinate (bit-exact), every success_history bit for all 1000 rounds of seeds 42-46.
Also checks the expected counts and the causal (no future data) property of the workload.
"""
import csv, os, sys
from collections import Counter, defaultdict

res = sys.argv[1] if len(sys.argv) > 1 else "results"
ref = sys.argv[2] if len(sys.argv) > 2 else os.path.join("matlab_reference", "data")
SEEDS = [42, 43, 44, 45, 46]
lines, fails = [], []

def check(ok, msg):
    lines.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)

def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

# ---- workload (identical for every seed; compare each seed's export with MATLAB)
mw = rows(os.path.join(ref, "workload_matlab.csv"))
num_fields = ["temperature", "pH", "conductivity", "TDS"]
for seed in SEEDS:
    ow = rows(os.path.join(res, f"ReferenceCheck-seed{seed}-workload.csv"))
    diff = 0
    for a, b in zip(mw, ow):
        for k in ["reportIndex", "round", "sourceNode", "station", "date"]:
            if a[k] != b[k]:
                diff += 1
        for k in num_fields:
            if float(a[k]) != float(b[k]):
                diff += 1
    check(len(mw) == len(ow) and diff == 0,
          f"seed {seed}: workload identical to MATLAB ({len(ow)} reports, {diff} field differences)")

ow = rows(os.path.join(res, "ReferenceCheck-seed42-workload.csv"))
summary = open(os.path.join(res, "ReferenceCheck-seed42-workload_summary.txt")).read().split()
msum = open(os.path.join(ref, "workload_summary_matlab.txt")).read().split()
check(summary == msum, "workload summary (counts, r_events milestones, station order, node ids) identical to MATLAB")
s = open(os.path.join(res, "ReferenceCheck-seed42-workload_summary.txt")).read().splitlines()[0]
check(s.startswith("raw 1273 valid 1251 dates 212 scheduled 10000 available 9825 unavailable 175"),
      f"expected counts: {s}")

# station -> node mapping and per-round structure
mapping = {r["station"]: int(r["sourceNode"]) for r in ow}
expected = {"ALUVA - MANAPPURAM": 4, "PURAPILLIKADAVU US": 8, "PURAPILLIKADAVU BUND NAVIGATION": 12,
            "PURAPILLIKADAVU BUND DS": 18, "PATHALAM BUND U/S": 22, "PATHALAM BUND D/S": 28,
            "PATHALAM BRIDGE": 32, "PUTHALAM KADAVU": 38, "MANJUMMAL BUND": 42, "VETTUKADAVU": 48}
check(mapping == expected, f"station -> node mapping as in create_periyar_workload_continuous.m: {mapping}")
per_round = Counter(int(r["round"]) for r in ow)
check(max(per_round.values()) <= 10 and len(per_round) == 1000, "at most one report per station per round, all 1000 rounds present")
per_station_round = Counter((r["station"], r["round"]) for r in ow)
check(max(per_station_round.values()) == 1, "no station emits twice in a round")

# causality: the observation date carried in round r must map to a milestone <= r
milestones = [int(x) for x in summary[summary.index("r_events") + 1: summary.index("r_events") + 213]]
dates = sorted({r["date"] for r in ow} | set())
# rebuild date -> milestone from the clean data set in the CSV (dates present in any station)
import datetime
clean_dates = set()
with open(os.path.join("data", "Periyar_WaterQuality_Project.csv"), newline="") as f:
    for r in csv.DictReader(f):
        try:
            t, ph, c, tds = (float(r[k]) if r[k] else float("nan") for k in ["Temperature", "pH", "Conductivity", "TDS"])
        except ValueError:
            continue
        if 15 <= t <= 50 and 0 <= ph <= 14 and c > 0 and tds > 0:
            clean_dates.add(r["Date"])
date_round = dict(zip(sorted(clean_dates), milestones))
leaks = [r for r in ow if date_round[r["date"]] > int(r["round"])]
check(len(clean_dates) == 212 and not leaks, f"no future observation used: {len(leaks)} reports carry a date after their round")
first = defaultdict(lambda: 10**9)
for r in ow:
    first[r["station"]] = min(first[r["station"]], int(r["round"]))
pre = sum(fr - 1 for fr in first.values())
check(pre == 175, f"pre-first-observation slots = sum over stations of (first round - 1) = {pre}")

# ---- topology and channel per seed
for seed in SEEDS:
    mn = rows(os.path.join(ref, f"nodes_seed{seed}.csv"))
    on = rows(os.path.join(res, f"ReferenceCheck-seed{seed}-nodes.csv"))
    nd = sum(1 for a, b in zip(mn, on) if float(a["x"]) != float(b["x"]) or float(a["y"]) != float(b["y"]))
    check(len(mn) == len(on) == 50 and nd == 0, f"seed {seed}: 50 node coordinates bit-identical to generate_scenario.m ({nd} differ)")
    a = open(os.path.join(ref, f"success_seed{seed}.bin"), "rb").read()
    b = open(os.path.join(res, f"ReferenceCheck-seed{seed}-success.bin"), "rb").read()
    nb = sum(1 for x, y in zip(a, b) if x != y)
    check(len(a) == len(b) == 50 * 51 * 1000 and nb == 0,
          f"seed {seed}: all {len(a)} success_history bits (50 x 51 x 1000) identical ({nb} differ)")

print("\n".join(lines))
print(f"\n{len(lines)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
