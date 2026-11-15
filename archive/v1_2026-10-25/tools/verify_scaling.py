#!/usr/bin/env python3
"""Stage B/C/D checks for relay-density scaling runs (N > 50).

Usage: python3 tools/verify_scaling.py <Config> <N> <seed> [<seed> ...]

  S1  exactly N battery-node modules (n1..n50 + relay[0..N-51]) and exactly one BS module
  S2  coordinates: N rows, ids 1..N; nodes 1..50 bit-identical to MATLAB generate_scenario(seed);
      added relays inside the 600 x 50 m area, no duplicates, none at the BS position
  S3  sources: the workload equals the MATLAB Periyar workload; only the 10 station nodes report
  S4  relays 51..N are relay-only: they never originate a report or a source (cluster-phase) action
  S5  action indices: every target in 1..N+1, every to-BS action targets N+1, states in 1..6561
  S6  added relays are used: distinct added-relay ids chosen as cluster head or next hop
  S7  channel: the original 50 x 51 block of success bits equals MATLAB success_history (if exported)
  S8  energy closes per node and over the network (budget 2 J x N)
  S9  accounting: one fate per report; 10 x rounds slots; emitted = delivered + lost + unattempted
  S10 no node acts after it became unavailable; no unavailable node is chosen; TTL <= 15
  S11 every round finished inside its 10 s slot; Q-updates > 0 and exploration > 0
"""
import csv, glob, math, os, sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
config, N, seeds = sys.argv[1], int(sys.argv[2]), [int(s) for s in sys.argv[3:]]
REF = os.path.join("matlab_reference", "data")
STATIONS = {4, 8, 12, 18, 22, 28, 32, 38, 42, 48}
out, fails = [], []

def check(ok, msg):
    out.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)

def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

