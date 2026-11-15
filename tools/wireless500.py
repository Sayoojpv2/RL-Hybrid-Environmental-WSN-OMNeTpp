"""500-node IEEE 802.15.4 analysis (W_Environmental, mixed scenario) and comparison with the abstract 500-node baseline.

Usage: python -P tools/wireless500.py [--dir results_research_upgrade/wireless_N500] [--nodes 500]
Reads only completed runs (a run counts when its -metrics.csv exists; status files and logs give runtime and memory).
Writes <dir>/analysis/per_seed.csv, summary.csv and report.txt. Mean, SD and 95 % t-intervals only with >= 2 seeds.
"""
import argparse, csv, math, os, re
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="results_research_upgrade/wireless_N500")
ap.add_argument("--nodes", type=int, default=500)
ap.add_argument("--abstract", default="results_environmental_500")
a = ap.parse_args()
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
D, N, ABS = os.path.join(ROOT, a.dir), a.nodes, os.path.join(ROOT, a.abstract)
OUT = os.path.join(D, "analysis")
ROUNDS, PHYS_ROUND_S, CCA_S = 500, 3600.0, 128e-6
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776}
EVENTS = {(int(r["node_id"]), int(r["round"])): (int(r["event_class"]), float(r["deadline_s"]))
          for r in csv.DictReader(open(os.path.join(ROOT, f"data/events/mixed_environment_{N}.csv")))}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def sca(path):
    v = {}
    for ln in open(path):
        if ln.startswith("scalar "):
            m = re.match(r'scalar (\S+) ("[^"]*"|\S+) (\S+)', ln)
            v[(m[1].split(".", 1)[1], m[2].strip('"'))] = float(m[3])
    return v


def common(pre, wireless):
    """metrics with the same definition in both models (same seed = same topology, workload and agent stream)"""
    m = next(csv.DictReader(open(pre + "-metrics.csv")))
    r = {k: fnum(m[k]) for k in ("scheduled", "delivered", "lossChannel", "lossNoCandidate", "lossTTL", "lossEnergy",
                                 "residualJ", "spentJ", "energyPerDeliveredJ", "meanHops", "qUpdates")}
    r["pdr_pct"] = 100 * r["delivered"] / r["scheduled"]
    alive = np.array([int(x["aliveCount"]) for x in csv.DictReader(open(pre + "-per_round.csv"))])
    first = lambda c: (int(np.nonzero(c)[0][0]) + 1) if c.any() else None
    r["first_node_failure_round"], r["n10_round"], r["n50_round"] = first(alive < N), first(alive <= 0.9 * N), first(alive <= 0.5 * N)
    r["alive_end"], r["dead_end"] = int(alive[-1]), N - int(alive[-1])
    by = {c: [0, 0, [], 0, 0.0] for c in (0, 1, 2)}           # generated, delivered, delays, on time, max queue wait
    lat, q = [], []
    for x in csv.DictReader(open(pre + "-reports.csv", newline="")):
        cls, dl = EVENTS.get((int(x["sourceNode"]), int(x["round"])), (0, 100.0))
        b = by[cls]; b[0] += 1
        if x["fate"] != "delivered":
            continue
        b[1] += 1
        if wireless:
            t = fnum(x["latencyS"]); b[2].append(t); b[3] += t <= dl; b[4] = max(b[4], fnum(x["queueDelayS"]))
            lat.append(t); q.append(fnum(x["queueDelayS"]))
    for c, nm in ((2, "critical"), (1, "warning"), (0, "routine")):
        g, d, l, ot, mq = by[c]
        r[f"{nm}_generated"], r[f"{nm}_delivered"], r[f"{nm}_pdr_pct"] = g, d, 100 * d / g if g else float("nan")
        if wireless:
            r[f"{nm}_delay_s"] = float(np.mean(l)) if l else float("nan")
            r[f"{nm}_within_deadline_pct"] = 100 * ot / g if g else float("nan")
            r[f"{nm}_max_queue_wait_s"] = mq
    if wireless:
        r["delay_mean_s"], r["delay_p95_s"] = float(np.mean(lat)), float(np.percentile(lat, 95))
        r["queue_delay_mean_s"] = float(np.mean(q))
    return r


