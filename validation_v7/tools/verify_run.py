#!/usr/bin/env python3
"""Stage E: internal consistency checks of OMNeT++ runs (independent of MATLAB).

Usage: python3 tools/verify_run.py <Config> <seed> [<seed> ...]
"""
import csv, glob, math, os, re, sys
from collections import Counter

RES = "results"
config, seeds = sys.argv[1], [int(s) for s in sys.argv[2:]]
out, fails = [], []

def check(ok, msg):
    out.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)

def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

for seed in seeds:
    pre = os.path.join(RES, f"{config}-seed{seed}")
    met = rows(pre + "-metrics.csv")[0]
    rep = rows(pre + "-reports.csv")
    dec = rows(pre + "-decisions.csv")
    ev = rows(pre + "-unavailability_events.csv")
    S = lambda k: float(met[k])

    # E1 each valid-data slot has exactly one fate; slot accounting
    idx = [int(r["reportIndex"]) for r in rep]
    fates = Counter(r["fate"] for r in rep)
    check(len(idx) == len(set(idx)) == 9825 and sorted(idx) == list(range(1, 9826)),
          f"seed {seed}: E1 every one of the 9825 valid-data slots has exactly one recorded fate")
    emitted = len(rep) - fates["source_unavailable"]
    losses = sum(v for k, v in fates.items() if k.startswith("lost_"))
    check(S("scheduled") == 10000 and S("workloadAvailable") == 9825 and S("sourceAvailable") == emitted
          and emitted == fates["delivered"] + losses + fates["unattempted"]
          and S("delivered") == fates["delivered"] and S("stageLoss") == losses and S("unattempted") == fates["unattempted"],
          f"seed {seed}: E1 10000 slots = 175 pre-observation + 9825 data; 9825 = {fates['source_unavailable']} source-down + "
          f"{emitted} emitted; emitted = {fates['delivered']} delivered + {losses} lost + {fates['unattempted']} unattempted")
    # E2 denominators
    check(fates["delivered"] <= emitted and abs(S("PDR") - 100.0 * fates["delivered"] / 10000) < 1e-9,
          f"seed {seed}: E2 delivered <= emitted, PDR = delivered / 10000 scheduled = {S('PDR'):.3f} % "
          f"(conditional delivered/emitted = {100.0 * fates['delivered'] / emitted:.3f} % reported separately)")
    # E3 energy per node from scalars
    sca = glob.glob(os.path.join(RES, f"{config}-seed={seed}-#*.sca"))
    vals = {}
    for line in open(sca[0]):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar":
            vals[(p[1], p[2])] = float(p[3])
    # MATLAB node K = module node[K-1] (current NED) or nK (results written before 2026-11-06)
    nodes = [f"PeriyarRiverNetwork.node[{i}]" if ("PeriyarRiverNetwork.node[0]", "residualEnergy") in vals
             else f"PeriyarRiverNetwork.n{i + 1}" for i in range(50)]
    worst = max(abs((2.0 - vals[(n, "residualEnergy")]) - (vals[(n, "txEnergy")] + vals[(n, "rxEnergy")] + vals[(n, "aggregationEnergy")])) for n in nodes)
    spent = sum(vals[(n, "txEnergy")] + vals[(n, "rxEnergy")] + vals[(n, "aggregationEnergy")] for n in nodes)
    resid = sum(vals[(n, "residualEnergy")] for n in nodes)
    check(worst < 1e-9 and abs(spent - S("spentJ")) < 1e-8 and abs(spent + resid - 100.0) < 1e-8,
          f"seed {seed}: E3 energy reconciles per node (max |E0-residual-(tx+rx+agg)| = {worst:.1e} J); "
          f"spent {spent:.6f} + residual {resid:.6f} = 100 J budget")
    check(vals[("PeriyarRiverNetwork.BS", "deliveredReports")] == fates["delivered"],
          f"seed {seed}: E3 BS counted {int(vals[('PeriyarRiverNetwork.BS', 'deliveredReports')])} delivered reports = report log")
    # E4 no unavailable node acts or is chosen
    tu = {}
    for e in ev:
        tu.setdefault(int(e["node"]), float(e["simTime"]))
    acts_after = [r for r in dec if int(r["actor"]) in tu and float(r["decisionTime"]) > tu[int(r["actor"])]]
    chosen_after = [r for r in dec if int(r["target"]) <= 50 and int(r["target"]) != int(r["actor"])
                    and int(r["target"]) in tu and tu[int(r["target"])] < float(r["decisionTime"])]
    check(not acts_after and not chosen_after,
          f"seed {seed}: E4 no node acts after it became unavailable ({len(tu)} nodes became unavailable; "
          f"{len(acts_after)} late actions, {len(chosen_after)} choices of an unavailable target)")
    # E5 TTL
    max_hop = max(int(r["hop"]) for r in dec)
    max_deliv = max(int(r["hops"]) for r in rep if r["fate"] == "delivered")
    check(max_hop <= 15 and max_deliv <= 16,
          f"seed {seed}: E5 TTL respected: largest route hop {max_hop} <= 15, largest delivered hop count {max_deliv} "
          f"(<= 15 route hops + 1 member hop); TTL losses {fates['lost_ttl']}")
    # E6 Q-table dimensions and learning activity
    states = [int(r["state"]) for r in dec]
    targets = [int(r["target"]) for r in dec]
    selfok = all(int(r["target"]) == int(r["actor"]) for r in dec if r["hopType"] == "0")
    check(min(states) >= 1 and max(states) <= 6561 and min(targets) >= 1 and max(targets) <= 51 and selfok,
          f"seed {seed}: E6 every action indexes Q(state 1..6561, action 1..51); {len(set(states))} distinct states visited; "
          f"self-head actions target the actor")
    qrows = sum(int(float(vals[(n, 'qUpdates')])) for n in nodes)
    check(qrows == int(S("qUpdates")) > 0 and int(S("explorations")) > 0,
          f"seed {seed}: E6 Q-learning active: {qrows} updates summed over the 50 per-node tables = network total; "
          f"{int(S('explorations'))} exploratory and {int(S('exploitations'))} greedy decisions")
    # E7 log consistency: hop types and channel outcomes vs frame counters
    ht = Counter(r["hopType"] for r in dec)
    member_ok = sum(1 for r in dec if r["hopType"] == "1" and r["outcome"] == "1")
    check(ht["1"] + ht["2"] + ht["3"] == int(S("physicalFrames")),
          f"seed {seed}: E7 logged radio actions (member {ht['1']}, relay {ht['2']}, to BS {ht['3']}) = physical frames "
          f"{int(S('physicalFrames'))}; self-head choices {ht['0']}; decoded member frames {member_ok}")

    # E8 roles: exactly 10 data-generating sources, 40 relay-only nodes, one BS
    sources = sorted({int(r["sourceNode"]) for r in rep})
    source_actors = sorted({int(r["actor"]) for r in dec if r["hopType"] in ("0", "1")})
    node_modules = sum(1 for n in nodes if (n, "residualEnergy") in vals)
    bs_modules = sum(1 for (m, k) in vals if k == "deliveredReports" and m.endswith(".BS"))
    check(sources == [4, 8, 12, 18, 22, 28, 32, 38, 42, 48] and set(source_actors) <= set(sources)
          and node_modules == 50 and bs_modules == 1,
          f"seed {seed}: E8 roles: reports generated only by {len(sources)} sensing nodes {sources}; source actions only by them; "
          f"{50 - len(sources)} relay-only nodes; {node_modules} battery-node modules + {bs_modules} BS")

print("\n".join(out))
print(f"\n{len(out)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
