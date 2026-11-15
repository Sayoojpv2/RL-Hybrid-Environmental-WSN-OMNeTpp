"""Event annotations for the event-aware RL-Hybrid option (Controller.eventAnnotations).

Usage: python -P tools/build_event_annotations.py            (all datasets of data/scenarios/)
Writes data/events/<dataset>.csv (one row per Mode 2 report: m2_report = 1) and data/events/event_summary.csv.
The datasets are read only; nothing in data/scenarios/ changes.

Classes (SIMULATION RULES of this study, built on documented thresholds; they are not official alarm categories):
  0 routine   no profile alarm threshold exceeded by the report's round value
  1 warning   a valid value exceeds a documented alarm threshold of its sensor profile
              (scenario_study/dataset_metadata/sensor_profiles.json "alarms": CPCB water-quality criteria, Environment
              (Protection) Rules 1986 Schedule VI, India NAAQS 2009; the soil thresholds are labelled ASSUMPTION there).
              This is exactly the dataset's alarm_flag, recomputed here and checked row by row.
  2 critical  the same threshold is exceeded in >= 3 consecutive DISTINCT samples of the node (persistence rule; a held
              KSPCB grab sample repeated over several rounds counts once)
Trigger = the exceeded rule with the largest relative exceedance (critical: among the persistent rules); the event report
carries its field id (1 B) and value (2 B, same scaled 16-bit encoding as the payload) in addition to the 10 B app header,
which already holds node id, round (timestamp), profile id (scenario) and the alarm/priority flags.
Deadlines (SIMULATION TARGETS, measured from report generation = round start): critical 2 s (one decision window),
warning 10 s, routine 100 s (one round period).
"""
import csv, json, math, pathlib, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILES = json.loads((ROOT / "scenario_study/dataset_metadata/sensor_profiles.json").read_text())["profiles"]
SCEN = ROOT / "data/scenarios"
OUT = ROOT / "data/events"
DEADLINE = {0: 100.0, 1: 10.0, 2: 2.0}
PERSIST = 3
# global 1-byte field ids (profile order, payload fields then extension fields)
FIELD_ID = {}
for p in PROFILES.values():
    for f in p["fields"] + p.get("extension_fields", []):
        FIELD_ID.setdefault(f["name"], len(FIELD_ID) + 1)
UNIT = {f["name"]: f["unit"] for p in PROFILES.values() for f in p["fields"] + p.get("extension_fields", [])}


def num(s):
    try:
        v = float(s)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def exceedance(a, v):
    """relative exceedance of rule a by value v (> 0 when violated), else None"""
    if a["op"] == "outside":
        e = max((a["lo"] - v) / abs(a["lo"]), (v - a["hi"]) / abs(a["hi"]))
    elif a["op"] == ">":
        e = (v - a["value"]) / abs(a["value"])
    else:
        e = (a["value"] - v) / abs(a["value"])
    return e if e > 0 else None


def rule_text(a):
    return f"{a['field']} outside [{a['lo']}, {a['hi']}]" if a["op"] == "outside" else f"{a['field']} {a['op']} {a['value']}"


def annotate(dataset):
    prof = PROFILES[dataset.rsplit("_", 1)[0]]
    rules = prof["alarms"]
    rows = list(csv.DictReader(open(SCEN / dataset / "observations.csv", newline="")))
    fields = [f["name"] for f in prof["fields"] + prof.get("extension_fields", [])]
    out, run, last = {}, {}, {}
    rows.sort(key=lambda w: (int(w["node_id"]), int(w["round"])))
    for w in rows:
        node, rnd = int(w["node_id"]), int(w["round"])
        if node not in last:
            last[node], run[node] = None, [0] * len(rules)
        ex = [exceedance(a, v) if (v := num(w.get(a["field"]))) is not None else None for a in rules]
        assert int(w["alarm_flag"]) == int(any(e is not None for e in ex)), f"{dataset} node {node} round {rnd}: alarm_flag"
        key = (w["env_time"], tuple(w.get(f, "") for f in fields))
        if key != last[node]:                      # a new distinct sample: update the persistence counters
            last[node] = key
            run[node] = [(c + 1 if e is not None else 0) for c, e in zip(run[node], ex)]
        if w["m2_report"] != "1":
            continue
        cand = [i for i, e in enumerate(ex) if e is not None]
        persistent = [i for i in cand if run[node][i] >= PERSIST]
        cls = 2 if persistent else (1 if cand else 0)
        pick = max(persistent or cand, key=lambda i: ex[i]) if cand else None
        a = rules[pick] if pick is not None else None
        out[(node, rnd)] = {
            "node_id": node, "round": rnd, "event_class": cls,
            "trigger_field": FIELD_ID[a["field"]] if a else -1,
            "trigger_value": num(w[a["field"]]) if a else 0, "deadline_s": DEADLINE[cls],
            "trigger_name": a["field"] if a else "", "unit": UNIT.get(a["field"], "") if a else "",
            "threshold_rule": rule_text(a) if a else "", "rule_class": a["class"] if a else "",
            "rule_source": a["source"] if a else "", "relative_exceedance": round(ex[pick], 6) if a else 0,
            "persistence_samples": run[node][pick] if a else 0, "quality_flag": w["quality_flag"],
            "env_time": w["env_time"], "profile": prof["code"], "sample_id": w["sample_id"]}
        if a:                                      # the trigger is a valid measurement that breaks its rule
            assert exceedance(a, out[(node, rnd)]["trigger_value"]) is not None
    return out


def write(dataset, ev):
    OUT.mkdir(exist_ok=True)
    cols = list(next(iter(ev.values())).keys())
    with open(OUT / f"{dataset}.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, cols)
        wr.writeheader()
        wr.writerows(ev[k] for k in sorted(ev))
    c = Counter(e["event_class"] for e in ev.values())
    t = Counter(e["trigger_name"] for e in ev.values() if e["event_class"] > 0)
    return [dataset, len(ev), c[0], c[1], c[2], ";".join(f"{k}:{v}" for k, v in t.most_common())]


summary = []
for n in (200, 500):
    base = {}
    for p in ("water_quality", "industrial_effluent", "air_quality", "soil_monitoring"):
        ds = f"{p}_{n}"
        base[ds] = annotate(ds)
        summary.append(write(ds, base[ds]))
    mixed = {}
    for m in csv.DictReader(open(SCEN / f"mixed_environment_{n}" / "node_map.csv", newline="")):
        src = m["source_dataset"].split("/")[0]
        k = int(m["node_id"])
        assert int(m["source_node_id"]) == k
        mixed.update({key: e for key, e in base[src].items() if key[0] == k})
    summary.append(write(f"mixed_environment_{n}", mixed))

with open(OUT / "event_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows([["dataset", "reports", "routine", "warning", "critical", "event_triggers"]] + summary)
for s in summary:
    print(f"{s[0]:26s} reports {s[1]:7d}  routine {s[2]:7d}  warning {s[3]:6d}  critical {s[4]:6d}  {s[5][:90]}")
print("field ids:", FIELD_ID)
sys.exit(0)
