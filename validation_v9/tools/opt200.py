#!/usr/bin/env python3
"""200-node RL-Hybrid optimisation study: metrics, paired comparisons, bottleneck diagnosis and graphs.

Usage (from the project folder):
  python3 tools/opt200.py runmaps                       # run-number -> iteration map of every config (needs the exe)
  python3 tools/opt200.py table  dev|final              # variant table + paired per-seed differences -> <stage>/
  python3 tools/opt200.py diag                          # bottleneck analysis of the baseline (+ seed-42 decision logs)
  python3 tools/opt200.py plots  dev|final              # PNG graphs + CSV data for the graphs -> <stage>/graphs/
Extended OMNeT++ simulation: there is no 200-node MATLAB reference. Metric definitions follow MATLAB extract_metrics
(delivery ratio = delivered / valid-data reports; source-packet PDR = delivered / generated; delay = mean per report).
"""
import csv, glob, json, math, os, re, statistics as st, subprocess, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "results_200node_optimization"
N = 200
REAL = set(range(1, 11))
# (label, result sub-folder, file prefix, config, iteration tokens in the .sca name)
DEV = [("Baseline", "dev/baseline", "V2_200Node", "V2_200Node", {}),
       ("A0 retry (unrestricted)", "dev/retx_unrestricted", "V2_200Node_RetxUnrestricted", "V2_200Node_RetxUnrestricted", {}),
       ("A retry, reserve 0.25", "dev/retx_energy_aware", "V2_200Node_RetxEnergyAware-reserve0.25", "V2_200Node_RetxEnergyAware", {"reserve": "0.25"}),
       ("A retry, reserve 0.50", "dev/retx_energy_aware", "V2_200Node_RetxEnergyAware-reserve0.5", "V2_200Node_RetxEnergyAware", {"reserve": "0.5"}),
       ("B Q-prior init", "dev/qprior", "V2_200Node_QPrior", "V2_200Node_QPrior", {}),
       ("C energy guard 0.5", "dev/energy_aware_routing", "V2_200Node_EnergyAwareRouting-guard0.5", "V2_200Node_EnergyAwareRouting", {"guard": "0.5"}),
       ("C energy guard 0.8", "dev/energy_aware_routing", "V2_200Node_EnergyAwareRouting-guard0.8", "V2_200Node_EnergyAwareRouting", {"guard": "0.8"}),
       ("D eps constant 0.05", "dev/adaptive_epsilon", "V2_200Node_AdaptiveEpsilon-ei0.05-em0.05-ed1.0", "V2_200Node_AdaptiveEpsilon", {"ei": "0.05"}),
       ("D eps 0.25 decay 0.99, floor 0", "dev/adaptive_epsilon", "V2_200Node_AdaptiveEpsilon-ei0.25-em0.0-ed0.99", "V2_200Node_AdaptiveEpsilon", {"ei": "0.25", "em": "0.0"}),
       ("D eps 0.25 decay 0.99, floor 0.01", "dev/adaptive_epsilon", "V2_200Node_AdaptiveEpsilon-ei0.25-em0.01-ed0.99", "V2_200Node_AdaptiveEpsilon", {"ei": "0.25", "em": "0.01"})]
EXTRA = os.path.join(ROOT, "variants_extra.json")   # variants added later (E, combinations, final stage)
DEV_SEEDS, FINAL_SEEDS = [42, 43, 44, 45, 46], list(range(47, 67))


def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def num(s):
    s = (s or "").strip()
    return math.nan if s in ("", "NaN", "nan") else float(s)


def variants(stage):
    v = list(DEV) if stage == "dev" else []
    if os.path.exists(EXTRA):
        v += [tuple(x[:4]) + (x[4],) for x in json.load(open(EXTRA)).get(stage, [])]
    return v


