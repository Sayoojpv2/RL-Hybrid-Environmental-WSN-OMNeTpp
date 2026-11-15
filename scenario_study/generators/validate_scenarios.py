"""Validate the scenario datasets in data/scenarios and write scenario_study/validation/<dataset>_validation.txt.

Usage:  python -P scenario_study/generators/validate_scenarios.py [--regen-dir DIR] [--nodes N]
--regen-dir: regenerate everything into DIR and require identical MD5s (reproducibility check).
Exit code 1 if any check fails.
"""
import argparse, csv, collections, hashlib, json, math, os, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'scenarios')
OUT = os.path.join(ROOT, 'scenario_study', 'validation')
P = json.load(open(os.path.join(ROOT, 'scenario_study', 'dataset_metadata', 'sensor_profiles.json')))
WORKLOAD = os.path.join(ROOT, 'results_200node_optimization', 'final', 'baseline', 'V2_200Node_Final-seed47-workload.csv')
N, R = 200, 500                          # N: --nodes (200 = the validated datasets)
KEYS = {}


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def num(s):
    return None if s == '' else float(s)


class Report:
    def __init__(self, name):
        self.name, self.lines, self.fail = name, [], 0

    def check(self, ok, text):
        self.lines.append(('PASS ' if ok else 'FAIL ') + text)
        self.fail += 0 if ok else 1

    def info(self, text):
        self.lines.append('     ' + text)

    def write(self):
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, self.name + '_validation.txt'), 'w') as f:
            f.write(f'{self.name}: {"ALL CHECKS PASSED" if not self.fail else str(self.fail) + " CHECK(S) FAILED"}\n')
            f.write('\n'.join(self.lines) + '\n')


