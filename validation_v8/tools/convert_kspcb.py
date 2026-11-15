#!/usr/bin/env python3
"""Convert raw KSPCB 'consdata-*.csv' river-quality sheets into the workload loader's long CSV format.

Usage: python3 tools/convert_kspcb.py <input dir> <output dir>

Input (one file per sampling point, wide layout): title rows, "Sampling point: <station>", then one or more
tables whose header row is "Sl. No, Parameter, Unit, <date>, <date>, ..." and whose rows are parameters.
Output (never touches the inputs):
  kspcb_long.csv      Location,Date,<parameter columns>   one row per (station, date) with >= 1 retained value;
                      values are the ORIGINAL numeric strings; empty cell = no retained value
  kspcb_fields.csv    column, raw parameter label, raw unit, normalised unit, retained count, min, max
  kspcb_cell_log.csv  every non-empty source cell that was NOT written as a value, with the reason
                      (plus kept-but-flagged cells), so that every source cell is accounted for
  kspcb_sources.csv   per input file: MD5, station, tables, date-column and record accounting
Rules (no value is invented; nothing is dropped without a log entry):
  * dates d.m.yyyy or d.m.yy; a date column outside the report period stated in the title, an unparseable
    header, or values under an empty header -> whole column rejected
  * rows without a serial number / parameter label (unlabelled rows or blocks) -> cells rejected
  * '#' not measured (CEE direction), '*' code, 'BDL' below detection limit, '#DIV/0!', single letters
    (annotation text written down a column), '"' in a value cell -> not a measurement, logged
  * physically impossible values rejected: Temperature <= 0 or > 50 degC, pH outside 0..14,
    Conductivity / TDS <= 0, any negative value; DO = 0 kept but flagged
  * same (station, date) more than once: identical values -> deduplicated; different values -> conflict,
    no value kept for that parameter (both logged)
"""
import csv, datetime, glob, hashlib, os, re, sys
from collections import OrderedDict, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

PARAM_COLUMNS = OrderedDict([   # raw label (normalised) -> output column
    ("temperature", "Temperature"), ("ph", "pH"), ("conductivity", "Conductivity"), ("tds", "TDS"),
    ("turbidity", "Turbidity"), ("colour", "Colour"), ("ss", "SS"), ("chlorides", "Chlorides"), ("hardness", "Hardness"),
    ("d.o.", "DO"), ("cod", "COD"), ("calcium", "Calcium"), ("magnesium", "Magnesium"),
    ("ammoniacal nitrogen", "AmmoniacalNitrogen"), ("free ammonia", "FreeAmmonia"), ("phosphates", "Phosphates"),
    ("hexa chromium", "HexaChromium"), ("oil & grease", "OilGrease"), ("iron", "Iron"), ("sulphides", "Sulphides"),
    ("sulphates", "Sulphates"), ("nitrate", "Nitrate"), ("total alkalinity", "TotalAlkalinity"), ("bod", "BOD"),
    ("tc", "TC"), ("fc", "FC"), ("fs", "FS"), ("sodium", "Sodium"), ("potassium", "Potassium"), ("sar", "SAR")])
UNIT_NORMAL = {"ºc": "degC", "°c": "degC", "µs/cm": "uS/cm", "mg/l": "mg/L", "ntu": "NTU", "hazen": "Hazen",
               "cfu/100ml": "cfu/100mL", "ppm": "ppm", "meq/l": "meq/L", "": ""}
MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                       "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], 1)}
NUM = re.compile(r"^-?\d+(\.\d+)?$")


def norm(s):
    return re.sub(r"\s+", " ", s.strip())


def parse_date(h):
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})", h.strip())
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = 2000 + y if y < 100 else y
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def report_period(rows):
    for r in rows:
        for c in r:
            m = re.search(r"([A-Z]+)\s*[- ]\s*([A-Z]+)\s+(\d{4})", c.upper())
            if m and m.group(1) in MONTHS and m.group(2) in MONTHS:
                y = int(m.group(3)); a, b = MONTHS[m.group(1)], MONTHS[m.group(2)]
                end = (datetime.date(y + (b == 12), b % 12 + 1, 1) - datetime.timedelta(days=1))
                return datetime.date(y, a, 1), end, c.strip()
    return None, None, None


def classify(raw):
    v = raw.strip()
    if NUM.match(v):
        return "number"
    if v == "#":
        return "not_measured_hash"
    if v == "*":
        return "asterisk_code"
    if v.upper() == "BDL":
        return "below_detection_limit"
    if v.startswith("#DIV"):
        return "spreadsheet_error"
    if v == '"':
        return "ditto_mark_in_value_cell"
    if re.fullmatch(r"[A-Za-z]", v):
        return "annotation_letter"
    return "unparsed_text"