def runmap():
    m = {}
    for p in glob.glob(os.path.join(ROOT, "runmaps", "*.txt")):
        cfg = os.path.basename(p)[:-4]
        for line in open(p):
            r = re.match(r"Run (\d+): (.*)", line.strip())
            if r:
                kv = dict(re.findall(r"\$(\w+)=([^,]+)", r.group(2)))
                m.setdefault(cfg, []).append((r.group(1), {k: v.strip() for k, v in kv.items()}))
    return m


def perf_of(cfg, seed, tok, rm, perf):
    for run, kv in rm.get(cfg, []):
        if kv.get("seed") == str(seed) and all(kv.get(k) == v for k, v in tok.items()):
            return perf.get((cfg, run), (math.nan, math.nan))
    return (math.nan, math.nan)


def load(sub, prefix, cfg, tok, seed, rm, perf):
    d = os.path.join(ROOT, sub)
    pre = os.path.join(d, f"{prefix}-seed{seed}")
    cand = [p for p in glob.glob(os.path.join(d, f"{cfg}-*.sca"))
            if all(re.search(rf"[-,]{k}={re.escape(v)}(,|-#)", os.path.basename(p)) for k, v in dict(tok, seed=str(seed)).items())]
    if len(cand) != 1:
        raise SystemExit(f"{pre}: expected one .sca, found {cand}")
    sc = defaultdict(dict)
    for line in open(cand[0]):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar":
            sc[p[1]][p[2]] = float(p[3])
    nodes = {int(m.split("[")[1].rstrip("]")) + 1: v for m, v in sc.items() if ".node[" in m}
    ctl = sc["PeriyarRiverNetwork.controller"]
    per = rows(pre + "-per_round.csv")
    rep = rows(pre + "-reports.csv")
    met = rows(pre + "-metrics.csv")[0]
    S = lambda k: sum(num(r[k]) for r in per)
    m = {}
    m["scheduled"], m["valid"], m["generated"], m["delivered"] = S("scheduled"), S("workloadAvailable"), S("sourceAvailable"), S("delivered")
    m["validPDR"] = 100 * m["delivered"] / m["valid"]; m["schedPDR"] = 100 * m["delivered"] / m["scheduled"]
    m["sourcePDR"] = 100 * m["delivered"] / m["generated"]
    for k, c in [("lossChannel", "lossChannel"), ("lossNoCand", "lossNoCandidate"), ("lossEnergy", "lossEnergy"),
                 ("lossTTL", "lossTTL"), ("unattempted", "unattempted")]:
        m[k] = S(c)
    m["deadSource"] = m["valid"] - m["generated"]
    # real stations vs virtual replay nodes
    for cls, sel in [("real", lambda nd: nd in REAL), ("replay", lambda nd: nd not in REAL)]:
        rr = [r for r in rep if sel(int(r["sourceNode"]))]
        v_ = len(rr); g_ = sum(1 for r in rr if r["fate"] != "source_unavailable"); d_ = sum(1 for r in rr if r["fate"] == "delivered")
        m[f"{cls}Valid"], m[f"{cls}Generated"], m[f"{cls}Delivered"] = v_, g_, d_
        m[f"{cls}ValidPDR"] = 100 * d_ / v_ if v_ else math.nan
        m[f"{cls}SourcePDR"] = 100 * d_ / g_ if g_ else math.nan
    # energy
    m["txJ"], m["rxJ"], m["aggJ"] = S("txJ"), S("rxJ"), S("aggJ")
    m["spentJ"] = m["txJ"] + m["rxJ"] + m["aggJ"]
    m["residualJ"] = num(per[-1]["residualJ"])
    m["usableResidualJ"] = sum(v["residualEnergy"] for v in nodes.values() if v["alive"] == 1)
    m["retryJ"] = sum(v.get("retryEnergy", 0.0) for v in nodes.values())
    m["eprMJ"] = 1000 * m["spentJ"] / m["delivered"]
    # lifetime
    alive = [int(r["aliveCount"]) for r in per]
    m["finalAlive"] = alive[-1]
    m["FND"] = next((i + 1 for i, a in enumerate(alive) if a < N), math.nan)
    m["HND"] = next((i + 1 for i, a in enumerate(alive) if a <= N / 2), math.nan)
    m["LND"] = next((i + 1 for i, a in enumerate(alive) if a == 0), math.nan)
    # routing
    m["meanHops"] = num(met["meanHops"])
    m["frames"] = ctl.get("physicalFrames", math.nan)
    m["linkSuccess"] = ctl.get("successfulFrames", math.nan) / ctl.get("physicalFrames", math.nan)
    m["retriesSent"] = ctl.get("retransmissionsSent", 0.0); m["retriesDecoded"] = ctl.get("retransmissionsDecoded", 0.0)
    m["qUpdates"] = S("qUpdates"); m["explorations"] = S("explorations")
    m["exploreShare"] = 100 * num(met["explorations"]) / (num(met["explorations"]) + num(met["exploitations"]))
    fw = sorted((v.get("reportsReceivedFromOthers", 0.0) for v in nodes.values()), reverse=True)
    m["fwdTop10Share"] = 100 * sum(fw[:10]) / max(1.0, sum(fw))
    m["fwdMax"] = fw[0]
    # delay
    dl = [r for r in rep if r["fate"] == "delivered"]
    byr = defaultdict(list)
    for r in dl:
        byr[int(r["resolvedRound"])].append(num(r["pathDelayS"]))
    m["delayMs"] = 1000 * st.mean(num(r["pathDelayS"]) for r in dl)
    m["delayRoundMs"] = 1000 * st.mean(st.mean(v) for v in byr.values())
    m["wallS"], m["peakMiB"] = perf_of(cfg, seed, tok, rm, perf)
    series = dict(alive=alive, residual=[num(r["residualJ"]) for r in per],
                  delivered=[int(r["delivered"]) for r in per])
    pernode = {i: dict(residual=v["residualEnergy"], spent=v["txEnergy"] + v["rxEnergy"] + v["aggregationEnergy"],
                       fwd=v.get("reportsReceivedFromOthers", 0.0), rxFrames=v["rxFrames"], death=v["firstUnavailableRound"])
               for i, v in nodes.items()}
    ok = ("energy closes OK; slot accounting OK; per-round MATLAB invariants OK" in open(pre + "-summary.txt").read()
          and len(per) == 500 and len({r["reportIndex"] for r in rep}) == len(rep)
          and sc["PeriyarRiverNetwork.BS"]["deliveredReports"] == len(dl) == m["delivered"]
          and m["retriesDecoded"] <= m["retriesSent"])
    return m, series, pernode, ok


