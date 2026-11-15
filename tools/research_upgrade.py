"""Research-upgrade analysis: abstract channel vs IEEE 802.15.4 (INET 4.7.0, CC2420), event-aware option vs variant C,
energy (2 J reference ledger and the physical CC2420 / sensing / processing model), lifetime, 200 vs 500 nodes,
placement and density.

Usage (project root):  python -P tools/research_upgrade.py
Reads (never writes) results_environmental*/ and reads results_research_upgrade/<experiment>/; writes
results_research_upgrade/analysis/: per_run.csv, summary_mean_sd.csv, paired_differences.csv, events_by_class.csv,
energy_breakdown.csv, lifetime_vs_capacity.csv, extra comparisons, analysis_report.txt and figures/fig01..fig10 (+ extras).
Statistics: mean and sample SD over the run seeds; paired differences (same seed = same topology, workload, channel and
agent streams) with 95 % t confidence intervals. Missing runs are listed, never filled in.
"""
import csv, json, math, os, re, sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RU = os.path.join(ROOT, "results_research_upgrade")
OUT = os.path.join(RU, "analysis")
FIG = os.path.join(OUT, "figures")
os.makedirs(FIG, exist_ok=True)
SCN = ["water", "effluent", "air", "soil", "mixed"]
NAME = {"water": "Water", "effluent": "Effluent", "air": "Air", "soil": "Soil", "mixed": "Mixed"}
PROFILE = {"water": "water_quality", "effluent": "industrial_effluent", "air": "air_quality", "soil": "soil_monitoring",
           "mixed": "mixed_environment"}
SEEDS = [42, 43, 44, 45, 46]
ROUNDS, ROUND_S, E0 = 500, 100.0, 2.0
PROF = json.load(open(os.path.join(ROOT, "scenario_study/dataset_metadata/sensor_profiles.json")))
PHYS_ROUND_S = 3600.0 * PROF["round_hours"]          # one round = 1 h of environmental time (sensor_profiles.json)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
CCA_S, ACK_S = 128e-6, 352e-6                        # INET Ieee802154Mac ccaDetectionTime; ACK airtime (pilot P1)
# experiments: (label, directory, config file prefix)
EXP = {
    "abstract": (os.path.join(ROOT, "results_environmental"), "V2_200Node_Environmental", 200),
    "abstract500": (os.path.join(ROOT, "results_environmental_500"), "V2_200Node_Environmental", 500),
    "wireless": (os.path.join(RU, "wireless_N200"), "W_Environmental", 200),
    "eventaware": (os.path.join(RU, "eventaware_N200"), "W_EventAware", 200),
    "wireless500": (os.path.join(RU, "wireless_N500"), "W_Environmental", 500),
    "density500": (os.path.join(RU, "fixed_density_N500"), "W_FixedDensity", 500),
    "placement": (os.path.join(RU, "placement_N200"), "W_ScenarioPlacement", 200),
    "matlabprior": (os.path.join(RU, "sensitivity_matlab_prior_N200"), "W_Environmental", 200),
}
log, missing = [], []


def say(s=""):
    log.append(s)


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return float("nan")


def read_sca(path):
    v = {}
    for ln in open(path):
        if ln.startswith("scalar "):
            m = re.match(r'scalar (\S+) ("[^"]*"|\S+) (\S+)', ln)
            v[(m[1].split(".", 1)[1], m[2].strip('"'))] = float(m[3])
    return v


def events_of(scn, n):
    """(node, round) -> (class, deadline) from data/events (class of every report)"""
    p = os.path.join(ROOT, "data/events", f"{PROFILE[scn]}_{n}.csv")
    return {(int(r["node_id"]), int(r["round"])): (int(r["event_class"]), float(r["deadline_s"]))
            for r in csv.DictReader(open(p, newline=""))}


EVENTS = {}