def validate(ds, mask):
    key = KEYS[ds]
    prof = P['profiles'][key]
    meta = json.load(open(os.path.join(DATA, ds, 'metadata.json')))
    path = os.path.join(DATA, ds, 'observations.csv')
    rows = list(csv.DictReader(open(path, newline='')))
    rep = Report(ds)
    names = list(meta['fields'])
    flds = {f['name']: f for f in prof['fields'] + prof.get('extension_fields', [])}
    rep.check(md5(path) == meta['observations_md5'], f"observations.csv MD5 matches metadata ({meta['observations_md5']})")
    rep.check(len(rows) == N * R, f'{len(rows)} rows = {N} nodes x {R} rounds')
    nodes = sorted({int(w['node_id']) for w in rows})
    rep.check(nodes == list(range(1, N + 1)), f'node ids 1..{N} ({len(nodes)} nodes)')
    rnds = sorted({int(w['round']) for w in rows})
    rep.check(rnds == list(range(1, R + 1)), f'rounds 1..{R}')
    ids = [w['sample_id'] for w in rows]
    rep.check(len(set(ids)) == len(ids), 'sample_id unique')
    keys = {(w['node_id'], w['round']) for w in rows}
    rep.check(len(keys) == len(rows), 'no duplicate (node, round) records')
    hdr = list(rows[0].keys())
    rep.check(all(n in hdr for n in names) and all(n in flds for n in names), f'field columns present with units: ' +
              ', '.join(f"{n} [{meta['fields'][n]['unit']}]" for n in names))
    rep.check(all(w['sensor_type'] == key and w['scenario_id'] == prof['scenario'] for w in rows), 'sensor_type / scenario_id labels')
    # ranges, encoding, missing values
    for n in names:
        f = flds[n]
        v = [num(w[n]) for w in rows]
        pres = [x for x in v if x is not None]
        miss = len(v) - len(pres)
        out_rng = sum(1 for x in pres if not (f['min'] <= x <= f['max']))
        if key == 'water_quality' and n != 'DO_mgL':          # MATLAB rule: strictly positive EC and TDS
            out_rng += sum(1 for x in pres if n in ('conductivity_uScm', 'TDS_mgL') and x <= 0)
        enc = sum(1 for x in pres if not (-32768 <= round(x / f['scale']) <= 65534))
        lo, hi = (min(pres), max(pres)) if pres else (float('nan'), float('nan'))
        rep.check(out_rng == 0 and enc == 0, f'{n}: {len(pres)} present, {miss} missing, range {lo:.4g}..{hi:.4g} within '
                  f"[{f['min']}, {f['max']}], all encodable at scale {f['scale']}")
        flagged = sum(1 for w in rows if w[n] == '' and w['quality_flag'] != 'ok')
        rep.check(flagged == miss, f'{n}: every missing value is an empty cell explained by quality_flag ({flagged}/{miss})')
    zeros = {n: sum(1 for w in rows if w[n] != '' and float(w[n]) == 0.0) for n in names}
    rep.info('exact zero values per field (missing values are never written as 0): ' + json.dumps(zeros))
    # physical constraints
    if key == 'air_quality':
        bad = [w for w in rows if w['PM25_ugm3'] and w['PM10_ugm3'] and float(w['PM10_ugm3']) < float(w['PM25_ugm3'])]
        rep.check(all('pm10_lt_pm25_in_source' in w['quality_flag'] for w in bad),
                  f'PM10 < PM2.5 in {len(bad)} rows ({len(bad) / len(rows):.2%}); all flagged pm10_lt_pm25_in_source, values unaltered')
    for n in names:
        if n.endswith(('mgL', 'ugm3', 'mgm3', 'NTU', 'mgkg', 'dSm', 'uScm')):
            rep.check(all(w[n] == '' or float(w[n]) >= 0 for w in rows), f'{n} non-negative')
    # temporal consistency and node mapping
    by = collections.defaultdict(list)
    for w in rows:
        by[int(w['node_id'])].append(w)
    mono = all([int(x['round']) for x in by[k]] == list(range(1, R + 1)) for k in by)
    rep.check(mono, 'rows of every node ordered by round with no gaps')
    rep.check(all(int(w['sim_time_s']) == (int(w['round']) - 1) * 100 for w in rows), 'sim_time_s = (round - 1) x 100 s')
    if key in ('industrial_effluent', 'soil_monitoring'):
        rep.check(all(w['env_time'] == f"T+{int(w['round']) - 1:04d}h" for w in rows), 'env_time step 1 h (T+0000h .. T+0499h)')
    if key == 'air_quality':
        import datetime as dt
        ok = all(dt.datetime.strptime(w['env_time'], '%Y-%m-%d %H:%M') == dt.datetime(2016, 12, 1) + dt.timedelta(hours=int(w['round']) - 1)
                 for w in rows)
        rep.check(ok, 'env_time = 2016-12-01 00:00 + (round - 1) h, hourly, no gaps')
    if key == 'water_quality':
        ok = all(all(a['env_time'] <= b['env_time'] for a, b in zip(by[k], by[k][1:]) if a['env_time'] and b['env_time']) for k in by)
        rep.check(ok, 'sampling dates non-decreasing per node (causal sample-and-hold)')
    nst = {'water_quality': 10, 'air_quality': 12, 'industrial_effluent': 20, 'soil_monitoring': 10}[key]
    rep.check(all(int(w['source_station_id']) == (int(w['node_id']) - 1) % nst + 1 for w in rows),
              f'node k -> source stream ((k - 1) mod {nst}) + 1')
    if key in ('water_quality', 'air_quality'):
        same = all(all(by[k][i][n] == by[(k - 1) % nst + 1][i][n] for n in names + ['env_time'] for i in range(R)) for k in range(nst + 1, N + 1))
        rep.check(same, f'replay nodes {nst + 1}-{N} carry exactly the values of their station node in the same round')
        rep.check(all(w['is_real'] == '1' and w['is_synthetic'] == '0' and w['is_replayed'] == str(int(int(w['node_id']) > nst)) for w in rows),
                  f'labels: is_real=1, is_synthetic=0, is_replayed=1 only for nodes > {nst}')
    else:
        rep.check(all(w['is_real'] == '0' and w['is_replayed'] == '0' and w['is_synthetic'] == '1' and w['data_source'] == 'SYNTHETIC'
                      for w in rows), 'labels: every row is_synthetic=1, is_real=0, data_source=SYNTHETIC')
    if key == 'water_quality':
        wl = {(r['sourceNode'], r['round']): r for r in csv.DictReader(open(WORKLOAD, newline=''))}
        m = {'temperature': 'temperature_C', 'pH': 'pH', 'conductivity': 'conductivity_uScm', 'TDS': 'TDS_mgL'}
        ident = sum(1 for w in rows if (w['node_id'], w['round']) in wl and all(wl[(w['node_id'], w['round'])][a] == w[b] for a, b in m.items())
                    and wl[(w['node_id'], w['round'])]['date'] == w['env_time'])
        rep.check(ident == len(wl) == 96500, f'{ident} of {len(wl)} workload reports identical to the validated 200-node OMNeT++ workload (values + date)')
        nob = sum(1 for w in rows if w['quality_flag'].startswith('no_observation_yet'))
        exp = sum(1 for w in rows if ((w['node_id'] if int(w['node_id']) <= 200 else str((int(w['node_id']) - 1) % 10 + 1)), w['round']) not in wl)
        rep.check(nob == exp and (N != 200 or exp == N * R - 96500),
                  f'{nob} slots before a station\'s first valid observation flagged no_observation_yet')
        st = meta['stats']
        rep.info(f"DO extension: {st['do_valid']} valid, {st['do_invalid']} invalid (> {flds['DO_mgL']['max']} mg/L or <= 0), "
                 f"{st['do_missing']} missing in the KSPCB loader table (rows with data)")
    # alarm flag recomputation
    def alarm(w):
        for a in prof['alarms']:
            v = num(w.get(a['field'], ''))
            if v is None:
                continue
            if (a['op'] == 'outside' and (v < a['lo'] or v > a['hi'])) or (a['op'] == '>' and v > a['value']) or (a['op'] == '<' and v < a['value']):
                return 1
        return 0
    rep.check(all(int(w['alarm_flag']) == alarm(w) for w in rows), 'alarm_flag recomputed from the profile thresholds')
    # modes
    m1 = {(int(w['node_id']), int(w['round'])) for w in rows if w['m1_report'] == '1'}
    rep.check(m1 == mask, f'Mode 1 mask = the 96,500 report slots of the validated 200-node workload ({len(m1)})')
    pay = [w for w in rows if w['m2_report'] == '1']
    hdr_b, fb, ovh = P['frame']['app_header_bytes'], P['frame']['field_bytes'], P['frame']['mac_phy_overhead_bytes']
    rep.check(all(int(w['m2_payload_bytes']) == hdr_b + fb * int(w['m2_fields']) and int(w['m2_frame_bits']) == 8 * (ovh + int(w['m2_payload_bytes']))
                  for w in pay), 'Mode 2 payload = 10 B + 2 B/field, frame bits = 8 x (17 B + payload)')
    payload_names = meta['payload_fields_mode2']
    rep.check(all(int(w['m2_fields']) == sum(1 for n in payload_names if w[n] != '') for w in pay), 'Mode 2 field count = present payload fields')
    rep.check(all(w['m2_report'] == '0' for w in rows if all(w[n] == '' for n in payload_names)), 'Mode 2 sends nothing when no field is present')
    RI, RA, RC = prof['report_interval_rounds'], prof['alarm_interval_rounds'], prof.get('chem_interval_rounds')
    chem = {f['name'] for f in prof['fields'] if f.get('chem')}
    def sched(w):
        r = int(w['round']); cr = RC is not None and (r - 1) % RC == 0
        pres = [n for n in payload_names if w[n] != '' and (n not in chem or cr)]
        return int(bool(pres) and ((r - 1) % RI == 0 or (w['alarm_flag'] == '1' and (r - 1) % RA == 0)))
    rep.check(all(int(w['m2_report']) == sched(w) for w in rows), f'Mode 2 schedule recomputed: periodic every {RI} round(s), '
              f'alarm reports every {RA} round(s)' + (f', chemistry fields only on rounds 1 + {RC}k' if RC else ''))
    def sense(cr):
        e = 0.0
        for f in prof['fields'] + prof.get('extension_fields', []):
            en = f['energy']; one = en['V'] * en['mA'] * en['ms'] / 1000.0     # V x mA x ms = uJ; / 1000 = mJ
            e += (one if cr else 0.0) if f.get('chem') else (one * P['round_hours'] if en['ms'] >= 3600000 else one * prof['samples_per_round'])
        pr = P['processing']
        return e + pr['mcu_active_V'] * pr['mcu_active_mA'] * pr['mcu_ms_per_sample'] / 1000.0 * prof['samples_per_round']
    rep.check(all(abs(float(w['m2_sensing_mJ']) - sense(RC is not None and (int(w['round']) - 1) % RC == 0)) < 1e-3 for w in rows),
              'm2_sensing_mJ recomputed from sensor_profiles.json (V x mA x ms per sample x samples, continuous loads x 1 h, '
              'chemistry only on chemistry rounds, MCU per sample)')
    trig = collections.Counter(w['m2_trigger'] for w in rows)
    bits = sum(int(w['m2_frame_bits']) for w in pay)
    rep.info(f'Mode 1: {len(m1)} reports x 4000 bits = {len(m1) * 4000 / 8e6:.1f} MB offered')
    rep.info(f'Mode 2: {len(pay)} reports ({len(pay) / N:.1f} per node), {sum(int(w["m2_priority"]) for w in pay)} priority (alarm), '
             f'{bits / 8e6:.3f} MB offered, mean frame {bits / max(1, len(pay)):.0f} bits; triggers {dict(trig)}')
    e = [float(w['m2_sensing_mJ']) for w in rows]
    rep.info(f'Mode 2 sensing+processing energy per node: {sum(e) / N / 1000:.3f} J over {R} rounds '
             f'({min(e):.3f}..{max(e):.3f} mJ per round)')
    rep.info('alarm rows: %d (%.1f%%); anomaly rows: %d; event types: %s' % (
        sum(int(w['alarm_flag']) for w in rows), 100 * sum(int(w['alarm_flag']) for w in rows) / len(rows),
        sum(int(w['anomaly_flag']) for w in rows), dict(collections.Counter(w['event_type'] for w in rows))))
    q = collections.Counter(f for w in rows for f in w['quality_flag'].split(';'))
    rep.info('quality flags: ' + json.dumps(dict(q)))
    rep.write()
    return rep, {k: by[k] for k in by}