def ms(v, f="%.2f"):
    v = [x for x in v if not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return "–"
    return (f % st.mean(v)) + (" ± " + (f % st.stdev(v)) if len(v) > 1 else "")


KEYS = [("generated", "Generated reports", "%.0f"), ("delivered", "Delivered reports", "%.0f"),
        ("validPDR", "Valid-report delivery ratio (%)", "%.2f"), ("schedPDR", "Scheduled-slot delivery ratio (%)", "%.2f"),
        ("sourcePDR", "Source-packet PDR (%)", "%.2f"), ("realValidPDR", "  real KSPCB stations: valid-report ratio (%)", "%.2f"),
        ("replayValidPDR", "  virtual replay nodes: valid-report ratio (%)", "%.2f"),
        ("realDelivered", "  real KSPCB stations: delivered", "%.0f"), ("replayDelivered", "  virtual replay nodes: delivered", "%.0f"),
        ("lossChannel", "Channel losses (reports)", "%.0f"), ("lossNoCand", "No-eligible-next-hop losses", "%.0f"),
        ("deadSource", "Dead-source losses (valid slots, source unavailable)", "%.0f"), ("unattempted", "Unattempted (stranded)", "%.0f"),
        ("lossEnergy", "Energy losses", "%.0f"),
        ("residualJ", "Total residual energy (J of 400)", "%.2f"), ("usableResidualJ", "Usable residual energy (J)", "%.2f"),
        ("txJ", "TX energy (J)", "%.2f"), ("rxJ", "RX energy (J)", "%.2f"), ("aggJ", "Aggregation energy (J)", "%.3f"),
        ("retryJ", "Retry TX energy (J)", "%.2f"), ("eprMJ", "Energy per delivered report (mJ)", "%.3f"),
        ("FND", "First node failure (round)", "%.1f"), ("HND", "Half of nodes failed (round)", "%.1f"),
        ("LND", "Last node failed (round)", "%.1f"), ("finalAlive", "Operational nodes at round 500", "%.1f"),
        ("meanHops", "Mean delivered hops", "%.2f"), ("linkSuccess", "Link (frame) success rate", "%.4f"),
        ("frames", "Physical frames", "%.0f"), ("retriesSent", "Retries sent", "%.0f"),
        ("qUpdates", "Q-learning updates", "%.0f"), ("exploreShare", "Exploratory decisions (%)", "%.2f"),
        ("fwdTop10Share", "Forwarding: share of the 10 busiest nodes (%)", "%.2f"),
        ("delayMs", "End-to-end delay per report (ms)", "%.2f"), ("delayRoundMs", "Delay, round-weighted (ms)", "%.2f"),
        ("wallS", "Runtime per run (s)", "%.2f"), ("peakMiB", "Peak memory (MiB)", "%.1f")]
HIGHER = {"generated", "delivered", "validPDR", "schedPDR", "sourcePDR", "realValidPDR", "replayValidPDR", "realDelivered",
          "replayDelivered", "residualJ", "usableResidualJ", "FND", "HND", "LND", "finalAlive", "linkSuccess"}
LOWER = {"lossChannel", "lossNoCand", "deadSource", "unattempted", "lossEnergy", "eprMJ", "delayMs", "delayRoundMs"}


def load_stage(stage):
    seeds = DEV_SEEDS if stage == "dev" else FINAL_SEEDS
    rm = runmap()
    perf = {}
    if os.path.exists("logs_v2/performance_v2.csv"):
        for r in rows("logs_v2/performance_v2.csv"):
            perf[(r["config"], r["run"])] = (float(r["wallSeconds"]), float(r["peakWorkingSetMiB"]))
    out = {}
    for lab, sub, prefix, cfg, tok in variants(stage):
        if not glob.glob(os.path.join(ROOT, sub, f"{prefix}-seed*-metrics.csv")):
            continue
        out[lab] = {s: load(sub, prefix, cfg, tok, s, rm, perf) for s in seeds}
        out[lab]["_sub"] = sub
    return seeds, out


def cmd_table(stage):
    seeds, D = load_stage(stage)
    labs = list(D)
    base = labs[0]
    lines = [f"# 200-node RL-Hybrid, {stage} stage (seeds {seeds[0]}-{seeds[-1]}), extended OMNeT++ simulation", "",
             "Integrity (500 rounds, one fate per report, BS count = delivered, energy/slot/invariant checks, retries decoded <= sent): "
             + ", ".join(f"{l}: {sum(D[l][s][3] for s in seeds)}/{len(seeds)}" for l in labs), "",
             "## Mean ± sample sd", "", "| Metric | " + " | ".join(labs) + " |", "|---" * (len(labs) + 1) + "|"]
    for k, name, f in KEYS:
        lines.append(f"| {name} | " + " | ".join(ms([D[l][s][0][k] for s in seeds], f) for l in labs) + " |")
    lines += ["", f"## Paired difference vs {base} (mean ± sd over seeds; [better seeds / n])", "",
              "| Metric | " + " | ".join(labs[1:]) + " |", "|---" * len(labs) + "|"]
    for k, name, f in KEYS:
        cells = []
        for l in labs[1:]:
            d = [D[l][s][0][k] - D[base][s][0][k] for s in seeds]
            d = [x for x in d if not math.isnan(x)]
            if not d:
                cells.append("–"); continue
            b = sum(1 for x in d if (x > 0 if k in HIGHER else x < 0)) if (k in HIGHER or k in LOWER) else None
            t = (st.mean(d) / (st.stdev(d) / math.sqrt(len(d)))) if len(d) > 1 and st.stdev(d) > 0 else math.nan
            cells.append(f"{('%+' + f[1:]) % st.mean(d)} ± {f % (st.stdev(d) if len(d) > 1 else 0)}"
                         + (f" [{b}/{len(d)}]" if b is not None else "") + (f" t={t:+.1f}" if not math.isnan(t) else ""))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Per seed (valid-report ratio % / source PDR % / FND / alive at 500 / residual J / delay ms)", "",
              "| Variant | " + " | ".join(f"seed {s}" for s in seeds) + " |", "|---" * (len(seeds) + 1) + "|"]
    for l in labs:
        lines.append(f"| {l} | " + " | ".join(
            "%.2f / %.2f / %s / %d / %.1f / %.1f" % (D[l][s][0]["validPDR"], D[l][s][0]["sourcePDR"],
                                                    "%.0f" % D[l][s][0]["FND"] if not math.isnan(D[l][s][0]["FND"]) else "none",
                                                    D[l][s][0]["finalAlive"], D[l][s][0]["residualJ"], D[l][s][0]["delayMs"]) for s in seeds) + " |")
    sizes = []
    for l in labs:
        b = sum(os.path.getsize(p) for p in glob.glob(os.path.join(ROOT, D[l]["_sub"], "*")) if os.path.isfile(p))
        sizes.append(f"{l}: {b / 2**20:.0f} MiB (folder)")
    lines += ["", "Result-file size: " + "; ".join(sizes)]
    out = os.path.join(ROOT, stage, "comparison.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    with open(os.path.join(ROOT, stage, "per_seed_metrics.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["variant", "seed"] + [k for k, _, _ in KEYS])
        for l in labs:
            for s in seeds:
                w.writerow([l, s] + [D[l][s][0][k] for k, _, _ in KEYS])
    print("\n".join(lines))