def implausible(col, x):
    if x < 0:
        return "negative_value"
    if col == "Temperature" and not (0 < x <= 50):
        return "temperature_outside_0_50"
    if col == "pH" and not (0 <= x <= 14):
        return "pH_outside_0_14"
    if col in ("Conductivity", "TDS") and x <= 0:
        return "zero_conductivity_or_TDS"
    return None


def suspicious(col, x):
    # kept unchanged (original value preserved) but flagged: not physically impossible to record, yet implausible
    if col == "DO" and x == 0:
        return "zero_DO_suspicious"
    if col == "DO" and x > 20:
        return "DO_above_20_mgL_implausible_possible_row_misalignment"
    if col == "Temperature" and x < 20:
        return "temperature_below_20_implausible_for_this_river"
    if col == "Conductivity" and x > 60000:
        return "conductivity_above_seawater_level"
    return None


def convert(in_dir, out_dir):
    files = sorted(glob.glob(os.path.join(in_dir, "consdata-*.csv")))
    if not files:
        sys.exit(f"no consdata-*.csv files in {in_dir}")
    os.makedirs(out_dir, exist_ok=True)
    log = []                                       # (file,row,col,station,dateHeader,parameter,raw,reason,action)
    values = defaultdict(dict)                     # (station, iso) -> {column: (raw string, file, row, col)}
    seen_keys = set()
    units = defaultdict(set); labels = defaultdict(set)
    sources = []
    stats = dict(records_read=0, records_bad_date=0, records_duplicate=0, cells_value=0, cells_dedup=0, cells_conflict=0)
    conflicts = set()
    for p in files:
        fn = os.path.basename(p)
        raw = open(p, "rb").read()
        rows = list(csv.reader(open(p, encoding="utf-8-sig", newline="")))
        station = None
        for r in rows:
            for c in r:
                if c.strip().lower().startswith("sampling point"):
                    station = norm(c.split(":", 1)[1])
        if not station:
            sys.exit(f"{fn}: no 'Sampling point' line")
        if "," in station:
            sys.exit(f"{fn}: station name contains a comma: {station}")
        p0, p1, title = report_period(rows)
        heads = [i for i, r in enumerate(rows) if len(r) > 1 and r[0].strip().lower().startswith("sl")
                 and r[1].strip().lower() == "parameter"]
        if not heads:
            sys.exit(f"{fn}: no 'Sl. No, Parameter' header row")
        src = dict(file=fn, md5=hashlib.md5(raw).hexdigest(), station=station, reportPeriod=f"{p0}..{p1}",
                   tables=len(heads), headerRows=" ".join(str(h + 1) for h in heads), records_read=0,
                   records_bad_date=0, records_duplicate=0)
        for t, h in enumerate(heads):
            end = heads[t + 1] if t + 1 < len(heads) else len(rows)
            hdr = rows[h]
            width = max(len(r) for r in rows[h:end])
            colinfo = {}
            for j in range(3, width):
                hv = hdr[j].strip() if j < len(hdr) else ""
                has_vals = any(j < len(r) and r[j].strip() for r in rows[h + 1:end])
                if not hv and not has_vals:
                    continue
                d = parse_date(hv) if hv else None
                if not hv:
                    why = "values_under_empty_date_header"
                elif d is None:
                    why = "unparseable_date_header"
                elif p0 and not (p0 <= d <= p1):
                    why = "date_outside_report_period"
                else:
                    why = None
                colinfo[j] = (hv, d, why)
                src["records_read"] += 1
                if why:
                    src["records_bad_date"] += 1
                else:
                    key = (station, d.isoformat())
                    if key in seen_keys:
                        src["records_duplicate"] += 1
                    seen_keys.add(key)
            prev_unit = ""
            for i in range(h + 1, end):
                r = rows[i]
                serial = r[0].strip() if r else ""
                label = norm(r[1]) if len(r) > 1 else ""
                cells = [(j, r[j]) for j in range(len(r)) if r[j].strip()]
                if not cells:
                    continue
                pkey = label.lower().rstrip(" ")
                if serial.isdigit() and pkey in PARAM_COLUMNS:
                    col = PARAM_COLUMNS[pkey]
                    u = r[2].strip() if len(r) > 2 else ""
                    u = prev_unit if u == '"' else u
                    prev_unit = u
                    units[col].add(UNIT_NORMAL.get(u.lower(), "UNRECOGNISED:" + u)); labels[col].add(label)
                    for j, c in cells:
                        if j < 3:
                            continue
                        hv, d, why = colinfo.get(j, ("", None, "values_under_empty_date_header"))
                        if why:
                            log.append((fn, i + 1, j + 1, station, hv, col, c.strip(), why, "rejected")); continue
                        kind = classify(c)
                        if kind != "number":
                            log.append((fn, i + 1, j + 1, station, hv, col, c.strip(), kind, "rejected")); continue
                        bad = implausible(col, float(c))
                        if bad:
                            log.append((fn, i + 1, j + 1, station, hv, col, c.strip(), bad, "rejected")); continue
                        flag = suspicious(col, float(c))
                        if flag:
                            log.append((fn, i + 1, j + 1, station, hv, col, c.strip(), flag, "kept_flagged"))
                        key = (station, d.isoformat())
                        if col in values[key]:
                            old = values[key][col]
                            if float(old[0]) == float(c):
                                stats["cells_dedup"] += 1
                                log.append((fn, i + 1, j + 1, station, hv, col, c.strip(), "duplicate_identical_value", "deduplicated"))
                            else:
                                conflicts.add((key, col))
                                log.append((fn, i + 1, j + 1, station, hv, col, c.strip(),
                                            f"conflicts_with_{old[1]}_row{old[2]}_col{old[3]}={old[0]}", "rejected_conflict"))
                            continue
                        values[key][col] = (c.strip(), fn, i + 1, j + 1)
                else:
                    reason = "note_text" if (not serial and len(cells) == 1 and cells[0][0] <= 2 and len(cells[0][1]) > 3) \
                        else ("unrecognised_parameter_label" if serial.isdigit() else "unlabelled_row")
                    for j, c in cells:
                        hv = colinfo.get(j, ("",))[0] if j >= 3 else ""
                        log.append((fn, i + 1, j + 1, station, hv, label, c.strip(), reason, "rejected"))
        for k in ("records_read", "records_bad_date", "records_duplicate"):
            stats[k] += src[k]
        sources.append(src)
    # conflicting parameters: drop the first-seen value too (it is not established which one is right)
    for key, col in sorted(conflicts):
        old = values[key].pop(col)
        log.append((old[1], old[2], old[3], key[0], "", col, old[0], "conflicting_duplicate_value", "rejected_conflict"))
    stats["cells_conflict"] = sum(1 for e in log if e[8] == "rejected_conflict")
    cols = [c for c in PARAM_COLUMNS.values()]
    keys = sorted(values)
    retained = [k for k in keys if values[k]]
    valid_date_records = stats["records_read"] - stats["records_bad_date"]
    unique_dates = len({k for k in seen_keys})
    empty = unique_dates - len(retained)
    with open(os.path.join(out_dir, "kspcb_long.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Location", "Date"] + cols)
        for k in retained:
            w.writerow([k[0], k[1]] + [values[k][c][0] if c in values[k] else "" for c in cols])
    with open(os.path.join(out_dir, "kspcb_fields.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["column", "rawLabels", "unit", "retainedValues", "min", "max", "note"])
        for c in cols:
            v = [float(values[k][c][0]) for k in retained if c in values[k]]
            u = sorted(units[c])
            note = "unit inconsistent across files" if len(u) > 1 else ""
            if c == "pH":
                note = "unitless"
            if c == "SAR":
                note = "source states meq/L; SAR is normally a dimensionless ratio - not established"
            w.writerow([c, "|".join(sorted(labels[c])), "|".join(u), len(v), min(v) if v else "", max(v) if v else "", note])
    with open(os.path.join(out_dir, "kspcb_cell_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["file", "row", "col", "station", "dateHeader", "parameter", "raw", "reason", "action"])
        w.writerows(log)
    for src in sources:
        src["cells_written"] = sum(1 for k in retained for v in values[k].values() if v[1] == src["file"])
        src["cells_logged_not_written"] = sum(1 for e in log if e[0] == src["file"] and e[8] != "kept_flagged")
    with open(os.path.join(out_dir, "kspcb_sources.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sources[0].keys()), lineterminator="\n")
        w.writeheader(); w.writerows(sources)
    stats.update(unique_station_dates=unique_dates, rows_retained=len(retained), station_dates_without_values=empty,
                 cells_value=sum(len(values[k]) for k in retained), cells_logged=len(log))
    return stats, sources


if __name__ == "__main__":
    s, src = convert(sys.argv[1], sys.argv[2])
    for x in src:
        print(f"{x['file']}: station '{x['station']}', period {x['reportPeriod']}, tables {x['tables']}, "
              f"date columns {x['records_read']}, rejected columns {x['records_bad_date']}, duplicate dates {x['records_duplicate']}")
    print("records (station-date columns) read:", s["records_read"], "| rejected (bad/out-of-period/missing date):",
          s["records_bad_date"], "| duplicates merged:", s["records_duplicate"], "| unique station-dates:",
          s["unique_station_dates"], "| retained rows:", s["rows_retained"], "| station-dates with no usable value:",
          s["station_dates_without_values"])
    print("cells written:", s["cells_value"], "| cells logged:", s["cells_logged"], "(deduplicated", s["cells_dedup"],
          ", conflict", s["cells_conflict"], ")")