def run(exp, scn, seed):
    d, cfg, n = EXP[exp]
    pre = os.path.join(d, f"{cfg}-{scn}-seed{seed}")
    if not os.path.exists(pre + "-metrics.csv"):
        missing.append(f"{exp}/{scn}/seed{seed}")
        return None
    m = next(csv.DictReader(open(pre + "-metrics.csv")))
    r = {"exp": exp, "scenario": scn, "seed": seed, "nodes": n}
    for k in ("scheduled", "attempts", "delivered", "lossChannel", "lossNoCandidate", "lossTTL", "lossEnergy", "residualJ",
              "spentJ", "energyPerDeliveredJ", "meanHops", "qUpdates", "physicalFrames"):
        r[k] = fnum(m[k])
    r["pdr_pct"] = 100 * r["delivered"] / r["scheduled"]
    r["valid_ratio_pct"] = 100 * r["delivered"] / max(1, r["attempts"])
    r["route_failures"] = r["lossChannel"] + r["lossNoCandidate"] + r["lossTTL"] + r["lossEnergy"]
    pr = list(csv.DictReader(open(pre + "-per_round.csv")))
    alive = np.array([int(x["aliveCount"]) for x in pr])
    r["_alive"], r["_resid"] = alive, np.array([fnum(x["residualJ"]) for x in pr])
    r["_txJ"], r["_rxJ"], r["_aggJ"] = (sum(fnum(x[k]) for x in pr) for k in ("txJ", "rxJ", "aggJ"))

    def first(cond):
        idx = np.nonzero(cond)[0]
        return int(idx[0]) + 1 if len(idx) else float("nan")       # round number; nan = not observed in 500 rounds
    r["FND"], r["N10"], r["N50"], r["LND"] = first(alive < n), first(alive <= 0.9 * n), first(alive <= 0.5 * n), first(alive == 0)
    r["node_rounds"] = int(alive.sum())
    # reports: latency, queueing, event classes (abstract runs: classes joined from data/events)
    key = (scn, n)
    if key not in EVENTS:
        EVENTS[key] = events_of(scn, n)
    ev = EVENTS[key]
    by = defaultdict(lambda: {"gen": 0, "del": 0, "lat": [], "ontime": 0, "qmax": 0.0})
    lat_all, pd_all, q_all = [], [], []
    for x in csv.DictReader(open(pre + "-reports.csv", newline="")):
        cls, dl = ev.get((int(x["sourceNode"]), int(x["round"])), (0, 100.0))
        b = by[cls]
        b["gen"] += 1
        if x["fate"] != "delivered":
            continue
        b["del"] += 1
        pd_all.append(fnum(x["pathDelayS"]))
        if "latencyS" in x:
            lat, q = fnum(x["latencyS"]), fnum(x["queueDelayS"])
            b["lat"].append(lat); lat_all.append(lat); q_all.append(q)
            b["ontime"] += lat <= dl
            b["qmax"] = max(b["qmax"], q)
    r["path_delay_s"] = float(np.mean(pd_all)) if pd_all else float("nan")
    r["latency_s"] = float(np.mean(lat_all)) if lat_all else float("nan")
    r["latency_p95_s"] = float(np.percentile(lat_all, 95)) if lat_all else float("nan")
    r["queue_delay_s"] = float(np.mean(q_all)) if q_all else float("nan")
    for cls, nm in ((0, "routine"), (1, "warning"), (2, "critical")):
        b = by[cls]
        r[f"{nm}_generated"], r[f"{nm}_delivered"] = b["gen"], b["del"]
        r[f"{nm}_pdr_pct"] = 100 * b["del"] / b["gen"] if b["gen"] else float("nan")
        r[f"{nm}_latency_s"] = float(np.mean(b["lat"])) if b["lat"] else float("nan")
        r[f"{nm}_deadline_pct"] = 100 * b["ontime"] / b["gen"] if (b["gen"] and lat_all) else float("nan")
        r[f"{nm}_max_queue_s"] = b["qmax"] if lat_all else float("nan")
    # sensing ledger (never charged to the 2 J battery) and the MCU processing share of it (profiles: ASSUMPTION)
    sl = list(csv.DictReader(open(pre + "-sensing_ledger.csv")))
    pp = PROF["processing"]
    proc_mJ = {p: pp["mcu_active_V"] * pp["mcu_active_mA"] * pp["mcu_ms_per_sample"] / 1000 * PROF["profiles"][p]["samples_per_round"]
               for p in PROF["profiles"]}
    op_rounds = sum(int(x["operationalRounds"]) for x in sl)
    r["processing_J"] = sum(int(x["operationalRounds"]) * proc_mJ[x["sensorType"]] / 1000 for x in sl)
    r["sensing_J"] = sum(fnum(x["sensingJ_operational"]) for x in sl) - r["processing_J"]
    r["op_node_rounds"] = op_rounds
    r["_pdr_round"] = np.array([fnum(x["delivered"]) / max(1.0, fnum(x["scheduled"])) for x in pr]) * 100
    sca = pre + ".sca"
    if os.path.exists(sca):
        v = read_sca(sca)
        mod = (lambda i: f"node[{i}].rl") if not exp.startswith("abstract") else (lambda i: f"node[{i}]")
        rx = np.sort([v.get((mod(i), "rxFrames"), 0.0) for i in range(n)])[::-1]
        r["relay_top10_share_pct"] = 100 * rx[: max(1, n // 10)].sum() / rx.sum() if rx.sum() else float("nan")
        if not exp.startswith("abstract"):
            wireless_metrics(r, v, n)
    return r


def wireless_metrics(r, v, n):
    nodes = [f"node[{i}]" for i in range(n)]
    g = lambda nd, mod, k: v.get((f"{nd}.{mod}", k), 0.0)
    S = ["off", "sleep", "switching", "rxIdle", "rxBusy", "rxReceiving", "txIdle", "tx"]
    P = {s: g(nodes[0], "adapter", "power:" + s) for s in S}
    tA = {s: sum(g(nd, "adapter", "timeActive:" + s) for nd in nodes) for s in S}
    tG = {s: sum(g(nd, "adapter", "timeGap:" + s) for nd in nodes) for s in S}
    act = sum(tA.values())
    e_act = sum(g(nd, "adapter", "radioEnergyActive") for nd in nodes)
    e_gap = sum(g(nd, "adapter", "radioEnergyGap") for nd in nodes)
    e_inet = sum(g(nd, "adapter", "radioEnergyInet") for nd in nodes)
    r["radio_energy_check"] = abs(e_act + e_gap - e_inet) <= 1e-6 * max(1.0, e_inet)
    # 2 J ledger: one first-order TX charge per MAC transmission that started (no node died in these runs)
    r["tx_charge_check"] = all(g(nd, "rl", "txFrames") == g(nd, "wlan.mac", "nbTxFrames") for nd in nodes)
    tx_frames = sum(g(nd, "wlan.mac", "nbTxFrames") for nd in nodes)
    acks_tx = sum(g(nd, "wlan.mac", "nbTxAcks") for nd in nodes) + g("bs", "wlan.mac", "nbTxAcks")
    acks_rx = sum(g(nd, "wlan.mac", "nbRecvdAcks") for nd in nodes)
    backoffs = sum(g(nd, "wlan.mac", "nbBackoffs") for nd in nodes)
    r.update({
        "mac_tx": tx_frames, "mac_tx_success": acks_rx, "mac_missed_acks": sum(g(nd, "wlan.mac", "nbMissedAcks") for nd in nodes),
        "mac_retries": tx_frames - sum(g(nd, "adapter", "framesDown") for nd in nodes)
                       + sum(g(nd, "adapter", "dropChannelAccess") + g(nd, "adapter", "dropQueueOverflow") for nd in nodes),
        "mac_fail_retry": sum(g(nd, "adapter", "dropRetryLimit") for nd in nodes),
        "mac_fail_cca": sum(g(nd, "adapter", "dropChannelAccess") for nd in nodes),
        "mac_fail_queue": sum(g(nd, "adapter", "dropQueueOverflow") for nd in nodes),
        "corrupted_rx": sum(g(nd, "adapter", "corruptedReceptions") for nd in nodes + ["bs"]),
        "backoffs": backoffs,
        "rssi_bs_dBm": v.get(("bs.adapter", "rssiMean"), float("nan")),          # nan: run made before RSSI was recorded
        "snir_bs_dB": v.get(("bs.adapter", "snirMinMean"), float("nan")),
        "rssi_nodes_dBm": float(np.nanmean([v.get((f"{nd}.adapter", "rssiMean"), np.nan) for nd in nodes
                                            if g(nd, "adapter", "framesUp") > 0] or [np.nan])),
        "rounds_active_s": act / n / ROUNDS,                       # mean active window per node and round
        "channel_util_pct": 100 * (tA["rxBusy"] + tA["rxReceiving"] + tA["tx"]) / act if act else float("nan"),
        "channel_busy_s": (tA["rxBusy"] + tA["rxReceiving"]) / n,
    })
    hops = sum(g(nd, "rl", "macHopsDelivered") for nd in nodes)
    r["mac_hop_delay_ms"] = 1e3 * sum(g(nd, "rl", "macHopDelayMean") * g(nd, "rl", "macHopsDelivered") for nd in nodes
                                      if g(nd, "rl", "macHopsDelivered") > 0) / hops if hops else float("nan")
    # CC2420 energy split (J, network total, measured state times; CCA and ACK parts from counts x fixed durations)
    r["E_tx"] = (tA["tx"] + tG["tx"]) * P["tx"]
    r["E_rx"] = (tA["rxReceiving"] + tG["rxReceiving"]) * P["rxReceiving"]
    r["E_cca"] = backoffs * CCA_S * P["rxIdle"]
    r["E_listen_active"] = (tA["rxIdle"] + tA["rxBusy"]) * P["rxIdle"] - r["E_cca"]
    r["E_idle_other"] = sum((tA[s] + tG[s]) * P[s] for s in ("txIdle", "switching", "sleep", "off"))
    r["E_ack_tx"], r["E_ack_rx"] = acks_tx * ACK_S * P["tx"], acks_rx * ACK_S * P["rxReceiving"]
    # Time mapping: a simulated round lasts 100 s, an environmental round 1 h. Network behaviour does not depend on the gap
    # (checked: 100 s and 3600 s rounds give identical results); between rounds only late MAC activity (a retry or ACK just
    # after a round ended) happens, so that part is kept as measured and only the idle part of the gap is mapped to the hour.
    busy = ("switching", "rxBusy", "rxReceiving", "txIdle", "tx")
    late_e, late_t = sum(tG[s] * P[s] for s in busy), sum(tG[s] for s in busy)
    idle_phys = n * ROUNDS * PHYS_ROUND_S - act - late_t      # node-seconds of the hours outside the active windows
    r["E_radio_active"] = e_act
    r["E_radio_always_on"] = e_act + late_e + idle_phys * P["rxIdle"]   # receivers listen all hour (non-beacon routers)
    r["E_sleep_dc"] = idle_phys * P["sleep"]                            # duty cycle: power-down outside the active windows
    r["E_radio_dc"] = e_act + late_e + r["E_sleep_dc"]
    inbox = [v[(f"{nd}.rl", "inboxMax")] for nd in nodes if (f"{nd}.rl", "inboxMax") in v]
    macq = [v[(f"{nd}.wlan.queue", "queueLength:max")] for nd in nodes if (f"{nd}.wlan.queue", "queueLength:max") in v]
    r["inbox_max"] = max(inbox) if inbox else float("nan")            # nan: run made before these were recorded
    lost = [v[(f"{nd}.rl", "framesLostNoOutcome")] for nd in nodes if (f"{nd}.rl", "framesLostNoOutcome") in v]
    r["lost_in_mac"] = sum(lost) if lost else 0.0     # older binaries stopped the run instead, so a finished run had none
    r["macq_max"] = max(macq) if macq else float("nan")


rows = {}
for exp in EXP:
    for s in SCN:
        for sd in SEEDS:
            x = run(exp, s, sd)
            if x:
                rows[(exp, s, sd)] = x

KEYS = ["pdr_pct", "valid_ratio_pct", "delivered", "meanHops", "relay_top10_share_pct", "qUpdates", "route_failures", "lossChannel", "lossNoCandidate",
        "lossTTL", "FND", "N10", "N50", "LND", "node_rounds", "residualJ", "spentJ", "energyPerDeliveredJ", "path_delay_s",
        "latency_s", "latency_p95_s", "queue_delay_s", "mac_hop_delay_ms", "mac_tx", "mac_retries", "mac_missed_acks",
        "mac_fail_retry", "mac_fail_cca", "mac_fail_queue", "corrupted_rx", "channel_util_pct", "channel_busy_s",
        "rounds_active_s", "inbox_max", "macq_max", "lost_in_mac", "rssi_bs_dBm", "snir_bs_dB", "rssi_nodes_dBm", "E_tx", "E_rx", "E_cca", "E_listen_active",
        "E_idle_other", "E_ack_tx", "E_ack_rx", "E_radio_active", "E_radio_always_on", "E_sleep_dc", "E_radio_dc",
        "sensing_J", "processing_J"] + [f"{c}_{k}" for c in ("routine", "warning", "critical")
                                       for k in ("generated", "delivered", "pdr_pct", "latency_s", "deadline_pct", "max_queue_s")]


def write(name, data, cols=None):
    if not data:
        return
    cols = cols or list(data[0].keys())
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)


write("per_run.csv", [x for x in rows.values()], ["exp", "scenario", "seed", "nodes"] + KEYS)


def vals(exp, s, k):
    return [rows[(exp, s, sd)][k] for sd in SEEDS if (exp, s, sd) in rows and k in rows[(exp, s, sd)]]


def msd(a):
    a = [x for x in a if not (isinstance(x, float) and math.isnan(x))]
    if not a:
        return float("nan"), float("nan"), 0
    return float(np.mean(a)), float(np.std(a, ddof=1)) if len(a) > 1 else float("nan"), len(a)


summ = []
for exp in EXP:
    for s in SCN:
        if not any((exp, s, sd) in rows for sd in SEEDS):
            continue
        for k in KEYS:
            m, sdv, nn = msd(vals(exp, s, k))
            if nn:
                summ.append({"exp": exp, "scenario": s, "metric": k, "n_seeds": nn, "mean": m, "sd": sdv})
write("summary_mean_sd.csv", summ)


def paired(a_exp, b_exp, s, k):
    """b - a over the seeds both have; mean, SD, 95 % CI"""
    d = [rows[(b_exp, s, sd)][k] - rows[(a_exp, s, sd)][k] for sd in SEEDS
         if (a_exp, s, sd) in rows and (b_exp, s, sd) in rows and k in rows[(a_exp, s, sd)] and k in rows[(b_exp, s, sd)]]
    d = [x for x in d if not math.isnan(x)]
    if not d:
        return None
    if len(d) == 1:                                # one paired seed: the difference, no spread and no CI
        return {"n": 1, "mean_diff": d[0], "sd_diff": float("nan"), "ci95_low": float("nan"), "ci95_high": float("nan"),
                "per_seed": f"{d[0]:.6g}"}
    m, sdv = float(np.mean(d)), float(np.std(d, ddof=1))
    h = T975[len(d) - 1] * sdv / math.sqrt(len(d))
    return {"n": len(d), "mean_diff": m, "sd_diff": sdv, "ci95_low": m - h, "ci95_high": m + h, "per_seed": " ".join(f"{x:.6g}" for x in d)}


PAIRS = [("abstract", "wireless", ["pdr_pct", "delivered", "meanHops", "relay_top10_share_pct", "route_failures", "FND", "N10", "N50", "node_rounds",
                                    "residualJ", "spentJ", "energyPerDeliveredJ", "path_delay_s", "qUpdates"]),
         ("wireless", "eventaware", ["pdr_pct", "critical_pdr_pct", "critical_latency_s", "critical_deadline_pct",
                                     "warning_pdr_pct", "warning_deadline_pct", "routine_pdr_pct", "routine_latency_s",
                                     "routine_deadline_pct", "routine_max_queue_s", "latency_s", "spentJ", "energyPerDeliveredJ",
                                     "E_radio_active", "E_radio_dc", "sensing_J", "mac_tx", "mac_retries", "corrupted_rx", "FND", "node_rounds"])]
pd_rows = []
for a, b, ks in PAIRS:
    for s in SCN:
        for k in ks:
            p = paired(a, b, s, k)
            if p:
                pd_rows.append({"comparison": f"{b} - {a}", "scenario": s, "metric": k, **p})
write("paired_differences.csv", pd_rows)

# ------------------------------------------------------------------------------------------------ text report
say("RESEARCH UPGRADE ANALYSIS (results_research_upgrade/analysis)")
say(f"runs found: {len(rows)}; not run (listed, never filled in): {len(missing)}")
for exp in EXP:
    have_runs = sorted(f"{s}/{sd}" for (e, s, sd) in rows if e == exp)
    nmiss = sum(m.startswith(exp + "/") for m in missing)
    say(f"  {exp:12s} {len(have_runs):2d} runs present, {nmiss:2d} not run" + (f"  ({', '.join(have_runs)})" if 0 < len(have_runs) < 25 else ""))
for exp in ("abstract", "wireless", "eventaware"):
    say(f"\n== {exp} (mean ± SD over seeds)")
    for s in SCN:
        def f(k, fmt=".2f"):
            m, sdv, nn = msd(vals(exp, s, k))
            return "n/a" if not nn else (f"{m:{fmt}}" + ("" if math.isnan(sdv) else f" ± {sdv:{fmt}}"))
        say(f"  {NAME[s]:9s} PDR {f('pdr_pct')} %  hops {f('meanHops')}  FND {f('FND', '.0f')}  spent {f('spentJ')} J  "
            f"latency {f('latency_s', '.3f')} s  critical PDR {f('critical_pdr_pct')} %  critical on time {f('critical_deadline_pct')} %")
say("\n== paired differences (b - a), 95 % CI")
for p in pd_rows:
    say(f"  {p['comparison']:22s} {p['scenario']:8s} {p['metric']:22s} {p['mean_diff']:+.4g}  [{p['ci95_low']:+.4g}, {p['ci95_high']:+.4g}]  n={p['n']}")
checks = [x.get("radio_energy_check") for x in rows.values() if "radio_energy_check" in x]
say(f"\nradio energy: adapter state integration = INET energy meter in {sum(map(bool, checks))}/{len(checks)} wireless runs")
checks = [x.get("tx_charge_check") for x in rows.values() if "tx_charge_check" in x]
say(f"2 J ledger: TX charges = INET MAC transmissions for every node in {sum(map(bool, checks))}/{len(checks)} wireless runs")

# ------------------------------------------------------------------------------------------------ energy model
eb = []
for exp in ("wireless", "eventaware"):
    for s in SCN:
        rr = [rows[(exp, s, sd)] for sd in SEEDS if (exp, s, sd) in rows and "E_tx" in rows[(exp, s, sd)]]
        if not rr:
            continue
        per = lambda k: float(np.mean([x[k] / x["op_node_rounds"] for x in rr]))     # J per operational node-round
        row = {"exp": exp, "scenario": s, "seeds": len(rr)}
        for k in ("E_tx", "E_rx", "E_cca", "E_listen_active", "E_idle_other", "E_ack_tx", "E_ack_rx", "E_radio_active",
                  "E_sleep_dc", "E_radio_dc", "E_radio_always_on", "sensing_J", "processing_J"):
            row[k + "_per_node_round_J"] = per(k)
        row["aggregation_firstorder_per_node_round_J"] = float(np.mean([x["_aggJ"] / x["op_node_rounds"] for x in rr]))
        row["ledger2J_tx_rx_per_node_round_J"] = float(np.mean([(x["_txJ"] + x["_rxJ"]) / x["op_node_rounds"] for x in rr]))
        row["device_dc_per_node_round_J"] = row["E_radio_dc_per_node_round_J"] + row["sensing_J_per_node_round_J"] + \
            row["processing_J_per_node_round_J"]
        eb.append(row)
write("energy_breakdown.csv", eb)
caps = [1e2, 1e3, 1e4, 1e5]
lt = []
for row in eb:
    for c in caps:
        lt.append({"exp": row["exp"], "scenario": row["scenario"], "usable_capacity_J": c,
                   "rounds_duty_cycled": c / row["device_dc_per_node_round_J"],
                   "days_duty_cycled": c / row["device_dc_per_node_round_J"] * PROF["round_hours"] / 24,
                   "rounds_radio_only_dc": c / row["E_radio_dc_per_node_round_J"],
                   "rounds_2J_reference_ledger": c / row["ledger2J_tx_rx_per_node_round_J"]})
write("lifetime_vs_capacity.csv", lt)
say("\n== physical energy per operational node-round (J): CC2420 radio duty-cycled (active window measured + sleep for the rest")
say(f"   of a {PHYS_ROUND_S:.0f} s round), sensing and processing from the dataset ledger; 2 J ledger = first-order TX+RX")
for row in eb:
    say(f"  {row['exp']:10s} {NAME[row['scenario']]:9s} radio dc {row['E_radio_dc_per_node_round_J']:.4f} (active "
        f"{row['E_radio_active_per_node_round_J']:.4f}, sleep {row['E_sleep_dc_per_node_round_J']:.4f})  sensing "
        f"{row['sensing_J_per_node_round_J']:.4f}  processing {row['processing_J_per_node_round_J']:.5f}  "
        f"2 J ledger {row['ledger2J_tx_rx_per_node_round_J']:.2e}")

# ------------------------------------------------------------------------------------------------ figures
COL = dict(zip(SCN, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))     # palette of tools/environmental_200node.py
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.facecolor": SURF, "figure.facecolor": SURF, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                     "axes.titlesize": 11, "axes.titlecolor": INK})
VAR = [("abstract", "abstract channel (validated)", None), ("wireless", "IEEE 802.15.4, variant C", "////"),
       ("eventaware", "IEEE 802.15.4, event-aware", "...")]
X = np.arange(len(SCN))
def cover(exp):
    got = sorted({(s, sd) for (e, s, sd) in rows if e == exp})
    if len(got) == len(SCN) * len(SEEDS):
        return f"{exp}: 5 scenarios x seeds 42-46"
    return f"{exp}: " + (", ".join(f"{s} seed {sd}" for s, sd in got) + " only" if got else "not run")


NOTE = ("mean ± SD over the seeds present (" + "; ".join(cover(e) for e in ("abstract", "wireless", "eventaware")) +
        "); paired seeds; 200 nodes, 600 x 50 m, 500 rounds")


def bars(ax, key, variants, ylabel, title, scale=1.0):
    w = 0.8 / len(variants)
    for j, (exp, lab, hatch) in enumerate(variants):
        for i, s in enumerate(SCN):
            m, sdv, nn = msd(vals(exp, s, key))
            if not nn:
                continue
            ax.bar(i + (j - (len(variants) - 1) / 2) * w, m * scale, w * 0.92, color=COL[s], hatch=hatch,
                   edgecolor=SURF if hatch is None else INK2, linewidth=0.0 if hatch is None else 0.3,
                   alpha=1.0 if j == 0 else 0.75)
            if nn > 1 and not math.isnan(sdv):
                ax.errorbar(i + (j - (len(variants) - 1) / 2) * w, m * scale, yerr=sdv * scale, color=INK, capsize=2, linewidth=0.9)
            elif nn == 1:                              # single seed: no spread to show
                ax.text(i + (j - (len(variants) - 1) / 2) * w, m * scale, "n=1", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_xticks(X); ax.set_xticklabels([NAME[s] for s in SCN]); ax.grid(axis="x", visible=False)
    ax.set_ylabel(ylabel); ax.set_title(title, loc="left")


def legend(ax, variants):
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor="#bcbbb4", hatch=h, edgecolor=INK2 if h else SURF, label=l) for _, l, h in variants],
              loc="upper left", bbox_to_anchor=(0, -0.12), ncol=len(variants), fontsize=8)


