#!/usr/bin/env python3
"""Dataset-loader verification (Loader_TestFixture, Loader_PeriyarClean; 20 rounds).

Usage: python3 tools/verify_loader.py make-variant      -> writes results_loader_test/variant/fixture_values_shifted.csv
       python3 tools/verify_loader.py check             -> PASS/FAIL lines

The expected workload is recomputed here independently from the configuration (not from the C++ code):
read CSV by column name, stable sort by (time, station), validity per field, drop/keepNaN, uniform
timestamp->round milestones, schedule every reportInterval rounds, sampleAndHold (LOCF) or freshOnly.
"""
import csv, math, os, sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
OUT = "results_loader_test"
fails, lines = [], []


def check(ok, msg):
    lines.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def num(s):
    try:
        v = float(s.strip())
        return v
    except ValueError:
        return math.nan


def in_range(v, lo, hi):
    if math.isnan(v):
        return False
    lo_x, hi_x = lo.startswith(">"), hi.startswith("<")
    l = float(lo.lstrip("><").replace("inf", "inf")); h = float(hi.lstrip("><"))
    return (v > l if lo_x else v >= l) and (v < h if hi_x else v <= h)


def expected(path, tcol, scol, fields, smap, policy, hold, interval, rounds):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    recs = [(r[scol], r[tcol], [num(r[c]) for c, *_ in fields]) for r in rows]
    recs.sort(key=lambda x: (x[1], x[0]))                     # stable
    clean = []
    for st, t, v in recs:
        ok = [in_range(x, lo, hi) for x, (_, _, _, lo, hi) in zip(v, fields)]
        v = [x if o else math.nan for x, o in zip(v, ok)]
        if (all(ok) if policy == "drop" else any(ok)):
            clean.append((st, t, v))
    times = sorted({t for _, t, _ in clean})
    U = len(times)
    mil = {t: (1 if U == 1 else 1 + int(math.floor(k * (rounds - 1) / (U - 1) + 0.5))) for k, t in enumerate(times)}
    obs = {s: sorted([(t, mil[t], v) for st, t, v in clean if st == s], key=lambda x: x[0]) for s, _ in smap}
    out, sched = [], 0
    for r in range(1, rounds + 1):
        if (r - 1) % interval:
            continue
        for s, nd in smap:
            sched += 1
            act = None
            for t, m, v in obs[s]:
                if (m <= r) if hold == "sampleAndHold" else (m == r):
                    act = (t, v)
            if act:
                out.append((len(out) + 1, r, nd, s, act[0], act[1]))
    return len(rows), len(clean), U, sched, out


def same(a, b):
    return (math.isnan(a) and math.isnan(b)) or a == b


def verify(cfg, path, tcol, scol, fields, smap, policy, hold, interval, wrounds, nfields_names):
    pre = os.path.join(OUT, f"{cfg}-seed42")
    raw, valid, U, sched, exp = expected(path, tcol, scol, fields, smap, policy, hold, interval, wrounds)
    with open(pre + "-workload.csv", newline="") as f:
        got = list(csv.DictReader(f))
    hdr = list(got[0].keys())
    check(hdr == ["reportIndex", "round", "sourceNode", "station", "date"] + nfields_names,
          f"{cfg}: workload columns {hdr[5:]}")
    summ = open(pre + "-workload_summary.txt").read().split("\n")[0].split()
    kv = dict(zip(summ[0::2], summ[1::2]))
    check(int(kv["raw"]) == raw and int(kv["valid"]) == valid and int(kv["dates"]) == U and int(kv["scheduled"]) == sched
          and int(kv["available"]) == len(exp),
          f"{cfg}: raw {kv['raw']}, valid {kv['valid']}, unique times {kv['dates']}, scheduled {kv['scheduled']}, with data {kv['available']} "
          f"(expected {raw}/{valid}/{U}/{sched}/{len(exp)})")
    match = len(got) == len(exp) and all(
        int(g["reportIndex"]) == e[0] and int(g["round"]) == e[1] and int(g["sourceNode"]) == e[2] and g["station"] == e[3]
        and g["date"] == e[4] and all(same(num(g[n]), x) for n, x in zip(nfields_names, e[5])) for g, e in zip(got, exp))
    nan_vals = sum(1 for g in got for n in nfields_names if math.isnan(num(g[n])))
    check(match, f"{cfg}: all {len(got)} reports match the independent recomputation (round, node, station, timestamp, "
                 f"every payload value; {nan_vals} NaN payload values)")
    pf = list(csv.DictReader(open(pre + "-payload_fields.csv")))
    check([p["name"] for p in pf] == nfields_names and [p["unit"] for p in pf] == [f[2] for f in fields]
          and [p["datasetColumn"] for p in pf] == [f[0] for f in fields] and all(p["origin"] == "dataset" for p in pf),
          f"{cfg}: payload field names/units/columns " + ", ".join(f"{p['name']}[{p['unit']}]<-{p['datasetColumn']}" for p in pf))
    rep = list(csv.DictReader(open(pre + "-reports.csv")))
    dec = list(csv.DictReader(open(pre + "-decisions.csv")))
    mapped = {nd for _, nd in smap}
    srcs = {int(r["sourceNode"]) for r in rep}
    actors = {int(r["actor"]) for r in dec if r["hopType"] in ("0", "1")}
    simulated = len(list(csv.DictReader(open(pre + "-per_round.csv"))))
    check(srcs <= mapped and actors <= mapped and {int(r["reportIndex"]) for r in rep} == {e[0] for e in exp if e[1] <= simulated},
          f"{cfg}: report sources {sorted(srcs)} and cluster-phase actors {sorted(actors)} are mapped nodes {sorted(mapped)}; "
          f"every workload report of the {simulated} simulated rounds has exactly one fate")
    fates = Counter(r["fate"] for r in rep)
    s = open(pre + "-summary.txt").read()
    check("slot accounting OK" in s and "energy closes OK" in s, f"{cfg}: accounting OK; fates {dict(fates)}")
    # end-to-end payload: values in the frames received by the BS == the workload values of those reports
    dp = list(csv.DictReader(open(pre + "-delivered_payload.csv")))
    wl = {g["reportIndex"]: g for g in got}
    intact = all(all(d[n] == wl[d["reportIndex"]][n] for n in ["sourceNode", "station", "date"] + nfields_names) for d in dp)
    delivered_ids = {r["reportIndex"] for r in rep if r["fate"] == "delivered"}
    check(intact and {d["reportIndex"] for d in dp} == delivered_ids,
          f"{cfg}: {len(dp)} delivered reports; payload received at the BS identical to the dataset values for every one")
    return fates["delivered"]
    per = list(csv.DictReader(open(pre + "-per_round.csv")))
    exp_sched = Counter(e[1] for e in exp)
    sched_ok = all(int(p["scheduled"]) == (len(smap) if (int(p["round"]) - 1) % interval == 0 else 0)
                   and int(p["workloadAvailable"]) == exp_sched.get(int(p["round"]), 0) for p in per)
    check(sched_ok, f"{cfg}: per-round scheduled/with-data slots follow the schedule (interval {interval}, {hold})")