def validate_mixed(src_rows):
    mxd = f'mixed_environment_{N}'
    rep = Report(mxd)
    meta = json.load(open(os.path.join(DATA, mxd, 'metadata.json')))
    nm = list(csv.DictReader(open(os.path.join(DATA, mxd, 'node_map.csv'), newline='')))
    rep.check(md5(os.path.join(DATA, mxd, 'node_map.csv')) == meta['node_map_md5'], 'node_map.csv MD5 matches metadata')
    rep.check([int(x['node_id']) for x in nm] == list(range(1, N + 1)), f'every node 1..{N} mapped exactly once')
    cnt = collections.Counter(x['sensor_type'] for x in nm)
    rep.check(dict(cnt) == meta['distribution'] and len(set(cnt.values())) == 1, f'distribution {dict(cnt)} (equal split)')
    rep.check(all(x['sensor_type'] == 'water_quality' for x in nm[:10]), 'nodes 1-10 (real KSPCB stations) are water_quality')
    for ds, key in KEYS.items():
        rep.check(md5(os.path.join(DATA, ds, 'observations.csv')) == meta['source_md5'][ds], f'{ds} MD5 equals the one the manifest was built with')
    ok = all(len(src_rows[x['sensor_type']][int(x['source_node_id'])]) == R and
             all(w['sensor_type'] == x['sensor_type'] for w in src_rows[x['sensor_type']][int(x['source_node_id'])]) for x in nm)
    rep.check(ok and all(x['source_node_id'] == x['node_id'] for x in nm), 'each node resolves to 500 rows of its own profile, same node id')
    for c in sorted(cnt):
        rows = [w for x in nm if x['sensor_type'] == c for w in src_rows[c][int(x['node_id'])]]
        pay = [w for w in rows if w['m2_report'] == '1']
        rep.info(f"{c}: {cnt[c]} nodes, Mode 1 reports {sum(w['m1_report'] == '1' for w in rows)}, Mode 2 reports {len(pay)}, "
                 f"Mode 2 bits {sum(int(w['m2_frame_bits']) for w in pay)}, sensing {sum(float(w['m2_sensing_mJ']) for w in rows) / 1000 / cnt[c]:.2f} J/node")
    rep.write()
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--regen-dir')
    ap.add_argument('--nodes', type=int, default=200)
    a = ap.parse_args()
    global N
    N = a.nodes
    KEYS.update({f'{k}_{N}': k for k in ('water_quality', 'air_quality', 'industrial_effluent', 'soil_monitoring')})
    mask = {(int(r['sourceNode']), int(r['round'])) for r in csv.DictReader(open(WORKLOAD, newline=''))}
    reps, src = [], {}
    for ds, key in KEYS.items():
        r, by = validate(ds, mask)
        reps.append(r)
        src[key] = by
    reps.append(validate_mixed(src))
    if a.regen_dir:
        subprocess.run([sys.executable, '-P', os.path.join(ROOT, 'scenario_study', 'generators', 'generate_scenarios.py'),
                        '--out', a.regen_dir, '--matrix', os.path.join(a.regen_dir, 'matrix.csv'), '--nodes', str(N)], check=True, capture_output=True)
        for r in reps:
            sub = 'node_map.csv' if r.name.startswith('mixed') else 'observations.csv'
            same = md5(os.path.join(DATA, r.name, sub)) == md5(os.path.join(a.regen_dir, r.name, sub))
            r.check(same, f'reproducible: regenerated {sub} is byte-identical (MD5)')
            r.write()
        m_same = md5(os.path.join(ROOT, 'scenario_study', 'SENSOR_PARAMETER_MATRIX.csv')) == md5(os.path.join(a.regen_dir, 'matrix.csv'))
        print('SENSOR_PARAMETER_MATRIX.csv reproducible:', m_same)
    for r in reps:
        print(f'{r.name:26s} {"PASS" if not r.fail else "FAIL x" + str(r.fail)}  ({len(r.lines)} lines)')
    sys.exit(1 if any(r.fail for r in reps) else 0)


if __name__ == '__main__':
    main()