def finish(fig, name, title, note=NOTE):
    fig.suptitle(title, x=0.01, ha="left", color=INK, fontsize=12)
    fig.text(0.01, 0.01, note, color=MUTED, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(os.path.join(FIG, name), dpi=150)
    plt.close(fig)


have = lambda exp: any(k[0] == exp for k in rows)
V3 = [v for v in VAR if have(v[0])]
if have("abstract") and have("wireless"):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    bars(ax[0], "pdr_pct", V3, "PDR (%)", "Packet delivery ratio (delivered / scheduled)")
    bars(ax[1], "route_failures", V3, "lost reports", "Route failures (channel / MAC, no candidate, TTL)")
    legend(ax[0], V3)
    finish(fig, "fig01_delivery_ratio.png", "Delivery: abstract channel vs IEEE 802.15.4 (INET 4.7.0, CC2420 radio)")

    fig, axs = plt.subplots(1, 5, figsize=(15, 3.6), sharey=True)
    for i, s in enumerate(SCN):
        for exp, lab, ls in (("abstract", "abstract", "-"), ("wireless", "802.15.4 variant C", "--"), ("eventaware", "802.15.4 event-aware", ":")):
            a = [rows[(exp, s, sd)]["_alive"] for sd in SEEDS if (exp, s, sd) in rows]
            if a:
                axs[i].plot(np.arange(1, ROUNDS + 1), np.mean(a, axis=0), ls, color=COL[s], label=lab, linewidth=1.6)
        axs[i].set_title(NAME[s], loc="left"); axs[i].set_xlabel("round")
    axs[0].set_ylabel("operational nodes"); axs[0].legend(fontsize=7, loc="lower left")
    finish(fig, "fig02_operational_nodes.png", "Operational nodes per round (2 J reference ledger, 200 uJ death threshold)",
           "mean over the seeds present (" + cover("abstract") + "; " + cover("wireless") + "); node death uses the validated first-order 2 J ledger in both models")

    fig, axs = plt.subplots(1, 5, figsize=(15, 3.6), sharey=True)
    for i, s in enumerate(SCN):
        for exp, lab, ls in (("abstract", "abstract", "-"), ("wireless", "802.15.4 variant C", "--"), ("eventaware", "802.15.4 event-aware", ":")):
            a = [rows[(exp, s, sd)]["_resid"] for sd in SEEDS if (exp, s, sd) in rows]
            if a:
                axs[i].plot(np.arange(1, ROUNDS + 1), np.mean(a, axis=0), ls, color=COL[s], label=lab, linewidth=1.6)
        axs[i].set_title(NAME[s], loc="left"); axs[i].set_xlabel("round")
    axs[0].set_ylabel("residual energy, network (J)"); axs[0].legend(fontsize=7, loc="lower left")
    finish(fig, "fig03_residual_energy.png", "Residual 2 J-ledger energy of the network (200 x 2 J = 400 J)",
           "mean over the seeds present (" + cover("abstract") + "; " + cover("wireless") + "); 802.15.4 charges every MAC transmission (retries included)")

if eb:
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    comp = [("E_tx", "TX (data + ACK)", "#2a78d6"), ("E_rx", "RX (frames, incl. overheard)", "#1baf7a"),
            ("E_cca", "CCA", "#eda100"), ("E_listen_active", "idle listening (active window)", "#c3c2b7"),
            ("E_sleep_dc", "sleep between rounds", "#52514e")]
    rr = [r_ for r_ in eb if r_["exp"] == "wireless"]
    bottom = np.zeros(len(rr))
    for k, lab, c in comp:
        v = np.array([r_[k + "_per_node_round_J"] for r_ in rr]) * 1e3
        ax[0].bar(np.arange(len(rr)), v, 0.6, bottom=bottom, color=c, label=lab, edgecolor=SURF, linewidth=0.6)
        bottom += v
    ax[0].set_xticks(np.arange(len(rr))); ax[0].set_xticklabels([NAME[r_["scenario"]] for r_ in rr]); ax[0].grid(axis="x", visible=False)
    ax[0].set_ylabel("mJ per node and round"); ax[0].set_title("CC2420 radio, duty-cycled (measured radio states)", loc="left")
    ax[0].legend(fontsize=7, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=3)
    parts = [("E_radio_dc", "radio (duty-cycled)", "#2a78d6"), ("sensing_J", "sensing (ledger)", "#eb6834"),
             ("processing_J", "processing (MCU, ASSUMPTION)", "#e87ba4"), ("aggregation_firstorder", "aggregation (first-order E_DA)", "#1baf7a")]
    w = 0.8 / len(parts)                           # grouped on a log axis: the components differ by 5 orders of magnitude
    for j, (k, lab, c) in enumerate(parts):
        v = np.array([r_[k + "_per_node_round_J"] for r_ in rr]) * 1e3
        ax[1].bar(np.arange(len(rr)) + (j - (len(parts) - 1) / 2) * w, v, w * 0.92, color=c, label=lab)
    ax[1].set_yscale("log")
    ax[1].set_xticks(np.arange(len(rr))); ax[1].set_xticklabels([NAME[r_["scenario"]] for r_ in rr]); ax[1].grid(axis="x", visible=False)
    ax[1].set_ylabel("mJ per node and round (log)"); ax[1].set_title("Estimated device energy per 1 h round, by component", loc="left")
    ax[1].legend(fontsize=7, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=2)
    finish(fig, "fig04_energy_breakdown.png", "Energy breakdown (802.15.4, variant C)",
           "radio: INET StateBasedEpEnergyConsumer with CC2420 datasheet currents at 3.3 V; sleep = power-down 20 uA outside the "
           "measured active windows of 1 h rounds (schedule assumption); sensing/processing: sensor_profiles.json ledger")

if have("wireless"):
    V2 = [v for v in VAR[1:] if have(v[0])]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    bars(ax[0], "latency_s", V2, "s", "End-to-end delay (generation -> BS)")
    bars(ax[1], "queue_delay_s", V2, "s", "Queueing delay at nodes (per report)")
    bars(ax[2], "mac_hop_delay_ms", V2, "ms", "MAC delay per hop (queue + CSMA/CA + retries + airtime)")
    legend(ax[0], V2)
    finish(fig, "fig05_delay.png", "Delay on IEEE 802.15.4",
           "end-to-end delay includes the protocol's phase structure (cluster phase, then route phase; 2 s decision jitter each)")

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    for r_ in rows.values():
        if "mac_tx" in r_:
            r_["retries_per_tx_pct"] = 100 * r_["mac_retries"] / max(1, r_["mac_tx"])
            r_["missed_ack_pct"] = 100 * r_["mac_missed_acks"] / max(1, r_["mac_tx"])
            r_["corrupted_per_1k_tx"] = 1000 * r_["corrupted_rx"] / max(1, r_["mac_tx"])
    bars(ax[0], "retries_per_tx_pct", V2, "% of MAC transmissions", "MAC retransmissions")
    bars(ax[1], "missed_ack_pct", V2, "% of MAC transmissions", "Transmissions without MAC ACK")
    bars(ax[2], "corrupted_per_1k_tx", V2, "per 1000 transmissions", "Receptions with bit errors (collisions, interference)")
    legend(ax[0], V2)
    finish(fig, "fig06_mac_collisions_retries.png", "MAC contention: retries, missing ACKs and corrupted receptions",
           "INET has no explicit collision counter: corrupted receptions (packetDropIncorrectlyReceived) at any radio are the collision proxy")

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    bars(ax[0], "channel_util_pct", V2, "% of the active window", "Channel utilisation seen by the nodes (busy + receiving + TX)")
    bars(ax[1], "rounds_active_s", V2, "s per round", "Radio active window per node and round")
    legend(ax[0], V2)
    finish(fig, "fig07_channel_utilization.png", "Channel utilisation on IEEE 802.15.4",
           "busy = energy above the CC2420 CCA threshold (-77 dBm) without decoding; receiving = locked on a frame")

    fig, ax = plt.subplots(1, 4, figsize=(17, 4.2))
    bars(ax[0], "rssi_nodes_dBm", V2, "dBm", "RSSI of frames accepted by nodes")
    bars(ax[1], "snir_bs_dB", V2, "dB", "Mean per-frame minimum SNIR at the BS")
    bars(ax[2], "inbox_max", V2, "frames", "Largest node queue (frames waiting)")
    bars(ax[3], "macq_max", V2, "frames", "Largest MAC interface queue")
    legend(ax[0], V2)
    finish(fig, "figS6_radio_quality_queues.png", "Link quality and queue growth on IEEE 802.15.4",
           "RSSI/SNIR: INET reception indications (no LQI in INET); queues: node inbox (RL layer) and INET DropTailQueue (capacity 100)")

if have("wireless") and have("eventaware"):
    V2 = [v for v in VAR[1:]]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    bars(ax[0], "critical_generated", V2[:1], "reports", "Critical reports generated (same in both)")
    bars(ax[1], "critical_pdr_pct", V2, "%", "Critical-report PDR")
    bars(ax[2], "critical_latency_s", V2, "s", "Mean critical-report delay (delivered)")
    legend(ax[1], V2)
    finish(fig, "fig08_critical_delivery.png", "Critical-event delivery: variant C vs event-aware option (802.15.4)",
           "critical = threshold exceeded in >= 3 consecutive distinct samples (simulation rule); " + cover("wireless") + "; " + cover("eventaware"))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    for i, (c, dl) in enumerate((("critical", 2), ("warning", 10), ("routine", 100))):
        bars(ax[i], f"{c}_deadline_pct", V2, "% of generated", f"{c.capitalize()}: delivered within {dl} s")
    legend(ax[0], V2)
    finish(fig, "fig09_critical_deadline.png", "Deadline performance by event class (simulation targets 2 s / 10 s / 100 s)",
           "deadline success = delivered within the class deadline / generated; " + cover("wireless") + "; " + cover("eventaware"))

if have("abstract") and have("abstract500"):
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    V = [("abstract", "200 nodes", None), ("abstract500", "500 nodes", "////")]
    bars(ax[0], "pdr_pct", V, "PDR (%)", "Abstract channel: PDR")
    bars(ax[1], "energyPerDeliveredJ", V, "mJ", "Abstract: 2 J-ledger energy per delivered report", 1e3)
    # 802.15.4, mixed seed 42 (paired): the full 500-round 500-node run when it exists, otherwise rounds 1-5 of each
    sm = os.path.join(RU, "smoke_tests")
    full500 = os.path.join(EXP["wireless500"][0], "W_Environmental-mixed-seed42-metrics.csv")
    RMAX = 500 if os.path.exists(full500) else 5
    w = [("200 nodes, 600 m", os.path.join(EXP["wireless"][0], "W_Environmental-mixed-seed42-per_round.csv")),
         ("500, fixed area", os.path.join(EXP["wireless500"][0], "W_Environmental-mixed-seed42-per_round.csv") if RMAX == 500
          else os.path.join(sm, "W500_fixed_area_5rounds", "W_Environmental-mixed-seed42-per_round.csv"))]
    if RMAX == 5:
        w.append(("500, fixed density", os.path.join(sm, "W500_fixed_density_5rounds", "W_FixedDensity-mixed-seed42-per_round.csv")))
    w = [(l, f) for l, f in w if os.path.exists(f)]
    fr = []
    for j, (l, f) in enumerate(w):
        pr = [x for x in csv.DictReader(open(f)) if int(x["round"]) <= RMAX]
        sch = sum(int(x["scheduled"]) for x in pr)
        parts_ = [("delivered", sum(int(x["delivered"]) for x in pr), COL["mixed"]),
                  ("lost: MAC / channel", sum(int(x["lossChannel"]) for x in pr), INK2),
                  ("lost: TTL (15 hops)", sum(int(x["lossTTL"]) for x in pr), AXIS)]
        bottom = 0.0
        for k, (lab, v_, c) in enumerate(parts_):
            ax[2].bar(j, 100 * v_ / sch, 0.6, bottom=bottom, color=c, label=lab if j == 0 else None, edgecolor=SURF, linewidth=0.6)
            bottom += 100 * v_ / sch
        ax[2].text(j, 100 * parts_[0][1] / sch / 2, f"{100 * parts_[0][1] / sch:.1f} %", ha="center", fontsize=8, color=SURF)
        fr.append({"case": l, "rounds": f"1-{RMAX}", "scheduled": sch, **{p_[0]: p_[1] for p_ in parts_}})
    write(f"wireless_200_vs_500_rounds1-{RMAX}.csv", fr)
    ax[2].set_xticks(range(len(w))); ax[2].set_xticklabels([l for l, _ in w], fontsize=8); ax[2].grid(axis="x", visible=False)
    ax[2].set_ylabel("% of scheduled reports"); ax[2].set_title(f"802.15.4, mixed seed 42, rounds 1-{RMAX}", loc="left")
    ax[2].legend(fontsize=7, loc="upper right")
    legend(ax[0], V)
    finish(fig, "fig10_200_vs_500.png", "200 versus 500 nodes",
           "abstract: seeds 42-46, 500 rounds (600 x 50 m); 802.15.4: single paired seed 42" + ("" if RMAX == 500 else ", 5-round smoke runs only; fixed density = 1500 x 50 m"))

# ------------------------------------------------------------------------------------------------ event-aware vs variant C
# Rounds 1-100 of mixed seed 42 (a 100-round run equals the first 100 rounds of a full run: checked for 20 rounds)
EA100 = os.path.join(RU, "eventaware_N200_100rounds", "W_EventAware-mixed-seed42")
VC = os.path.join(EXP["wireless"][0], "W_Environmental-mixed-seed42")
if os.path.exists(EA100 + "-metrics.csv") and os.path.exists(VC + "-reports.csv"):
    ev = EVENTS.get(("mixed", 200)) or events_of("mixed", 200)

    def by_class(pre, rmax=100):
        o = defaultdict(lambda: {"gen": 0, "del": 0, "lat": [], "ontime": 0, "q": [0.0]})
        for x in csv.DictReader(open(pre + "-reports.csv", newline="")):
            if int(x["round"]) > rmax:
                continue
            cls, dl = ev.get((int(x["sourceNode"]), int(x["round"])), (0, 100.0))
            b = o[cls]; b["gen"] += 1
            if x["fate"] == "delivered":
                lat = fnum(x["latencyS"]); b["del"] += 1; b["lat"].append(lat); b["ontime"] += lat <= dl
                b["q"].append(fnum(x["queueDelayS"]))
        return o

    def energy100(pre):
        pr = [x for x in csv.DictReader(open(pre + "-per_round.csv")) if int(x["round"]) <= 100]
        return sum(fnum(x["txJ"]) + fnum(x["rxJ"]) + fnum(x["aggJ"]) for x in pr), sum(int(x["delivered"]) for x in pr), \
            sum(int(x["scheduled"]) for x in pr)
    A, B = by_class(VC), by_class(EA100)
    r100 = []
    for cls, nm in ((2, "critical"), (1, "warning"), (0, "routine")):
        for lab, s_ in (("variant C", A[cls]), ("event-aware", B[cls])):
            r100.append({"class": nm, "variant": lab, "generated": s_["gen"], "delivered": s_["del"],
                         "pdr_pct": 100 * s_["del"] / s_["gen"], "mean_delay_s": float(np.mean(s_["lat"])),
                         "p95_delay_s": float(np.percentile(s_["lat"], 95)), "deadline_met_pct": 100 * s_["ontime"] / s_["gen"],
                         "max_queue_delay_s": max(s_["q"])})
    write("eventaware_vs_variantC_rounds1-100.csv", r100)
    (eA, dA, sA), (eB, dB, sB) = energy100(VC), energy100(EA100)
    say("\n== event-aware vs variant C, mixed seed 42, rounds 1-100 (paired: same topology, workload, seeds)")
    say(f"  all reports: PDR {100 * dA / sA:.2f} % -> {100 * dB / sB:.2f} %; 2 J-ledger energy {eA:.3f} -> {eB:.3f} J; "
        f"per delivered report {1e3 * eA / dA:.4f} -> {1e3 * eB / dB:.4f} mJ")
    for x in r100:
        say(f"  {x['class']:8s} {x['variant']:11s} generated {x['generated']:5d}  PDR {x['pdr_pct']:6.2f} %  delay {x['mean_delay_s']:.3f} s "
            f"(p95 {x['p95_delay_s']:.3f})  deadline met {x['deadline_met_pct']:6.2f} %  max queue wait {x['max_queue_delay_s']:.3f} s")
    V2l = [("variant C", None), ("event-aware", "////")]
    cl = ["critical", "warning", "routine"]
    for name, key, yl, title in (("figS4_eventaware_rounds1-100_delivery.png", "pdr_pct", "PDR (%)", "Delivery by event class"),
                                 ("figS5_eventaware_rounds1-100_deadline.png", "deadline_met_pct", "% of generated reports",
                                  "Delivered within the class deadline (2 s / 10 s / 100 s)")):
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
        for j, (lab, h) in enumerate(V2l):
            vals_ = [next(x[key] for x in r100 if x["class"] == c and x["variant"] == lab) for c in cl]
            ax[0].bar(np.arange(3) + (j - 0.5) * 0.38, vals_, 0.35, color=COL["mixed"], hatch=h, edgecolor=INK2 if h else SURF,
                      linewidth=0.3 if h else 0, alpha=1 - 0.25 * j, label=lab)
            for i, v_ in enumerate(vals_):
                ax[0].text(i + (j - 0.5) * 0.38, v_ + 1, f"{v_:.1f}", ha="center", fontsize=8, color=INK2)
        ax[0].set_xticks(range(3)); ax[0].set_xticklabels(cl); ax[0].grid(axis="x", visible=False)
        ax[0].set_ylabel(yl); ax[0].set_title(title, loc="left"); ax[0].legend(fontsize=8, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=2)
        for j, (lab, ls) in enumerate((("variant C", "-"), ("event-aware", "--"))):
            lat = np.sort((A if j == 0 else B)[2]["lat"])
            ax[1].plot(lat, np.arange(1, len(lat) + 1) / len(lat), ls, color=COL["mixed"] if j == 0 else INK2, label=lab, linewidth=1.6)
        ax[1].axvline(2.0, color=MUTED, linewidth=1, linestyle=":"); ax[1].text(2.05, 0.5, "2 s deadline", fontsize=8, color=MUTED)
        ax[1].set_xlabel("delay from generation (s)"); ax[1].set_ylabel("fraction of delivered critical reports")
        ax[1].set_title("Critical-report delay (CDF)", loc="left"); ax[1].legend(fontsize=8, loc="lower right")
        finish(fig, name, "Critical events: variant C vs event-aware option (IEEE 802.15.4, 200 nodes, mixed)",
               "single paired seed (42), rounds 1-100; classes and deadlines are simulation rules (data/events, tools/build_event_annotations.py)")

# ------------------------------------------------------------------------------------------------ routing feedback airtime
# W_FeedbackAck: the feedback carried in a 6-byte-longer enhanced MAC ACK (48 bit x 4 us = 192 us more per ACK), rounds 1-100
FB = os.path.join(RU, "feedback_ack_N200_100rounds", "W_FeedbackAck-mixed-seed42")
VC0 = os.path.join(EXP["wireless"][0], "W_Environmental-mixed-seed42")
if os.path.exists(FB + "-metrics.csv") and os.path.exists(VC0 + "-per_round.csv"):
    def pr100(pre):
        pr = [x for x in csv.DictReader(open(pre + "-per_round.csv")) if int(x["round"]) <= 100]
        return {k: sum(fnum(x[k]) for x in pr) for k in ("delivered", "scheduled", "lossChannel", "txJ", "rxJ", "aggJ", "physicalFrames")}
    a, b = pr100(VC0), pr100(FB)
    v = read_sca(FB + ".sca")
    nd = [f"node[{i}]" for i in range(200)]
    acks_tx = sum(v.get((f"{x}.wlan.mac", "nbTxAcks"), 0) for x in nd + ["bs"])
    acks_rx = sum(v.get((f"{x}.wlan.mac", "nbRecvdAcks"), 0) for x in nd)
    p_tx, p_rx = v[("node[0].adapter", "power:tx")], v[("node[0].adapter", "power:rxReceiving")]
    extra = 48 * 4e-6
    e_act = sum(v.get((f"{x}.adapter", "radioEnergyActive"), 0) for x in nd)
    fb = {"acks_sent": acks_tx, "acks_received": acks_rx, "extra_ack_airtime_s": acks_tx * extra,
          "extra_tx_energy_J": acks_tx * extra * p_tx, "extra_rx_energy_J_addressed": acks_rx * extra * p_rx,
          "radio_active_energy_J": e_act, "pdr_variantC_pct": 100 * a["delivered"] / a["scheduled"],
          "pdr_feedback_ack_pct": 100 * b["delivered"] / b["scheduled"], "lossChannel_variantC": a["lossChannel"],
          "lossChannel_feedback_ack": b["lossChannel"], "ledger2J_variantC_J": a["txJ"] + a["rxJ"] + a["aggJ"],
          "ledger2J_feedback_ack_J": b["txJ"] + b["rxJ"] + b["aggJ"]}
    write("feedback_ack_rounds1-100.csv", [fb])
    say()
    say("== routing feedback in an enhanced MAC ACK (+6 B), mixed seed 42, rounds 1-100, vs variant C (same rounds)")
    say(f"  PDR {fb['pdr_variantC_pct']:.2f} % -> {fb['pdr_feedback_ack_pct']:.2f} %; channel losses {a['lossChannel']:.0f} -> {b['lossChannel']:.0f}")
    say(f"  {acks_tx:.0f} ACKs x 192 us = {fb['extra_ack_airtime_s']:.2f} s extra airtime; extra energy TX {fb['extra_tx_energy_J']:.3f} J + "
        f"addressed RX {fb['extra_rx_energy_J_addressed']:.3f} J = {100 * (fb['extra_tx_energy_J'] + fb['extra_rx_energy_J_addressed']) / e_act:.3f} % "
        f"of the {e_act:.0f} J active-window radio energy")

# ------------------------------------------------------------------------------------------------ supplementary figures
if have("abstract") and have("wireless"):
    fig, axs = plt.subplots(1, 5, figsize=(15, 3.6), sharey=True)
    for i, s in enumerate(SCN):
        for exp, lab, ls in (("abstract", "abstract", "-"), ("wireless", "802.15.4, link-budget prior", "--"),
                             ("matlabprior", "802.15.4, MATLAB prior (seed 42)", ":")):
            a = [rows[(exp, s, sd)]["_pdr_round"] for sd in SEEDS if (exp, s, sd) in rows]
            if a:
                m = np.convolve(np.mean(a, axis=0), np.ones(10) / 10, mode="valid")
                axs[i].plot(np.arange(10, ROUNDS + 1), m, ls, color=COL[s], label=lab, linewidth=1.5)
        axs[i].set_title(NAME[s], loc="left"); axs[i].set_xlabel("round")
    axs[0].set_ylabel("PDR per round (%), 10-round mean"); axs[0].legend(fontsize=7, loc="lower right")
    finish(fig, "figS1_learning_curve.png", "Learning curve: delivery per round",
           "mean over the seeds present (" + cover("abstract") + "; " + cover("wireless") + "; MATLAB-prior sensitivity: mixed seed 42); 10-round running mean")

LC = os.path.join(RU, "link_check")
if os.path.isdir(LC):
    pre = os.path.join(LC, "W_Environmental-mixed-seed42")
    pos = {int(x["node"]): (float(x["x"]), float(x["y"])) for x in csv.DictReader(open(pre + "-nodes.csv"))}
    pos[len(pos) + 1] = (600.0, 25.0)                                  # the BS
    bins = defaultdict(lambda: [0, 0])
    for x in csv.DictReader(open(pre + "-decisions.csv")):
        a, t = int(x["actor"]), int(x["target"])
        if a != t:
            b = bins[int(math.dist(pos[a], pos[t]) // 10) * 10 + 5]
            b[0] += 1; b[1] += int(x["outcome"])
    ks = sorted(bins)
    write("link_success_by_distance.csv", [{"distance_bin_center_m": k, "decisions": bins[k][0],
                                            "success_rate": bins[k][1] / bins[k][0]} for k in ks])
    prior = [(float(x["distance_m"]), float(x["prr"])) for x in csv.DictReader(open(os.path.join(
        ROOT, "results_research_upgrade/wireless_N200/W_Environmental-mixed-seed42-link_prior.csv")))]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot([d for d, _ in prior], [p for _, p in prior], color=COL["water"], linewidth=2,
            label="link-budget prior (expected PRR, 127 B PSDU)")
    ax.scatter(ks, [bins[k][1] / bins[k][0] for k in ks], s=[8 + bins[k][0] / 20 for k in ks], color=COL["effluent"],
               label="measured hop success (MAC outcome); area ~ number of decisions")
    ax.set_xlabel("link length (m)"); ax.set_ylabel("success"); ax.set_xlim(0, 250); ax.legend(fontsize=8)
    finish(fig, "figS2_link_prior_vs_measured.png", "Agent link prior vs measured IEEE 802.15.4 hop success",
           "measured: 20 rounds, 200 nodes, mixed seed 42 with the MATLAB distance prior (which also tries links beyond range)")

if have("placement") and have("wireless"):
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    V = [("wireless", "common topology", None), ("placement", "scenario-specific synthetic layout", "////")]
    for j, (k, yl, t) in enumerate((("pdr_pct", "PDR (%)", "PDR"), ("meanHops", "hops", "Mean delivered hops"),
                                     ("latency_s", "s", "End-to-end delay"))):
        for jj, (e, lab, h) in enumerate(V):
            for i, s in enumerate(SCN):
                if (e, s, 42) in rows:
                    ax[j].bar(i + (jj - 0.5) * 0.4, rows[(e, s, 42)][k], 0.37, color=COL[s], hatch=h,
                              edgecolor=INK2 if h else SURF, linewidth=0.3 if h else 0, alpha=1 - 0.25 * jj)
        ax[j].set_xticks(X); ax[j].set_xticklabels([NAME[s] for s in SCN]); ax[j].grid(axis="x", visible=False)
        ax[j].set_ylabel(yl); ax[j].set_title(t, loc="left")
    legend(ax[0], V)
    finish(fig, "figS3_placement.png", "Placement sensitivity on IEEE 802.15.4 (seed 42)",
           "synthetic layouts, no real coordinates: water centreline, effluent outfall clusters, air grid, soil near-bank grid")

open(os.path.join(OUT, "analysis_report.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