if sys.argv[1] == "make-variant":
    os.makedirs(os.path.join(OUT, "variant"), exist_ok=True)
    src = list(csv.reader(open("data/TEST_FIXTURE_not_real_data.csv", newline="")))
    payload_cols = {"nitrate_mgL", "water_temp_C", "turbidity_NTU"}
    hdr = src[0]
    with open(os.path.join(OUT, "variant", "fixture_values_shifted.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(hdr)
        for r in src[1:]:
            # shift every in-range payload value by +0.5 (validity pattern unchanged; 99.0 stays out of range)
            w.writerow([("%.2f" % (num(x) + 0.5)) if h in payload_cols and not math.isnan(num(x)) and num(x) < 90 else x
                        for h, x in zip(hdr, r)])
    print("variant written")
    sys.exit(0)

FIX = [("water_temp_C", "waterTemp", "degC", "0", "40"), ("turbidity_NTU", "turbidity", "NTU", "0", "1000"),
       ("nitrate_mgL", "nitrate", "mg/L", "0", "50")]
delivered = {}
delivered["fixture"] = verify("Loader_TestFixture", "data/TEST_FIXTURE_not_real_data.csv", "timestamp", "site_id", FIX,
       [("TESTFIX-A", 7), ("TESTFIX-B", 23), ("TESTFIX-C", 41)], "drop", "freshOnly", 1, 20, ["waterTemp", "turbidity", "nitrate"])
CLEAN = [("Temperature", "temperature", "degC", "15", "50"), ("pH", "pH", "pH", "0", "14"),
         ("TDS", "TDS", "unspecified", ">0", "inf"), ("DO", "DO", "unspecified", ">0", "inf")]
CMAP = [("VETTUKADAVU", 5), ("MANJUMMAL BUND", 10), ("PUTHALAM KADAVU", 15), ("PATHALAM BRIDGE", 20), ("PATHALAM BUND D/S", 25),
        ("PATHALAM BUND U/S", 30), ("PURAPILLIKADAVU BUND DS", 35), ("PURAPILLIKADAVU BUND NAVIGATION", 40),
        ("PURAPILLIKADAVU US", 45), ("ALUVA - MANAPPURAM", 50)]
delivered["clean"] = verify("Loader_PeriyarClean", "data/Periyar_WaterQuality_Clean.csv", "Date", "Location", CLEAN, CMAP, "keepNaN",
       "sampleAndHold", 2, 1000, ["temperature", "pH", "TDS", "DO"])

check(sum(delivered.values()) > 0, f"packet delivery observed: {delivered} reports delivered (fixture, clean)")

# payload independence: same fixture with shifted measurement values -> identical routing outputs
a = os.path.join(OUT, "Loader_TestFixture-seed42")
b = os.path.join(OUT, "variant", "Loader_TestFixture-seed42")
ident = {k: open(f"{a}-{k}", "rb").read() == open(f"{b}-{k}", "rb").read()
         for k in ["decisions.csv", "reports.csv", "per_round.csv", "metrics.csv", "unavailability_events.csv"]}
wl_differs = open(f"{a}-workload.csv", "rb").read() != open(f"{b}-workload.csv", "rb").read()
check(all(ident.values()) and wl_differs,
      f"payload independence: measurement values changed (workload differs: {wl_differs}); routing outputs identical: {ident}")

print("\n".join(lines))
print(f"\n{len(lines)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