def cmd_diag():
    seeds, D = load_stage("dev")
    B = D["Baseline"]
    print("## Baseline bottlenecks (seeds 42-46)")
    tot = lambda k: st.mean(B[s][0][k] for s in seeds)
    lost = tot("lossChannel") + tot("lossNoCand") + tot("lossEnergy") + tot("lossTTL") + tot("unattempted") + tot("deadSource")
    for k in ["lossChannel", "lossNoCand", "deadSource", "unattempted", "lossEnergy", "lossTTL"]:
        print(f"{k}: {tot(k):.0f} ({100 * tot(k) / lost:.1f}% of non-delivered valid reports)")
    deaths = [(i, p["death"]) for s in seeds for i, p in B[s][2].items() if not math.isnan(p["death"])]
    pos = {}
    for s in seeds:
        for r in rows(os.path.join(ROOT, "dev/baseline", f"V2_200Node-seed{s}-nodes.csv")):
            pos[(s, int(r["node"]))] = math.hypot(num(r["x"]) - 600, num(r["y"]) - 25)
    dead_d = [pos[(s, i)] for s in seeds for i, p in B[s][2].items() if not math.isnan(p["death"])]
    all_d = [pos[(s, i)] for s in seeds for i in B[s][2]]
    print(f"dead nodes per seed {[sum(1 for p in B[s][2].values() if not math.isnan(p['death'])) for s in seeds]}; "
          f"mean distance to BS of dead nodes {st.mean(dead_d):.0f} m vs all nodes {st.mean(all_d):.0f} m")
    for band in [(0, 100), (100, 200), (200, 300), (300, 400), (400, 650)]:
        n_all = sum(1 for x in all_d if band[0] <= x < band[1]); n_dead = sum(1 for x in dead_d if band[0] <= x < band[1])
        fwd = [B[s][2][i]["fwd"] for s in seeds for i in B[s][2] if band[0] <= pos[(s, i)] < band[1]]
        spent = [B[s][2][i]["spent"] for s in seeds for i in B[s][2] if band[0] <= pos[(s, i)] < band[1]]
        print(f"  distance to BS {band[0]}-{band[1]} m: {n_all} nodes, {n_dead} died ({100 * n_dead / max(1, n_all):.0f}%), "
              f"mean reports forwarded {st.mean(fwd) if fwd else 0:.0f}, mean energy spent {st.mean(spent) if spent else 0:.3f} J")
    real_dead = sum(1 for s in seeds for i in REAL if not math.isnan(B[s][2][i]["death"]))
    print(f"real station nodes (1-10) that died: {real_dead} of 50 (5 seeds)")
    # seed-42 decision log: where do no-candidate losses and channel losses happen?
    dd = os.path.join(ROOT, "dev/baseline_diag")
    dec = rows(os.path.join(dd, "V2_200Node_Diag-seed42-decisions.csv"))
    hops = rows(os.path.join(dd, "V2_200Node_Diag-seed42-hops.csv"))
    rep = rows(os.path.join(dd, "V2_200Node_Diag-seed42-reports.csv"))
    nodes = {int(r["node"]): (num(r["x"]), num(r["y"])) for r in rows(os.path.join(dd, "V2_200Node_Diag-seed42-nodes.csv"))}
    dbs = {k: math.hypot(x - 600, y - 25) for k, (x, y) in nodes.items()}
    lost_nc = [r for r in rep if r["fate"] == "lost_no_candidate"]
    rounds_nc = [int(r["resolvedRound"]) for r in lost_nc]
    print(f"seed 42: {len(lost_nc)} no-candidate losses; by round quartile "
          f"{[sum(1 for x in rounds_nc if q * 125 < x <= (q + 1) * 125) for q in range(4)]}")
    tx = [h for h in hops]
    print(f"seed 42: frame success {sum(1 for h in tx if num(h['outcome']) == 1) / len(tx):.3f}; mean true LQ of chosen links "
          f"{st.mean(num(h['trueLQ']) for h in tx):.3f}; member-hop success "
          f"{st.mean(1.0 if num(h['outcome']) == 1 else 0.0 for h in tx if h['hopType'] == '1'):.3f}; route-hop success "
          f"{st.mean(1.0 if num(h['outcome']) == 1 else 0.0 for h in tx if h['hopType'] in ('2', '3')):.3f}")
    rd = [r for r in dec if r["hopType"] in ("2", "3")]
    print(f"seed 42: route decisions {len(rd)}; mean feasible candidates {st.mean(int(r['numCandidates']) for r in rd):.1f}; "
          f"share choosing BS {sum(1 for r in rd if r['hopType'] == '3') / len(rd):.3f}; exploratory {st.mean(int(r['explored']) for r in rd):.3f}")
    cl = [r for r in dec if r["hopType"] in ("0", "1")]
    print(f"seed 42: cluster decisions {len(cl)}; self-head share {sum(1 for r in cl if r['hopType'] == '0') / len(cl):.3f}; "
          f"mean cluster candidates {st.mean(int(r['numCandidates']) for r in cl):.1f}")
    # what kills nodes: energy by role
    un = rows(os.path.join(dd, "V2_200Node_Diag-seed42-unavailability.csv"))
    print("seed 42 death reasons:", Counter(r["reason"] for r in un if r["reason"]).most_common())
    per = rows(os.path.join(dd, "V2_200Node_Diag-seed42-per_round.csv"))
    for q in range(5):
        sl = per[q * 100:(q + 1) * 100]
        g = sum(int(r["sourceAvailable"]) for r in sl); d = sum(int(r["delivered"]) for r in sl)
        nc = sum(int(r["lossNoCandidate"]) for r in sl); ch = sum(int(r["lossChannel"]) for r in sl)
        print(f"seed 42 rounds {q * 100 + 1}-{(q + 1) * 100}: alive end {per[(q + 1) * 100 - 1]['aliveCount']}, source PDR "
              f"{100 * d / max(1, g):.1f}%, channel losses {ch}, no-candidate {nc}, epsilon {num(sl[0]['epsilon']):.3f}")


