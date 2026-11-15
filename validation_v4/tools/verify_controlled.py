#!/usr/bin/env python3
"""v2 checks for the controlled design (Ctrl50/100/250/500, run seeds 42-46) and the placement runs (Place250).

Usage: python3 tools/verify_controlled.py      (run from the project folder; prints PASS/FAIL lines)

Per run:
  C1  exactly N battery-node modules and one BS
  C2  design file: run seed, topologySeed 42, the expected extraTopologySeed, channelStream independent
  C3  nodes 1..50 bit-identical to MATLAB generate_scenario(42); added relays inside 600 x 50 m, all distinct
  C4  workload identical to the MATLAB Periyar workload; only the 10 stations originate reports or source actions
  C5  every target in 1..N+1, to-BS actions target N+1, states in 1..6561
  C6  per-node and network energy closure (2 J x N)
  C7  accounting: 10 x rounds slots, emitted = delivered + lost + unattempted, BS count matches
  C8  no action by or towards an unavailable node; route hop <= 15 (TTL)
  C9  every round inside its 10 s slot; Q-updates and explorations > 0
  C10 diagnostics: one hops.csv row per real transmission in decisions.csv, same outcome, trueLQ in [0.1, 0.95]
Across runs:
  X1  the topology (all N coordinates) is identical for run seeds 42-46 at each N
  X2  nesting: N=100 relays = first 50 relays of N=250 and N=500; N=250 relays = first 200 of N=500
  X3  run seeds give different random paths (decision traces differ pairwise)
  X4  Place250 with extraTopologySeed 900042 reproduces Ctrl250 run seed 42 byte for byte
  X5  Place250 placements: nodes 1..50 identical, added relays differ between the five topology seeds
"""
import csv, filecmp, glob, os, sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
REF = os.path.join("matlab_reference", "data")
STATIONS = {4, 8, 12, 18, 22, 28, 32, 38, 42, 48}
SEEDS = [42, 43, 44, 45, 46]
out, fails = [], []


def check(ok, msg):
    out.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


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


MAT42 = rows(os.path.join(REF, "nodes_seed42.csv"))
WM = rows(os.path.join(REF, "workload_matlab.csv"))


def verify_run(tag, pre, sca, N, seed, extra):
    vals = scalars(sca)
    node_mods = sorted({m for (m, k) in vals if k == "residualEnergy" and (".n" in m or ".relay[" in m)})
    bs_mods = {m for (m, k) in vals if k == "deliveredReports" and m.endswith(".BS")}
    check(len(node_mods) == N and len(bs_mods) == 1, f"{tag}: C1 {len(node_mods)} battery nodes (expected {N}), {len(bs_mods)} BS")

    d = dict(l.split(" ", 1) for l in open(pre + "-design.txt").read().strip().splitlines())
    d = {k: v.strip() for k, v in d.items()}
    check(d["runSeed"] == str(seed) and d["topologySeed"] == "42" and d["extraTopologySeed"] == str(extra)
          and d["channelStream"] == "independent" and d["numNodes"] == str(N) and d["channelSeedRound1"] == str(1000000 * seed + 1),
          f"{tag}: C2 design run seed {d['runSeed']}, topology 42, relays {d['extraTopologySeed']}, channel {d['channelStream']} "
          f"(round-1 channel seed {d['channelSeedRound1']})")

    nodes = rows(pre + "-nodes.csv")
    first50 = all(float(a["x"]) == float(b["x"]) and float(a["y"]) == float(b["y"]) for a, b in zip(nodes[:50], MAT42))
    pts = [(float(r["x"]), float(r["y"])) for r in nodes]
    inside = all(0 < x < 600 and 0 < y < 50 for x, y in pts[50:])
    check(len(nodes) == N and first50 and inside and len(set(pts)) == N,
          f"{tag}: C3 nodes 1..50 = MATLAB layout 42; {N - 50} added relays inside the area, all distinct")

    wl = rows(pre + "-workload.csv")
    same_wl = len(wl) == len(WM) and all(a[k] == b[k] for a, b in zip(wl, WM) for k in ["reportIndex", "round", "sourceNode", "station", "date"]) \
        and all(float(a[k]) == float(b[k]) for a, b in zip(wl, WM) for k in ["temperature", "pH", "conductivity", "TDS"])
    rep = rows(pre + "-reports.csv")
    dec = rows(pre + "-decisions.csv")
    srcs = {int(r["sourceNode"]) for r in rep}
    bad_src = [r for r in dec if r["hopType"] in ("0", "1") and int(r["actor"]) not in STATIONS]
    check(same_wl and srcs <= STATIONS and not bad_src, f"{tag}: C4 workload = MATLAB (9825 reports); sources {len(srcs)} stations; "
                                                      f"{len(bad_src)} source actions by non-stations")

    targets = [int(r["target"]) for r in dec]
    states = [int(r["state"]) for r in dec]
    check(min(targets) >= 1 and max(targets) <= N + 1 and all(int(r["target"]) == N + 1 for r in dec if r["hopType"] == "3")
          and 1 <= min(states) and max(states) <= 6561, f"{tag}: C5 targets 1..{N + 1}, states 1..6561")

    E0 = 2.0
    worst = max(abs((E0 - vals[(m, "residualEnergy")]) - (vals[(m, "txEnergy")] + vals[(m, "rxEnergy")] + vals[(m, "aggregationEnergy")])) for m in node_mods)
    spent = sum(vals[(m, "txEnergy")] + vals[(m, "rxEnergy")] + vals[(m, "aggregationEnergy")] for m in node_mods)
    resid = sum(vals[(m, "residualEnergy")] for m in node_mods)
    met = rows(pre + "-metrics.csv")[0]
    check(worst < 1e-9 and abs(spent + resid - E0 * N) < 1e-7 and abs(spent - float(met["spentJ"])) < 1e-8,
          f"{tag}: C6 energy closes (max node error {worst:.1e} J)")

    per = rows(pre + "-per_round.csv")
    fates = Counter(r["fate"] for r in rep)
    emitted = len([r for r in rep if int(r["round"]) <= len(per)]) - fates["source_unavailable"]
    lost = sum(v for k, v in fates.items() if k.startswith("lost_"))
    idx = [int(r["reportIndex"]) for r in rep]
    check(len(idx) == len(set(idx)) and int(met["scheduled"]) == 10 * len(per) == 10000 and emitted == int(met["sourceAvailable"])
          and emitted == fates["delivered"] + lost + fates["unattempted"] and fates["delivered"] == int(met["delivered"])
          and vals[("PeriyarRiverNetwork.BS", "deliveredReports")] == fates["delivered"],
          f"{tag}: C7 10000 slots; {emitted} emitted = {fates['delivered']} delivered + {lost} lost + {fates['unattempted']} unattempted")

    tu = {}
    for e in rows(pre + "-unavailability_events.csv"):
        tu.setdefault(int(e["node"]), float(e["simTime"]))
    late = [r for r in dec if int(r["actor"]) in tu and float(r["decisionTime"]) > tu[int(r["actor"])]]
    chosen = [r for r in dec if int(r["target"]) <= N and r["target"] != r["actor"] and int(r["target"]) in tu
              and tu[int(r["target"])] < float(r["decisionTime"])]
    check(not late and not chosen and max(int(r["hop"]) for r in dec) <= 15,
          f"{tag}: C8 {len(tu)} nodes unavailable; {len(late)} late actions, {len(chosen)} unavailable targets; TTL respected")

    over = max(float(r["roundEndTime"]) - 10.0 * (int(r["round"]) - 1) for r in per)
    check(over < 10.0 and int(met["qUpdates"]) > 0 and int(met["explorations"]) > 0, f"{tag}: C9 longest round {over:.2f} s of 10 s")

    hops = rows(pre + "-hops.csv")
    tx = [r for r in dec if r["target"] != r["actor"]]
    same = len(hops) == len(tx) and all(h["actor"] == t["actor"] and h["target"] == t["target"] and h["round"] == t["round"]
                                        and float(h["outcome"]) == float(t["outcome"]) for h, t in zip(hops, tx))
    lq_ok = all(0.1 - 1e-12 <= float(h["trueLQ"]) <= 0.95 + 1e-12 for h in hops)
    check(same and lq_ok, f"{tag}: C10 {len(hops)} transmissions logged with true link quality, matching decisions.csv")
    return pts, dec