def radio(r, v):
    nodes = [f"node[{i}]" for i in range(N)]
    g = lambda nd, mod, k: v.get((f"{nd}.{mod}", k), 0.0)
    S = ["off", "sleep", "switching", "rxIdle", "rxBusy", "rxReceiving", "txIdle", "tx"]
    P = {s: g(nodes[0], "adapter", "power:" + s) for s in S}
    tA = {s: sum(g(nd, "adapter", "timeActive:" + s) for nd in nodes) for s in S}
    tG = {s: sum(g(nd, "adapter", "timeGap:" + s) for nd in nodes) for s in S}
    act = sum(tA.values())
    e_act = sum(g(nd, "adapter", "radioEnergyActive") for nd in nodes)
    e_all = e_act + sum(g(nd, "adapter", "radioEnergyGap") for nd in nodes)
    busy = ("switching", "rxBusy", "rxReceiving", "txIdle", "tx")
    late_e, late_t = sum(tG[s] * P[s] for s in busy), sum(tG[s] for s in busy)
    idle = N * ROUNDS * PHYS_ROUND_S - act - late_t
    nr = N * ROUNDS
    tx = sum(g(nd, "wlan.mac", "nbTxFrames") for nd in nodes)
    down = sum(g(nd, "adapter", "framesDown") for nd in nodes)
    never = sum(g(nd, "adapter", "dropChannelAccess") + g(nd, "adapter", "dropQueueOverflow") for nd in nodes)
    hops = sum(g(nd, "rl", "macHopsDelivered") for nd in nodes)
    rs = [v[(f"{nd}.adapter", "rssiMean")] for nd in nodes if (f"{nd}.adapter", "rssiMean") in v and g(nd, "adapter", "framesUp") > 0]
    r.update({
        "check_radio_energy_eq_inet_meter": abs(e_all - sum(g(nd, "adapter", "radioEnergyInet") for nd in nodes)) <= 1e-6 * e_all,
        "check_tx_charges_eq_mac_tx": all(g(nd, "rl", "txFrames") == g(nd, "wlan.mac", "nbTxFrames") for nd in nodes
                                          if g(nd, "rl", "alive") == 1),
        "mac_transmissions": tx, "mac_retransmissions": tx - down + never,
        "mac_retx_pct": 100 * (tx - down + never) / tx if tx else float("nan"),
        "mac_missed_ack_pct": 100 * sum(g(nd, "wlan.mac", "nbMissedAcks") for nd in nodes) / tx if tx else float("nan"),
        "mac_drop_retry_limit": sum(g(nd, "adapter", "dropRetryLimit") for nd in nodes),
        "mac_drop_channel_access": sum(g(nd, "adapter", "dropChannelAccess") for nd in nodes),
        "mac_drop_queue_overflow": sum(g(nd, "adapter", "dropQueueOverflow") for nd in nodes),
        "hops_lost_in_receiver_mac": sum(g(nd, "rl", "framesLostNoOutcome") for nd in nodes),
        "corrupted_receptions": sum(g(nd, "adapter", "corruptedReceptions") for nd in nodes + ["bs"]),
        "mac_hop_delay_ms": 1e3 * sum(g(nd, "rl", "macHopDelayMean") * g(nd, "rl", "macHopsDelivered") for nd in nodes
                                      if g(nd, "rl", "macHopsDelivered") > 0) / hops if hops else float("nan"),
        "rssi_bs_dBm": v.get(("bs.adapter", "rssiMean"), float("nan")), "snir_bs_dB": v.get(("bs.adapter", "snirMinMean"), float("nan")),
        "rssi_nodes_mean_dBm": float(np.mean(rs)) if rs else float("nan"),
        "channel_utilisation_pct": 100 * (tA["rxBusy"] + tA["rxReceiving"] + tA["tx"]) / act,
        "active_window_s": act / nr,
        "node_queue_max_frames": max(g(nd, "rl", "inboxMax") for nd in nodes),
        "mac_queue_max_frames": max(g(nd, "wlan.queue", "queueLength:max") for nd in nodes),
        "radio_active_J_per_node_round": e_act / nr,
        "radio_idle_listening_J_per_node_round": ((tA["rxIdle"] + tA["rxBusy"]) * P["rxIdle"]) / nr,
        "radio_tx_J_per_node_round": (tA["tx"] + tG["tx"]) * P["tx"] / nr,
        "radio_rx_J_per_node_round": (tA["rxReceiving"] + tG["rxReceiving"]) * P["rxReceiving"] / nr,
        "radio_duty_cycled_J_per_node_round": (e_act + late_e + idle * P["sleep"]) / nr,
        "radio_listen_all_hour_J_per_node_round": (e_act + late_e + idle * P["rxIdle"]) / nr,
    })