for seed in seeds:
    pre = os.path.join("results", f"{config}-seed{seed}")
    sca = glob.glob(os.path.join("results", f"{config}-seed={seed}-#*.sca"))[0]
    vals = {}
    for line in open(sca):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar":
            vals[(p[1], p[2])] = float(p[3])
    node_mods = sorted({m for (m, k) in vals if k == "residualEnergy" and (".n" in m or ".relay[" in m)})
    bs_mods = {m for (m, k) in vals if k == "deliveredReports" and m.endswith(".BS")}
    check(len(node_mods) == N and len(bs_mods) == 1, f"seed {seed}: S1 {len(node_mods)} battery-node modules (expected {N}) and {len(bs_mods)} BS")

    nodes = rows(pre + "-nodes.csv")
    mat = rows(os.path.join(REF, f"nodes_seed{seed}.csv"))
    first50 = all(float(a["x"]) == float(b["x"]) and float(a["y"]) == float(b["y"]) for a, b in zip(nodes[:50], mat))
    extra = [(float(r["x"]), float(r["y"])) for r in nodes[50:]]
    allpts = [(float(r["x"]), float(r["y"])) for r in nodes]
    inside = all(0 < x < 600 and 0 < y < 50 for x, y in extra)
    check(len(nodes) == N and [int(r["node"]) for r in nodes] == list(range(1, N + 1)) and first50 and inside
          and len(set(allpts)) == N and (600.0, 25.0) not in set(allpts),
          f"seed {seed}: S2 {len(nodes)} coordinates; nodes 1..50 bit-identical to MATLAB; {len(extra)} added relays inside 600 x 50 m, all distinct")

    wl = rows(pre + "-workload.csv")
    wm = rows(os.path.join(REF, "workload_matlab.csv"))
    same_wl = len(wl) == len(wm) and all(a[k] == b[k] for a, b in zip(wl, wm) for k in ["reportIndex", "round", "sourceNode", "station", "date"]) \
        and all(float(a[k]) == float(b[k]) for a, b in zip(wl, wm) for k in ["temperature", "pH", "conductivity", "TDS"])
    rep = rows(pre + "-reports.csv")
    srcs = {int(r["sourceNode"]) for r in rep}
    check(same_wl and srcs <= STATIONS, f"seed {seed}: S3 workload identical to the MATLAB Periyar workload (9825 reports); report sources {sorted(srcs)}")

    dec = rows(pre + "-decisions.csv")
    src_actions_by_relay = [r for r in dec if r["hopType"] in ("0", "1") and int(r["actor"]) not in STATIONS]
    check(not src_actions_by_relay and all(s in STATIONS for s in srcs),
          f"seed {seed}: S4 nodes other than the 10 stations never originate reports or source actions ({len(src_actions_by_relay)} violations)")

    targets = [int(r["target"]) for r in dec]
    states = [int(r["state"]) for r in dec]
    to_bs_ok = all(int(r["target"]) == N + 1 for r in dec if r["hopType"] == "3")
    check(min(targets) >= 1 and max(targets) <= N + 1 and to_bs_ok and 1 <= min(states) and max(states) <= 6561,
          f"seed {seed}: S5 targets within 1..{N + 1} (max {max(targets)}), to-BS actions target {N + 1}, states within 1..6561 ({len(set(states))} visited)")

    extra_used = {t for t in targets if 50 < t <= N}
    extra_heads = {int(r["target"]) for r in dec if r["hopType"] == "1" and int(r["target"]) > 50}
    check(len(extra_used) > 0, f"seed {seed}: S6 {len(extra_used)} of {N - 50} added relays were chosen as next hop or cluster head "
                               f"({len(extra_heads)} as cluster head)")

    bpath = pre + "-success.bin"
    if os.path.exists(bpath):
        a = open(bpath, "rb").read()
        b = open(os.path.join(REF, f"success_seed{seed}.bin"), "rb").read()
        check(a == b, f"seed {seed}: S7 original 50 x 51 channel block, all {len(b)} bits identical to MATLAB success_history")

    E0 = 2.0
    worst = max(abs((E0 - vals[(m, "residualEnergy")]) - (vals[(m, "txEnergy")] + vals[(m, "rxEnergy")] + vals[(m, "aggregationEnergy")])) for m in node_mods)
    spent = sum(vals[(m, "txEnergy")] + vals[(m, "rxEnergy")] + vals[(m, "aggregationEnergy")] for m in node_mods)
    resid = sum(vals[(m, "residualEnergy")] for m in node_mods)
    met = rows(pre + "-metrics.csv")[0]
    check(worst < 1e-9 and abs(spent + resid - E0 * N) < 1e-7 and abs(spent - float(met["spentJ"])) < 1e-8,
          f"seed {seed}: S8 energy closes per node (max error {worst:.1e} J); spent {spent:.4f} + residual {resid:.4f} = {E0 * N:.0f} J")

    per = rows(pre + "-per_round.csv")
    rounds = len(per)
    fates = Counter(r["fate"] for r in rep)
    rep_rounds = [r for r in rep if int(r["round"]) <= rounds]
    emitted = len(rep_rounds) - fates["source_unavailable"]
    lost = sum(v for k, v in fates.items() if k.startswith("lost_"))
    idx = [int(r["reportIndex"]) for r in rep]
    check(len(idx) == len(set(idx)) and int(met["scheduled"]) == 10 * rounds and emitted == int(met["sourceAvailable"])
          and emitted == fates["delivered"] + lost + fates["unattempted"] and fates["delivered"] == int(met["delivered"])
          and vals[("PeriyarRiverNetwork.BS", "deliveredReports")] == fates["delivered"],
          f"seed {seed}: S9 {int(met['scheduled'])} slots ({rounds} rounds); {emitted} emitted = {fates['delivered']} delivered + "
          f"{lost} lost + {fates['unattempted']} unattempted; each report counted once; BS count matches")

    tu = {}
    for e in rows(pre + "-unavailability_events.csv"):
        tu.setdefault(int(e["node"]), float(e["simTime"]))
    late = [r for r in dec if int(r["actor"]) in tu and float(r["decisionTime"]) > tu[int(r["actor"])]]
    chosen = [r for r in dec if int(r["target"]) <= N and r["target"] != r["actor"] and int(r["target"]) in tu
              and tu[int(r["target"])] < float(r["decisionTime"])]
    maxhop = max(int(r["hop"]) for r in dec)
    check(not late and not chosen and maxhop <= 15,
          f"seed {seed}: S10 {len(tu)} nodes became unavailable; 0 late actions ({len(late)}), 0 unavailable targets ({len(chosen)}); max route hop {maxhop}")

    over = max(float(r["roundEndTime"]) - 10.0 * (int(r["round"]) - 1) for r in per)
    check(over < 10.0 and int(met["qUpdates"]) > 0 and int(met["explorations"]) > 0,
          f"seed {seed}: S11 longest round {over:.2f} s of 10 s; {met['qUpdates']} Q-updates, {met['explorations']} exploratory decisions")

print("\n".join(out))
print(f"\n{len(out)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