def cmd_plots(stage):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    seeds, D = load_stage(stage)
    labs = list(D)
    gd = os.path.join(ROOT, stage, "graphs")
    os.makedirs(gd, exist_ok=True)
    note = f"200 nodes, 600 x 50 m, 500 rounds, seeds {seeds[0]}-{seeds[-1]} (mean ± sd) - extended OMNeT++ simulation"
    cmap = plt.get_cmap("tab20")
    col = ["#000000"] + [cmap(i) for i in range(20)]        # baseline black, then 20 distinct colours

    def bar(key, title, fname, ylabel):
        fig, ax = plt.subplots(figsize=(11, 5))
        mv = [st.mean(D[l][s][0][key] for s in seeds) for l in labs]
        sd = [st.stdev(D[l][s][0][key] for s in seeds) for l in labs]
        ax.bar(range(len(labs)), mv, yerr=sd, capsize=4, color=[col[i % len(col)] for i in range(len(labs))])
        ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs, rotation=25, ha="right", fontsize=8)
        ax.set_ylabel(ylabel); ax.set_title(title + "\n" + note, fontsize=10); ax.grid(axis="y", alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(gd, fname), dpi=140); plt.close(fig)
        with open(os.path.join(gd, fname.replace(".png", ".csv")), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["variant", "mean", "sd"] + [f"seed{s}" for s in seeds])
            for l, a, b in zip(labs, mv, sd):
                w.writerow([l, a, b] + [D[l][s][0][key] for s in seeds])

    def series(key, title, fname, ylabel, cumulative=False):
        fig, ax = plt.subplots(figsize=(11, 5))
        with open(os.path.join(gd, fname.replace(".png", ".csv")), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["round"] + labs)
            cols = []
            for i, l in enumerate(labs):
                arr = [D[l][s][1][key] for s in seeds]
                if cumulative:
                    arr = [[sum(a[:r + 1]) for r in range(len(a))] for a in arr]
                mean = [st.mean(x) for x in zip(*arr)]
                cols.append(mean)
                ax.plot(range(1, 501), mean, label=l, lw=1.4 if i else 2.4, color=col[i % len(col)])
            for r in range(500):
                w.writerow([r + 1] + [c[r] for c in cols])
        ax.set_xlabel("round"); ax.set_ylabel(ylabel); ax.set_title(title + "\n" + note.replace("(mean ± sd)", "(mean over seeds)"), fontsize=10)
        ax.grid(alpha=0.3); ax.legend(fontsize=7, ncol=2)
        fig.tight_layout(); fig.savefig(os.path.join(gd, fname), dpi=140); plt.close(fig)

    bar("validPDR", "1. Valid-report delivery ratio", "01_delivery_ratio.png", "delivered / valid-data reports (%)")
    bar("sourcePDR", "2. Source-packet PDR", "02_source_pdr.png", "delivered / generated reports (%)")
    series("alive", "3. Operational nodes", "03_operational_nodes.png", "operational nodes (of 200)")
    series("residual", "4. Total residual energy", "04_residual_energy.png", "residual energy (J of 400)")
    series("delivered", "5. Cumulative delivered reports", "05_cumulative_delivered.png", "reports delivered to the BS", True)
    bar("delayMs", "6. End-to-end delay per delivered report", "06_delay.png", "ms")
    bar("eprMJ", "7. Energy per delivered report", "07_energy_per_report.png", "mJ")
    # 8 per-node energy distribution (spent energy, all nodes of all seeds)
    fig, ax = plt.subplots(figsize=(11, 5))
    data = [[D[l][s][2][i]["spent"] for s in seeds for i in D[l][s][2]] for l in labs]
    ax.boxplot(data, showfliers=False); ax.set_xticks(range(1, len(labs) + 1)); ax.set_xticklabels(labs, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("energy spent per node in 500 rounds (J of 2 J)"); ax.set_title("8. Per-node energy distribution\n" + note, fontsize=10)
    ax.grid(axis="y", alpha=0.3); fig.tight_layout(); fig.savefig(os.path.join(gd, "08_per_node_energy.png"), dpi=140); plt.close(fig)
    with open(os.path.join(gd, "08_per_node_energy.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["variant", "seed", "node", "spentJ", "residualJ", "reportsForwarded", "firstUnavailableRound"])
        for l in labs:
            for s in seeds:
                for i, p in sorted(D[l][s][2].items()):
                    w.writerow([l, s, i, p["spent"], p["residual"], p["fwd"], p["death"]])
    # 9 real vs virtual
    fig, ax = plt.subplots(figsize=(11, 5))
    x = range(len(labs)); wdt = 0.38
    for j, (k, lab) in enumerate([("realValidPDR", "10 real KSPCB station nodes"), ("replayValidPDR", "190 virtual replay nodes")]):
        mv = [st.mean(D[l][s][0][k] for s in seeds) for l in labs]; sd = [st.stdev(D[l][s][0][k] for s in seeds) for l in labs]
        ax.bar([i + (j - 0.5) * wdt for i in x], mv, wdt, yerr=sd, capsize=3, label=lab)
    ax.set_xticks(list(x)); ax.set_xticklabels(labs, rotation=25, ha="right", fontsize=8); ax.legend(fontsize=8)
    ax.set_ylabel("valid-report delivery ratio (%)"); ax.set_title("9. Real-station vs virtual-node delivery\n" + note, fontsize=10)
    ax.grid(axis="y", alpha=0.3); fig.tight_layout(); fig.savefig(os.path.join(gd, "09_real_vs_virtual.png"), dpi=140); plt.close(fig)
    # 10 forwarding distribution (Lorenz-style: share of forwarding carried by the busiest k% of nodes)
    fig, ax = plt.subplots(figsize=(11, 5))
    with open(os.path.join(gd, "10_forwarding_distribution.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["variant", "busiest_nodes_percent", "share_of_forwarded_reports_percent"])
        for i, l in enumerate(labs):
            curves = []
            for s in seeds:
                fw = sorted((p["fwd"] for p in D[l][s][2].values()), reverse=True); tot = max(1.0, sum(fw))
                acc, cur = 0.0, []
                for v in fw:
                    acc += v; cur.append(100 * acc / tot)
                curves.append(cur)
            mean = [st.mean(c) for c in zip(*curves)]
            xs = [100 * (k + 1) / N for k in range(N)]
            ax.plot(xs, mean, label=l, color=col[i % len(col)], lw=2.4 if i == 0 else 1.4)
            for a, b in zip(xs, mean):
                w.writerow([l, a, b])
    ax.plot([0, 100], [0, 100], "k:", lw=1, label="perfectly even")
    ax.set_xlabel("busiest nodes (% of 200)"); ax.set_ylabel("share of all reports forwarded (%)")
    ax.set_title("10. Routing workload: concentration of forwarding\n" + note, fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=7, ncol=2); fig.tight_layout()
    fig.savefig(os.path.join(gd, "10_forwarding_distribution.png"), dpi=140); plt.close(fig)
    print("graphs:", gd)


def cmd_runmaps():
    os.makedirs(os.path.join(ROOT, "runmaps"), exist_ok=True)
    cfgs = sorted({v[3] for v in DEV} | {v[3] for st_ in ("dev", "final") for v in variants(st_)} | {"V2_200Node_Diag"})
    exe = os.path.abspath("RLHybrid_Scalability_Experiment.exe" if os.name == "nt" else "RLHybrid_Scalability_Experiment")
    for c in cfgs:
        out = subprocess.run([exe, "-u", "Cmdenv", "-c", c, "-q", "runs"], capture_output=True, text=True).stdout
        open(os.path.join(ROOT, "runmaps", c + ".txt"), "w").write(out)
        print(c, out.count("Run "), "runs")


if __name__ == "__main__":
    {"table": lambda: cmd_table(sys.argv[2]), "diag": cmd_diag, "plots": lambda: cmd_plots(sys.argv[2]),
     "runmaps": cmd_runmaps}[sys.argv[1]]()