def runtime(seed):
    t, mem = float("nan"), float("nan")
    lg = os.path.join(D, f"W_Environmental-mixed-seed{seed}.log")
    if os.path.exists(lg):
        m = re.search(r"^real\s+(\d+)m([\d.]+)s", open(lg).read(), re.M)
        if m:
            t = (int(m[1]) * 60 + float(m[2])) / 3600
    st = os.path.join(D, f"seed{seed}.status.txt")
    if os.path.exists(st):
        m = re.search(r"peak_MB ([\d.]+)", open(st).read())
        if m:
            mem = float(m[1])
    return t, mem


rows = []
for seed in (42, 43, 44, 45, 46):
    pre = os.path.join(D, f"W_Environmental-mixed-seed{seed}")
    if not os.path.exists(pre + "-metrics.csv"):
        continue
    r = {"model": "802.15.4", "seed": seed, **common(pre, True)}
    radio(r, sca(pre + ".sca"))
    r["runtime_h"], r["peak_memory_MB"] = runtime(seed)
    rows.append(r)
    ab = os.path.join(ABS, f"V2_200Node_Environmental-mixed-seed{seed}")
    if os.path.exists(ab + "-metrics.csv"):
        rows.append({"model": "abstract", "seed": seed, **common(ab, False)})
os.makedirs(OUT, exist_ok=True)
keys = list(dict.fromkeys(k for r in rows for k in r))
with open(os.path.join(OUT, "per_seed.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)

out = [f"500-node IEEE 802.15.4 (W_Environmental, mixed) - completed seeds: {[r['seed'] for r in rows if r['model'] == '802.15.4']}"]
summ = []
for model in ("802.15.4", "abstract"):
    rr = [r for r in rows if r["model"] == model]
    for k in keys:
        vals = [r[k] for r in rr if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool) and r.get(k) is not None
                and not math.isnan(r[k])]
        if vals and k != "seed":
            sd = float(np.std(vals, ddof=1)) if len(vals) > 1 else float("nan")
            summ.append({"model": model, "metric": k, "n": len(vals), "mean": float(np.mean(vals)), "sd": sd})
with open(os.path.join(OUT, "summary.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, ["model", "metric", "n", "mean", "sd"]); w.writeheader(); w.writerows(summ)
for r in rows:
    out.append(f"\n[{r['model']} seed {r['seed']}]")
    out += [f"  {k} = {v:.6g}" if isinstance(v, float) else f"  {k} = {v}" for k, v in r.items() if k not in ("model", "seed")]
pairs = [(w_, b) for w_ in rows if w_["model"] == "802.15.4" for b in rows if b["model"] == "abstract" and b["seed"] == w_["seed"]]
out.append("\npaired difference 802.15.4 - abstract (same seed: same topology, workload and agent stream)")
for k in ("pdr_pct", "delivered", "meanHops", "spentJ", "energyPerDeliveredJ", "critical_pdr_pct", "routine_pdr_pct", "alive_end"):
    d = [w_[k] - b[k] for w_, b in pairs]
    if len(d) >= 2:
        m, s = float(np.mean(d)), float(np.std(d, ddof=1)); h = T975[len(d) - 1] * s / math.sqrt(len(d))
        out.append(f"  {k}: {m:+.4g} [{m - h:+.4g}, {m + h:+.4g}] (n = {len(d)})")
    elif d:
        out.append(f"  {k}: {d[0]:+.4g} (one seed, no interval)")
open(os.path.join(OUT, "report.txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
