#!/usr/bin/env python3
"""Stage D: relay-density scaling table (mean +/- sample sd, n-1) across node counts.

Usage: python3 tools/scaling_table.py <Config50> <Config...>   -> prints Markdown
Columns are configurations (e.g. Periyar50_Baseline Periyar100_RelayScaling Periyar250_RelayScaling);
each uses every seed whose metrics file exists. FND = -1 (no node became unavailable in 1000
rounds) is right-censored: it is excluded from the mean and the count of censored seeds is shown.
"""
import csv, glob, os, re, statistics as st, sys

sys.stdout.reconfigure(encoding="utf-8")
configs = sys.argv[1:]

def rows(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

def load(cfg):
    data = {}
    for p in sorted(glob.glob(os.path.join("results", f"{cfg}-seed*-metrics.csv"))):
        s = int(re.search(r"-seed(\d+)-metrics", p).group(1))
        m = dict(rows(p)[0])
        sca = glob.glob(os.path.join("results", f"{cfg}-seed={s}-#*.sca"))[0]
        n = 0
        for line in open(sca):
            q = line.split()
            if len(q) >= 4 and q[0] == "scalar":
                if q[1] == "PeriyarRiverNetwork.BS" and q[2] == "latency:mean":
                    m["latency"] = q[3]
                if q[2] == "residualEnergy" and (".n" in q[1] or ".relay[" in q[1] or ".node[" in q[1]):
                    n += 1
        m["N"] = n
        m["deliveredPerEmitted"] = 100.0 * float(m["delivered"]) / float(m["sourceAvailable"])
        m["residualPct"] = 100.0 * float(m["residualJ"]) / (2.0 * n)
        m["sourceUnavailable"] = float(m["workloadAvailable"]) - float(m["sourceAvailable"])
        data[s] = m
    return data

D = {c: load(c) for c in configs}

def ms(vals, fmt):
    if not vals:
        return "–"
    if len(vals) == 1:
        return fmt % vals[0]
    return (fmt % st.mean(vals)) + " ± " + (fmt % st.stdev(vals))

metrics = [("Battery nodes N", "N", "%.0f"), ("Seeds", None, None),
           ("Scheduled report slots", "scheduled", "%.0f"), ("Slots with valid data", "workloadAvailable", "%.0f"),
           ("Slots lost: source unavailable", "sourceUnavailable", "%.1f"),
           ("Reports emitted", "sourceAvailable", "%.1f"), ("Reports delivered", "delivered", "%.1f"),
           ("PDR = delivered / scheduled (%)", "PDR", "%.2f"), ("Delivered / emitted (%)", "deliveredPerEmitted", "%.2f"),
           ("Network losses (all causes)", "stageLoss", "%.1f"), ("  - channel", "lossChannel", "%.1f"),
           ("  - energy", "lossEnergy", "%.1f"), ("  - no feasible candidate", "lossNoCandidate", "%.1f"),
           ("  - TTL (15 hops)", "lossTTL", "%.1f"), ("Unattempted reports", "unattempted", "%.1f"),
           ("FND, first round with < N operational", "FND", "%.1f"), ("Operational nodes at end", "finalAlive", "%.2f"),
           ("Residual energy (J, of 2N J)", "residualJ", "%.2f"), ("Residual energy (% of initial)", "residualPct", "%.2f"),
           ("Energy spent (J)", "spentJ", "%.3f"), ("Energy per delivered report (J)", "energyPerDeliveredJ", "%.5f"),
           ("Mean delivered hops", "meanHops", "%.2f"), ("Mean path delay (s; Σ per hop k/Rbit + Tproc + d/c)", "meanDelayS", "%.4f"),
           ("Mean latency round start → BS (s, OMNeT++ time)", "latency", "%.3f"),
           ("Q-table updates", "qUpdates", "%.1f"), ("Exploratory decisions", "explorations", "%.1f"),
           ("Physical frames", "physicalFrames", "%.1f")]
print("| Metric | " + " | ".join(configs) + " |")
print("|---" * (len(configs) + 1) + "|")
for label, key, fmt in metrics:
    cells = []
    for c in configs:
        d = D[c]
        if key is None:
            cells.append(", ".join(str(s) for s in sorted(d)))
        elif key == "FND":
            v = [float(d[s]["FND"]) for s in d if float(d[s]["FND"]) > 0]
            cen = sum(1 for s in d if float(d[s]["FND"]) < 0)
            cells.append(ms(v, fmt) + (f" (+{cen} seed(s) with none in 1000 rounds)" if cen else ""))
        else:
            cells.append(ms([float(d[s][key]) for s in d], fmt))
    print(f"| {label} | " + " | ".join(cells) + " |")
print()
base = D[configs[0]]
for c in configs[1:]:
    common = sorted(set(base) & set(D[c]))
    if not common:
        continue
    print(f"Paired difference {c} − {configs[0]} (seeds {', '.join(map(str, common))}):")
    for label, key in [("PDR (pp)", "PDR"), ("delivered", "delivered"), ("source-unavailable slots", "sourceUnavailable"),
                       ("channel losses", "lossChannel"), ("mean hops", "meanHops"), ("energy per delivered report (J)", "energyPerDeliveredJ"),
                       ("final operational nodes", "finalAlive")]:
        diff = [float(D[c][s][key]) - float(base[s][key]) for s in common]
        fmt2 = "%+.4f" if "J" in label else "%+.2f"
        print(f"* {label}: {ms(diff, fmt2).replace('± +', '± ')}  (per seed: {', '.join('%+.4g' % x for x in diff)})")
    print()
print("Per seed:")
for c in configs:
    print(f"* {c}: " + "; ".join(f"seed {s}: PDR {float(D[c][s]['PDR']):.2f} %, delivered {D[c][s]['delivered']}, "
                                 f"FND {D[c][s]['FND']}, final {D[c][s]['finalAlive']}" for s in sorted(D[c])))