topo = {}
traces = {}
for N in [50, 100, 250, 500]:
    for s in SEEDS:
        pre = f"results_controlled/Ctrl{N}-seed{s}"
        sca = glob.glob(f"results_controlled/Ctrl{N}-seed={s}-#*.sca")[0]
        pts, dec = verify_run(f"Ctrl{N} seed {s}", pre, sca, N, s, 900042)
        topo[(N, s)] = pts
        traces[(N, s)] = [(r["round"], r["actor"], r["target"], r["outcome"]) for r in dec]
    check(all(topo[(N, s)] == topo[(N, 42)] for s in SEEDS), f"X1 N={N}: topology identical for run seeds 42-46")
    diffs = sum(1 for a in SEEDS for b in SEEDS if a < b and traces[(N, a)] != traces[(N, b)])
    check(diffs == 10, f"X3 N={N}: decision traces differ for all {diffs} of 10 seed pairs")

t = {N: topo[(N, 42)] for N in [50, 100, 250, 500]}
check(t[100] == t[250][:100] == t[500][:100] and t[250] == t[500][:250] and t[50] == t[100][:50],
      "X2 nesting: N=50 ⊂ N=100 ⊂ N=250 ⊂ N=500 (same ids, same coordinates)")

place = {}
for e in [900042, 910001, 910002, 910003, 910004]:
    pre = f"results_placement/Place250-topo{e}-seed42"
    sca = glob.glob(f"results_placement/Place250-seed=42,topo={e}-#*.sca")[0]
    pts, _ = verify_run(f"Place250 topo {e}", pre, sca, 250, 42, e)
    place[e] = pts
same_files = all(filecmp.cmp(f"results_placement/Place250-topo900042-seed42-{k}", f"results_controlled/Ctrl250-seed42-{k}", shallow=False)
                 for k in ["metrics.csv", "decisions.csv", "reports.csv", "hops.csv", "nodes.csv", "per_round.csv"])
check(same_files, "X4 Place250 topo 900042 = Ctrl250 run seed 42 (6 output files byte-identical)")
keys = list(place)
check(all(place[k][:50] == place[keys[0]][:50] for k in keys)
      and all(place[a][50:] != place[b][50:] for a in keys for b in keys if a < b),
      "X5 placements: nodes 1..50 identical; added relays differ for every pair of topology seeds")

print("\n".join(out))
print(f"\n{len(out)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
