#!/usr/bin/env python3
"""Stage C/D: compare OMNeT++ runs with the frozen MATLAB RL-Hybrid results, seed by seed.

Usage: python3 tools/compare_with_matlab.py <Config> <seed> [<seed> ...]
  e.g. python3 tools/compare_with_matlab.py SmokeSeed42 42
       python3 tools/compare_with_matlab.py FiveSeeds 42 43 44 45 46

For each seed it compares
  1. the decision trace row by row with MATLAB res.decisionLog (round, hop type, actor, target,
     reports, causal qHat, prior, own attempts/successes before the action, actor/target energy,
     channel outcome) and reports the first divergence, if any;
  2. the per-round series (delivered, operational nodes, residual energy, Q updates,
     explorations, epsilon);
  3. per-node first-unavailable round and reason;
  4. the headline metrics (MATLAB definitions).
Numbers are compared with a relative tolerance of 1e-9 (identical code paths give identical
doubles; the tolerance only absorbs text formatting).
"""
import csv, math, os, sys

REF = os.path.join("matlab_reference", "data")
RES = "results"

def close(a, b, rel=1e-9, ab=1e-12):
    a, b = float(a), float(b)
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= max(ab, rel * max(abs(a), abs(b)))

def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

config, seeds = sys.argv[1], [int(s) for s in sys.argv[2:]]
out, fails = [], []
def check(ok, msg):
    out.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)

INT_COLS = ["round", "hopType", "actor", "target", "reports", "attemptsBefore", "successesBefore"]
NUM_COLS = ["qHat", "prior", "actorE", "targetE", "outcome"]
METRICS = ["scheduled", "workloadAvailable", "sourceAvailable", "attempts", "unattempted", "delivered", "stageLoss",
           "lossNoCandidate", "lossChannel", "lossEnergy", "lossTTL", "PDR", "FND", "finalAlive", "residualJ", "spentJ",
           "energyPerDeliveredJ", "meanHops", "meanDelayS", "qUpdates", "explorations", "exploitations", "physicalFrames"]
mref = {int(r["seed"]): r for r in rows(os.path.join(REF, "reference_metrics_matlab.csv"))}

for seed in seeds:
    pre = os.path.join(RES, f"{config}-seed{seed}")
    # 1. decision trace
    m = rows(os.path.join(REF, f"decisions_matlab_seed{seed}.csv"))
    o = rows(pre + "-decisions.csv")
    first = None
    for i, (a, b) in enumerate(zip(m, o)):
        bad = [c for c in INT_COLS if int(float(a[c])) != int(float(b[c]))] + \
              [c for c in NUM_COLS if not close(a[c], b[c])]
        if bad:
            first = (i, bad, a, b)
            break
    same = first is None and len(m) == len(o)
    msg = f"seed {seed}: decision trace {len(o)} rows vs MATLAB {len(m)} rows"
    if first:
        i, bad, a, b = first
        msg += f"; FIRST DIVERGENCE at row {i + 1} (round {a['round']}) in {bad}: MATLAB {dict((c, a[c]) for c in bad)} vs OMNeT++ {dict((c, b[c]) for c in bad)}"
    elif len(m) != len(o):
        msg += "; identical over the common prefix but lengths differ"
    else:
        msg += " -> IDENTICAL (every action, causal estimate, energy and channel outcome)"
    check(same, msg)
    # 2. per-round series
    mr, orr = rows(os.path.join(REF, f"per_round_matlab_seed{seed}.csv")), rows(pre + "-per_round.csv")
    bad_rounds = [a["round"] for a, b in zip(mr, orr)
                  if not all(close(a[c], b[c]) for c in ["delivered", "aliveCount", "residualJ", "qUpdates", "explorations", "epsilon"])]
    check(len(mr) == len(orr) == 1000 and not bad_rounds,
          f"seed {seed}: per-round delivered/operational nodes/residual energy/Q-updates/explorations/epsilon identical in all 1000 rounds"
          + (f" (first differing round {bad_rounds[0]}, {len(bad_rounds)} differ)" if bad_rounds else ""))
    # 3. unavailability
    mu, ou = rows(os.path.join(REF, f"unavailability_matlab_seed{seed}.csv")), rows(pre + "-unavailability.csv")
    bad_nodes = [a["node"] for a, b in zip(mu, ou)
                 if not close(a["firstUnavailableRound"], b["firstUnavailableRound"]) or a["reason"] != b["reason"]]
    nun = sum(1 for a in mu if a["firstUnavailableRound"] not in ("NaN", "nan"))
    check(not bad_nodes, f"seed {seed}: first-unavailable round and reason identical for all 50 nodes ({nun} became unavailable)"
          + (f"; differ: {bad_nodes}" if bad_nodes else ""))
    # 4. metrics
    om = rows(pre + "-metrics.csv")[0]
    diffs = [f"{k}: MATLAB {mref[seed][k]} vs OMNeT++ {om[k]}" for k in METRICS if not close(mref[seed][k], om[k], rel=1e-8)]
    check(not diffs, f"seed {seed}: all {len(METRICS)} headline metrics equal to the frozen MATLAB result" + ("; " + "; ".join(diffs) if diffs else ""))

print("\n".join(out))
print(f"\n{len(out)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
