#!/usr/bin/env python3
"""Check tools/convert_kspcb.py output against the raw KSPCB files (independent re-scan).

Usage: python3 tools/verify_kspcb.py <raw input dir> <converted dir>
  K1 raw files unchanged (MD5 recorded at conversion == MD5 now)
  K2 cell closure per file: every non-empty raw cell after the first table header (excluding header rows and the
     serial/label/unit cells of parameter rows) is either written to kspcb_long.csv or logged as not written
  K3 every value in kspcb_long.csv is found, as the identical string, in that station's raw file under the same
     parameter label and a date header that parses to the same date
  K4 record accounting: read = rejected date columns + duplicate dates + unique station-dates;
     unique station-dates = retained rows + station-dates without any usable value
  K5 loader compatibility: single header row, no quotes, no comma in station names, ISO dates, numeric cells only
"""
import csv, datetime, glob, hashlib, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
raw_dir, out_dir = sys.argv[1], sys.argv[2]
fails, lines = [], []


def check(ok, msg):
    lines.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


src = list(csv.DictReader(open(os.path.join(out_dir, "kspcb_sources.csv"), encoding="utf-8")))
log = list(csv.DictReader(open(os.path.join(out_dir, "kspcb_cell_log.csv"), encoding="utf-8")))
out = list(csv.DictReader(open(os.path.join(out_dir, "kspcb_long.csv"), encoding="utf-8")))
LABEL = {"Temperature": "temperature", "pH": "ph", "Conductivity": "conductivity", "TDS": "tds", "Turbidity": "turbidity",
         "Colour": "colour", "SS": "ss", "Chlorides": "chlorides", "Hardness": "hardness", "DO": "d.o.", "COD": "cod",
         "Calcium": "calcium", "Magnesium": "magnesium", "AmmoniacalNitrogen": "ammoniacal nitrogen",
         "FreeAmmonia": "free ammonia", "Phosphates": "phosphates", "HexaChromium": "hexa chromium",
         "OilGrease": "oil & grease", "Iron": "iron", "Sulphides": "sulphides", "Sulphates": "sulphates", "Nitrate": "nitrate",
         "TotalAlkalinity": "total alkalinity", "BOD": "bod", "TC": "tc", "FC": "fc", "FS": "fs", "Sodium": "sodium",
         "Potassium": "potassium", "SAR": "sar"}


def pdate(h):
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})", h.strip())
    if not m:
        return None
    y = int(m.group(3)); y = 2000 + y if y < 100 else y
    try:
        return datetime.date(y, int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


raw_index = {}          # (station, iso date, label) -> set of raw strings
cols_read = cols_bad = 0
valid_keys = []         # one entry per valid date column (duplicates included)
for s in src:
    p = os.path.join(raw_dir, s["file"])
    check(hashlib.md5(open(p, "rb").read()).hexdigest() == s["md5"], f"K1 {s['file']}: raw file unchanged (MD5 {s['md5'][:8]}…)")
    rows = list(csv.reader(open(p, encoding="utf-8-sig", newline="")))
    heads = [i for i, r in enumerate(rows) if len(r) > 1 and r[0].strip().lower().startswith("sl") and r[1].strip().lower() == "parameter"]
    census = 0
    hdr = None
    for i in range(heads[0], len(rows)):
        r = rows[i]
        if i in heads:
            hdr = r
            end = next((h for h in heads if h > i), len(rows))
            width = max(len(x) for x in rows[i:end])
            for j in range(3, width):
                hv = hdr[j].strip() if j < len(hdr) else ""
                if not hv and not any(j < len(x) and x[j].strip() for x in rows[i + 1:end]):
                    continue
                cols_read += 1
                d = pdate(hv) if hv else None
                if d and "2025-01-01" <= d <= "2025-07-31":
                    valid_keys.append((s["station"], d))
                else:
                    cols_bad += 1
            continue
        labelled = r and r[0].strip().isdigit() and len(r) > 1 and r[1].strip()
        census += sum(1 for j, c in enumerate(r) if c.strip() and not (labelled and j < 3))
        if labelled:
            lab = re.sub(r"\s+", " ", r[1].strip()).lower()
            for j in range(3, len(r)):
                if r[j].strip() and j < len(hdr):
                    d = pdate(hdr[j])
                    if d:
                        raw_index.setdefault((s["station"], d, lab), set()).add(r[j].strip())
    written, logged = int(s["cells_written"]), int(s["cells_logged_not_written"])
    check(census == written + logged, f"K2 {s['file']}: {census} non-empty data cells = {written} written + {logged} logged")

missing = []
nvals = 0
for r in out:
    for col, lab in LABEL.items():
        v = r[col]
        if v:
            nvals += 1
            if v not in raw_index.get((r["Location"], r["Date"], lab), set()):
                missing.append((r["Location"], r["Date"], col, v))
check(not missing, f"K3 all {nvals} written values found verbatim in the raw files at the same station/date/parameter "
                   f"({len(missing)} not found{': ' + str(missing[:3]) if missing else ''})")

read = sum(int(s["records_read"]) for s in src); bad = sum(int(s["records_bad_date"]) for s in src)
dup = sum(int(s["records_duplicate"]) for s in src)
uniq = len(set(valid_keys))
out_keys = {(r["Location"], r["Date"]) for r in out}
check(read == cols_read and bad == cols_bad and dup == len(valid_keys) - uniq and out_keys <= set(valid_keys),
      f"K4 date columns read {read} = {bad} rejected + {dup} duplicate dates + {uniq} unique station-dates "
      f"(re-scan: {cols_read}/{cols_bad}/{len(valid_keys) - uniq}/{uniq}); {len(out)} retained rows, {uniq - len(out)} station-dates "
      f"without any usable value")

text = open(os.path.join(out_dir, "kspcb_long.csv"), encoding="utf-8").read()
iso = all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["Date"]) for r in out)
nums = all(re.fullmatch(r"-?\d+(\.\d+)?", r[c]) for r in out for c in LABEL if r[c])
check('"' not in text and iso and nums and all("," not in r["Location"] for r in out),
      f"K5 loader format: {len(out)} rows, {len({r['Location'] for r in out})} stations, ISO dates, unquoted numeric cells")
print("\n".join(lines))
print(f"\n{len(lines)} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
