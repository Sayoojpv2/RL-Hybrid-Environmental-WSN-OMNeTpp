#!/usr/bin/env python3
"""Stage D: five-seed table (mean +/- sample std, n-1) for OMNeT++ and the frozen MATLAB result.

Usage: python3 tools/five_seed_table.py [Config]   (default FiveSeeds) -> prints Markdown
"""
import csv, glob, os, statistics as st, sys

sys.stdout.reconfigure(encoding="utf-8")
config = sys.argv[1] if len(sys.argv) > 1 else "FiveSeeds"
SEEDS = [42, 43, 44, 45, 46]

def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

ref = {int(r["seed"]): r for r in rows(os.path.join("matlab_reference", "data", "reference_metrics_matlab.csv"))}
omn = {s: rows(os.path.join("results", f"{config}-seed{s}-metrics.csv"))[0] for s in SEEDS}
lat = {}
for s in SEEDS:   # OMNeT++-only latency (round start -> BS), from the scalar file
    for line in open(glob.glob(os.path.join("results", f"{config}-seed={s}-#*.sca"))[0]):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar" and p[1] == "PeriyarRiverNetwork.BS" and p[2] == "latency:mean":
            lat[s] = float(p[3])

def ms(vals, fmt):
    return (fmt % st.mean(vals)) + " ± " + (fmt % st.stdev(vals))

metrics = [("Scheduled report slots", "scheduled", "%.0f", 1), ("Slots with valid data", "workloadAvailable", "%.0f", 1),
           ("Reports emitted (source available)", "sourceAvailable", "%.1f", 1), ("Reports delivered", "delivered", "%.1f", 1),
           ("PDR = delivered / scheduled (%)", "PDR", "%.3f", 1), ("Network losses (all causes)", "stageLoss", "%.1f", 1),
           ("  - channel", "lossChannel", "%.1f", 1), ("  - energy", "lossEnergy", "%.1f", 1),
           ("  - no feasible candidate", "lossNoCandidate", "%.1f", 1), ("  - TTL (15 hops)", "lossTTL", "%.1f", 1),
           ("Unattempted reports", "unattempted", "%.1f", 1), ("First node unavailable, FND (round)", "FND", "%.1f", 1),
           ("Final operational nodes", "finalAlive", "%.2f", 1), ("Residual energy (J)", "residualJ", "%.2f", 1),
           ("Energy per delivered report (J)", "energyPerDeliveredJ", "%.5f", 1), ("Mean delivered hops", "meanHops", "%.2f", 1),
           ("Mean path delay (s, MATLAB definition)", "meanDelayS", "%.5f", 1), ("Q-table updates", "qUpdates", "%.1f", 1),
           ("Exploratory decisions", "explorations", "%.1f", 1)]
print("| Metric | OMNeT++ (5 seeds) | MATLAB frozen (5 seeds) | Identical per seed? |")
print("|---|---|---|---|")
for label, key, fmt, _ in metrics:
    o = [float(omn[s][key]) for s in SEEDS]
    m = [float(ref[s][key]) for s in SEEDS]
    same = all(abs(a - b) <= 1e-8 * max(1, abs(b)) for a, b in zip(o, m))
    print(f"| {label} | {ms(o, fmt)} | {ms(m, fmt)} | {'yes' if same else 'NO'} |")
print(f"| Mean latency round-start→BS (s, OMNeT++ only, not comparable) | {ms([lat[s] for s in SEEDS], '%.3f')} | – | n/a |")
print()
print("Per seed (OMNeT++): " + "; ".join(
    f"seed {s}: PDR {float(omn[s]['PDR']):.2f} %, delivered {omn[s]['delivered']}, FND {omn[s]['FND']}, "
    f"final nodes {omn[s]['finalAlive']}, residual {float(omn[s]['residualJ']):.3f} J" for s in SEEDS))
