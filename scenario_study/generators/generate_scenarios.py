"""Generate the five scenario-study datasets (200 nodes x 500 rounds) from sensor_profiles.json.

  water_quality_200        real KSPCB station streams (nodes 1-10) + deterministic replay (nodes 11-200),
                           taken unchanged from the validated 200-node OMNeT++ workload export
  air_quality_200          real UCI Beijing hourly measurements, 12 station streams replayed onto 200 nodes
  industrial_effluent_200  deterministic SYNTHETIC outfall time series (seed 2101)
  soil_monitoring_200      deterministic SYNTHETIC soil water-balance / chemistry series (seed 2102)
  mixed_environment_200    node -> profile manifest that selects rows of the four datasets (no duplicated rows)

Usage:  python -P scenario_study/generators/generate_scenarios.py [--out DIR] [--nodes N]
--nodes N (default 200) writes <dataset>_N; nodes 1..200 are identical for every N (same per-node streams); water
replay nodes > 200 copy their station node exactly as nodes 11..200 do; the mixed allocation scales the 50/50/50/50 split.
Run from the project root. Nothing outside the output directory (default data/scenarios) and
scenario_study/SENSOR_PARAMETER_MATRIX.csv is written; all inputs are read-only.
"""
import argparse, csv, hashlib, io, json, math, os, sys, zipfile
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PROFILES = os.path.join(ROOT, 'scenario_study', 'dataset_metadata', 'sensor_profiles.json')
WORKLOAD = os.path.join(ROOT, 'results_200node_optimization', 'final', 'baseline', 'V2_200Node_Final-seed47-workload.csv')
KSPCB = os.path.join(ROOT, 'data', 'v2_consdata_loaded.csv')
UCI_ZIP = os.path.join(ROOT, 'data', 'scenarios', '_sources', 'uci_beijing_air', 'PRSA2017_Data_20130301-20170228.zip')
N_NODES, N_ROUNDS, ROUND_PERIOD_S = 200, 500, 100          # V2_200Node: 200 nodes, rounds 1-500, roundPeriod 100 s
V2_STATIONS = ['ALUVA - MANAPPURAM', 'PURAPILLIKADAVU US', 'PURAPILLIKADAVU BUND NAVIGATION', 'PURAPILLIKADAVU BUND DS',
               'PATHALAM BUND U/S', 'PATHALAM BUND D/S', 'PATHALAM BRIDGE', 'PUTHALAM KADAVU', 'MANJUMMAL BUND', 'VETTUKADAVU']
AIR_START = (2016, 12, 1, 0)                               # 500 consecutive hours from 2016-12-01 00:00 (Beijing local time)
COMMON = ['scenario_id', 'sample_id', 'node_id', 'sensor_type', 'round', 'sim_time_s', 'env_time', 'source_station_id',
          'source_station', 'data_source', 'is_real', 'is_replayed', 'is_synthetic']
TAIL = ['quality_flag', 'anomaly_flag', 'alarm_flag', 'event_type', 'm1_report', 'm2_report', 'm2_trigger', 'm2_priority',
        'm2_fields', 'm2_payload_bytes', 'm2_frame_bits', 'm2_sensing_mJ']


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def fmt(v, scale):
    """Quantise a synthetic value to the field's encoding resolution; None -> '' (missing is never 0)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ''
    dec = max(0, -int(math.floor(math.log10(scale)))) if scale < 1 else 0
    q = round(v / scale) * scale
    return f'{q:.{dec}f}'


def num(s):
    return None if s in ('', 'NA', 'NaN', 'nan') else float(s)


# ----------------------------------------------------------------------------------------------- Mode 1 / Mode 2
def load_mode1_mask():
    """Mode 1 slots = exactly the report slots of the validated 200-node workload (96,500)."""
    mask = set()
    with open(WORKLOAD, newline='') as f:
        for r in csv.DictReader(f):
            mask.add((int(r['sourceNode']), int(r['round'])))
    return mask


def alarm_check(prof, vals):
    for a in prof['alarms']:
        v = vals.get(a['field'])
        if v is None:
            continue
        if a['op'] == 'outside' and (v < a['lo'] or v > a['hi']):
            return True
        if a['op'] == '>' and v > a['value']:
            return True
        if a['op'] == '<' and v < a['value']:
            return True
    return False


def sensing_mJ(prof, P, chem_round):
    """Sensing + processing energy of one round (mJ). Per-sample components x samples_per_round,
    whole-round components (ms >= 1 h) once, chemistry components only on chemistry rounds."""
    e = 0.0
    for f in prof['fields'] + prof.get('extension_fields', []):
        en = f['energy']
        if en['V'] == 0:
            continue
        one = en['V'] * en['mA'] * en['ms'] / 1000.0            # V * mA * ms = uJ ; /1000 -> mJ
        if f.get('chem'):
            e += one if chem_round else 0.0
        elif en['ms'] >= 3600000:
            e += one * P['round_hours']
        else:
            e += one * prof['samples_per_round']
    pr = P['processing']
    e += pr['mcu_active_V'] * pr['mcu_active_mA'] * pr['mcu_ms_per_sample'] / 1000.0 * prof['samples_per_round']
    return e


def add_modes(rows, prof, P, mask, field_names):
    """Fill m1_* / m2_* columns. rows: dicts of ONE node, sorted by round. Values are strings ('' = missing)."""
    R, RA, RC = prof['report_interval_rounds'], prof['alarm_interval_rounds'], prof.get('chem_interval_rounds')
    chem = {f['name'] for f in prof['fields'] if f.get('chem')}
    hdr, fb, ovh = P['frame']['app_header_bytes'], P['frame']['field_bytes'], P['frame']['mac_phy_overhead_bytes']
    for w in rows:
        r = w['round']
        w['m1_report'] = 1 if (w['node_id'], r) in mask else 0
        chem_round = RC is not None and (r - 1) % RC == 0
        present = [n for n in field_names if w[n] != '' and (n not in chem or chem_round)]
        due = (r - 1) % R == 0
        alarm = w['alarm_flag'] == 1
        if not present:
            send, trig = False, 'no_data'
        elif due and alarm:
            send, trig = True, 'periodic+alarm'
        elif due:
            send, trig = True, 'periodic'
        elif alarm and (r - 1) % RA == 0:
            send, trig = True, 'alarm'
        else:
            send, trig = False, 'none'
        if send and chem_round and any(n in chem for n in present):
            trig += '+chem'
        w['m2_report'] = 1 if send else 0
        w['m2_trigger'] = trig
        w['m2_priority'] = 1 if (send and alarm) else 0
        w['m2_fields'] = len(present) if send else 0
        w['m2_payload_bytes'] = hdr + fb * len(present) if send else 0
        w['m2_frame_bits'] = 8 * (ovh + w['m2_payload_bytes']) if send else 0
        w['m2_sensing_mJ'] = f'{sensing_mJ(prof, P, chem_round):.4f}'


def base_row(sid, code, node, stype, r, env_time, st_id, st_name, src, real, rep, syn):
    return {'scenario_id': sid, 'sample_id': f'{code}-n{node:03d}-r{r:03d}', 'node_id': node, 'sensor_type': stype,
            'round': r, 'sim_time_s': (r - 1) * ROUND_PERIOD_S, 'env_time': env_time, 'source_station_id': st_id,
            'source_station': st_name, 'data_source': src, 'is_real': real, 'is_replayed': rep, 'is_synthetic': syn}


def vals_of(w, names):
    return {n: num(w[n]) for n in names}


# ----------------------------------------------------------------------------------------------- A: water (real)
def gen_water(P, mask):
    prof = P['profiles']['water_quality']
    names = [f['name'] for f in prof['fields']] + ['DO_mgL']
    do_max = prof['extension_fields'][0]['max']
    do = {}
    with open(KSPCB, newline='') as f:
        for r in csv.DictReader(f):
            do[(r['Location'], r['Date'])] = num(r['DO'])
    wl = {}
    with open(WORKLOAD, newline='') as f:
        for r in csv.DictReader(f):
            wl[(int(r['sourceNode']), int(r['round']))] = r
    stats = {'workload_rows': len(wl), 'do_valid': 0, 'do_invalid': 0, 'do_missing': 0}
    out = []
    for node in range(1, N_NODES + 1):
        st = (node - 1) % 10 + 1
        rows = []
        for r in range(1, N_ROUNDS + 1):
            x = wl.get((node if node <= 200 else st, r))   # replay > 200: the station node's row (same rule as 11..200)
            w = base_row('A', 'WQ', node, 'water_quality', r, x['date'] if x else '', st, V2_STATIONS[st - 1],
                         'KSPCB' if node <= 10 else 'KSPCB-replay', 1, int(node > 10), 0)
            q = []
            if x is None:
                for n in names:
                    w[n] = ''
                q.append('no_observation_yet')
            else:
                label = x['station'] if node <= 10 or node > 200 else x['station'].split(':', 1)[1]
                assert label == V2_STATIONS[st - 1], (node, r, x['station'])
                w['temperature_C'], w['pH'], w['conductivity_uScm'], w['TDS_mgL'] = x['temperature'], x['pH'], x['conductivity'], x['TDS']
                d = do.get((V2_STATIONS[st - 1], x['date']))
                if d is None:
                    w['DO_mgL'] = ''; q.append('DO_missing'); stats['do_missing'] += 1
                elif 0 < d <= do_max:
                    w['DO_mgL'] = repr(d); stats['do_valid'] += 1
                else:
                    w['DO_mgL'] = ''; q.append('DO_invalid_value'); stats['do_invalid'] += 1
            w['quality_flag'] = ';'.join(q) if q else 'ok'
            alarm = x is not None and alarm_check(prof, vals_of(w, names))
            w['alarm_flag'] = int(alarm)
            w['anomaly_flag'] = int(alarm)               # real data: no ground truth; anomaly = observed exceedance
            w['event_type'] = 'observed_exceedance' if alarm else 'none'
            rows.append(w)
        add_modes(rows, prof, P, mask, [f['name'] for f in prof['fields']])   # DO is not in the payload (extension)
        out += rows
    return out, names, stats


# ----------------------------------------------------------------------------------------------- C: air (real UCI)
def rh_magnus(t, td):
    if t is None or td is None:
        return None
    return min(100.0, 100.0 * math.exp(17.625 * td / (243.04 + td)) / math.exp(17.625 * t / (243.04 + t)))


def gen_air(P, mask):
    prof = P['profiles']['air_quality']
    names = [f['name'] for f in prof['fields']]
    z = zipfile.ZipFile(UCI_ZIP)
    series = {}
    for n in sorted(x for x in z.namelist() if x.endswith('.csv')):
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8')))
        i0 = next(i for i, x in enumerate(rows) if (int(x['year']), int(x['month']), int(x['day']), int(x['hour'])) == AIR_START)
        series[rows[0]['station']] = rows[i0:i0 + N_ROUNDS]
    stations = sorted(series)
    assert len(stations) == 12 and all(len(series[s]) == N_ROUNDS for s in stations)
    stats = {'stations': stations, 'na_cells': 0, 'pm10_lt_pm25': 0}
    out = []
    for node in range(1, N_NODES + 1):
        st = (node - 1) % 12 + 1
        rows = []
        for r in range(1, N_ROUNDS + 1):
            x = series[stations[st - 1]][r - 1]
            env = f"{int(x['year']):04d}-{int(x['month']):02d}-{int(x['day']):02d} {int(x['hour']):02d}:00"
            w = base_row('C', 'AQ', node, 'air_quality', r, env, st, stations[st - 1],
                         'UCI-Beijing' if node <= 12 else 'UCI-Beijing-replay', 1, int(node > 12), 0)
            co = num(x['CO'])
            raw = {'PM25_ugm3': x['PM2.5'], 'PM10_ugm3': x['PM10'], 'CO_mgm3': '' if co is None else repr(co / 1000.0),
                   'NO2_ugm3': x['NO2'], 'SO2_ugm3': x['SO2'], 'O3_ugm3': x['O3'], 'temperature_C': x['TEMP'],
                   'RH_pct': fmt(rh_magnus(num(x['TEMP']), num(x['DEWP'])), 0.01), 'wind_ms': x['WSPM']}
            q = []
            for k, v in raw.items():
                if v in ('NA', ''):
                    raw[k] = ''
                    q.append('missing:' + k)
            w.update(raw)
            if node <= 12:
                stats['na_cells'] += sum(1 for k in raw if raw[k] == '')
            pm25, pm10 = num(w['PM25_ugm3']), num(w['PM10_ugm3'])
            if pm25 is not None and pm10 is not None and pm10 < pm25:
                q.append('pm10_lt_pm25_in_source')          # flagged, never altered
                if node <= 12:
                    stats['pm10_lt_pm25'] += 1
            w['quality_flag'] = ';'.join(q) if q else 'ok'
            v = vals_of(w, names)
            alarm = alarm_check(prof, v)
            w['alarm_flag'] = w['anomaly_flag'] = int(alarm)
            hour = int(x['hour'])
            if v['NO2_ugm3'] is not None and v['NO2_ugm3'] > 80 and (7 <= hour <= 9 or 17 <= hour <= 20):
                w['event_type'] = 'observed_no2_peak_rush_hour'
            elif v['PM25_ugm3'] is not None and v['PM25_ugm3'] > 150:
                w['event_type'] = 'observed_pm_episode'
            elif alarm:
                w['event_type'] = 'observed_exceedance'
            else:
                w['event_type'] = 'none'
            rows.append(w)
        add_modes(rows, prof, P, mask, names)
        out += rows
    return out, names, stats


# ----------------------------------------------------------------------------------------------- B: effluent (synthetic)
def ar1(rng, n, phi, sigma):
    e = rng.normal(0.0, sigma, n)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(1 - phi * phi)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def pulse(n, start, dur, rng_tau):
    """Event shape: 1 h rise, plateau for `dur` h, exponential decay with tau = rng_tau h."""
    t = np.arange(n, dtype=float)
    s = np.zeros(n)
    s[(t >= start) & (t < start + 1)] = 0.6
    s[(t >= start + 1) & (t < start + dur)] = 1.0
    tail = t >= start + dur
    s[tail] = np.exp(-(t[tail] - start - dur) / rng_tau)
    return s


def outages(rng, n_rounds, mean_events, lo, hi):
    miss = np.zeros(n_rounds, bool)
    for _ in range(rng.poisson(mean_events)):
        s = int(rng.integers(0, n_rounds))
        miss[s:s + int(rng.integers(lo, hi + 1))] = True
    return miss


def do_sat(t):
    return 14.652 - 0.41022 * t + 0.007991 * t * t - 0.000077774 * t ** 3     # freshwater, mg/L, 1 atm


def gen_effluent(P, mask, seed):
    prof = P['profiles']['industrial_effluent']
    names = [f['name'] for f in prof['fields']]
    scale = {f['name']: f['scale'] for f in prof['fields']}
    rng = np.random.default_rng(seed)
    n, hours = N_ROUNDS, np.arange(N_ROUNDS)
    n_src = 20
    src = []
    for s in range(n_src):                               # 20 outfalls (discharge sources), 10 sensor nodes each
        ev = []
        for _ in range(int(rng.poisson(2.5))):
            ev.append(('abnormal_discharge', int(rng.integers(0, n - 12)), float(rng.uniform(2, 10)),
                       {'COD': rng.uniform(2.5, 6), 'NH3': rng.uniform(2, 4), 'TURB': rng.uniform(2, 5),
                        'EC': rng.uniform(1.3, 2.5), 'pH': rng.choice([-1, 1]) * rng.uniform(1.5, 3), 'T': rng.uniform(2, 6)}))
        if rng.random() < 0.5:
            ev.append(('treatment_upset', int(rng.integers(0, n - 48)), float(rng.uniform(24, 48)),
                       {'COD': rng.uniform(1.5, 2), 'NH3': rng.uniform(1.5, 2.5), 'TURB': rng.uniform(1.3, 2),
                        'EC': 1.0, 'pH': rng.uniform(-0.5, 0.5), 'T': 0.0}))
        src.append({'COD': rng.uniform(80, 180), 'bc': rng.uniform(0.12, 0.18), 'NH3': rng.uniform(5, 25),
                    'pH': rng.uniform(6.8, 8.0), 'EC': rng.uniform(1200, 3500), 'k': rng.uniform(0.60, 0.70),
                    'TURB': rng.uniform(8, 30), 'T': rng.uniform(29, 35), 'amp': rng.uniform(0.10, 0.25),
                    'phase': rng.uniform(6, 10), 'events': ev})
    out, stats = [], {'sources': n_src, 'events': sum(len(s['events']) for s in src)}
    for node in range(1, N_NODES + 1):
        S = src[(node - 1) % n_src]
        dil = rng.uniform(0.6, 1.0)                      # node position along the drain: event attenuation
        lag = int(rng.integers(0, 3))
        diurnal = 1 + S['amp'] * np.sin(2 * np.pi * (hours - S['phase']) / 24.0)
        mult = {k: np.ones(n) for k in ('COD', 'NH3', 'TURB', 'EC')}
        dpH, dT = np.zeros(n), np.zeros(n)
        etype = np.array(['none'] * n, dtype=object)
        for name, st, dur, mag in S['events']:
            sh = pulse(n, st + lag, dur, max(1.0, dur / 3)) * dil
            for k in mult:
                mult[k] *= 1 + (mag[k] - 1) * sh
            dpH += mag['pH'] * sh
            dT += mag['T'] * sh
            etype[(sh > 0.05) & (etype == 'none')] = name
        cod = S['COD'] * diurnal * mult['COD'] * np.exp(ar1(rng, n, 0.85, 0.06))
        bod = cod * S['bc'] * np.exp(ar1(rng, n, 0.85, 0.05))
        nh3 = S['NH3'] * diurnal * mult['NH3'] * np.exp(ar1(rng, n, 0.85, 0.06))
        ec = S['EC'] * mult['EC'] * np.exp(ar1(rng, n, 0.9, 0.03))
        tds = ec * S['k']
        turb = S['TURB'] * diurnal * mult['TURB'] * np.exp(ar1(rng, n, 0.8, 0.08))
        temp = S['T'] + 1.5 * np.sin(2 * np.pi * (hours - 14) / 24.0) + dT + ar1(rng, n, 0.9, 0.15)
        ph = np.clip(S['pH'] + dpH + ar1(rng, n, 0.9, 0.05), 2.0, 12.0)
        do = np.clip(do_sat(temp) * np.clip(0.75 - 0.0015 * (cod - 100), 0.05, 0.95) + ar1(rng, n, 0.8, 0.15), 0.0, None)
        spike = rng.random(n) < 0.0005                   # isolated sensor glitch on COD
        cod = np.where(spike, cod * 3, cod)
        etype[spike] = 'sensor_spike'
        miss = outages(rng, n, 0.5, 3, 12)
        fmiss = rng.random((n, len(names))) < 0.002
        series = {'temperature_C': temp, 'pH': ph, 'conductivity_uScm': ec, 'TDS_mgL': tds, 'DO_mgL': do,
                  'turbidity_NTU': turb, 'COD_mgL': cod, 'BOD_mgL': bod, 'NH3N_mgL': nh3}
        rows = []
        for i in range(n):
            r = i + 1
            w = base_row('B', 'EF', node, 'industrial_effluent', r, f'T+{i:04d}h', (node - 1) % n_src + 1,
                         f'SYN-OUTFALL-{(node - 1) % n_src + 1:02d}', 'SYNTHETIC', 0, 0, 1)
            q = []
            for j, k in enumerate(names):
                if miss[i] or fmiss[i, j]:
                    w[k] = ''
                else:
                    w[k] = fmt(float(series[k][i]), scale[k])
            if miss[i]:
                q.append('sensor_outage')
            else:
                q += ['missing:' + k for j, k in enumerate(names) if fmiss[i, j]]
            w['quality_flag'] = ';'.join(q) if q else 'ok'
            w['alarm_flag'] = int(alarm_check(prof, vals_of(w, names)))
            w['event_type'] = 'sensor_outage' if miss[i] and etype[i] == 'none' else etype[i]
            w['anomaly_flag'] = int(etype[i] != 'none')
            rows.append(w)
        add_modes(rows, prof, P, mask, names)
        out += rows
    return out, names, stats


# ----------------------------------------------------------------------------------------------- D: soil (synthetic)
def gen_soil(P, mask, seed):
    prof = P['profiles']['soil_monitoring']
    names = [f['name'] for f in prof['fields']]
    scale = {f['name']: f['scale'] for f in prof['fields']}
    chem_names = [f['name'] for f in prof['fields'] if f.get('chem')]
    RC = prof['chem_interval_rounds']
    rng = np.random.default_rng(seed)
    n = N_ROUNDS
    hours = np.arange(n)
    rain = np.zeros(n)                                   # regional rainfall (mm/h), shared by all fields
    rain_ev = []
    for _ in range(4):
        st, dur = int(rng.integers(0, n - 10)), int(rng.integers(2, 9))
        rain[st:st + dur] += rng.uniform(2, 15)
        rain_ev.append((st, dur))
    etp = np.clip(0.55 * np.sin(np.pi * ((hours % 24) - 6) / 12.0), 0, None)   # potential ET, mm/h (~4-5 mm/day)
    etp = np.where(rain > 0, etp * 0.2, etp)
    depth = 300.0                                       # root-zone depth, mm
    n_fields = 10
    fields = []
    for _ in range(n_fields):
        fields.append({'fc': rng.uniform(30, 38), 'wp': rng.uniform(10, 14), 'sat': rng.uniform(42, 48),
                       'T': rng.uniform(26, 29), 'A': rng.uniform(2, 4), 'ecw': rng.uniform(1.0, 3.0),
                       'pH': rng.uniform(4.8, 6.5), 'N': rng.uniform(80, 180), 'P': rng.uniform(8, 30), 'K': rng.uniform(60, 200),
                       'fert': int(rng.integers(24, n - 48)), 'irr_mm': rng.uniform(20, 30), 'theta0': rng.uniform(20, 32)})
    out, stats = [], {'fields': n_fields, 'rain_events': rain_ev, 'irrigations': 0}
    for node in range(1, N_NODES + 1):
        F = fields[(node - 1) % n_fields]
        infl, et_f = rng.uniform(0.8, 1.2), rng.uniform(0.85, 1.15)
        th = np.empty(n)
        irr = np.zeros(n)
        theta = F['theta0'] + rng.uniform(-2, 2)
        trigger = F['wp'] + 0.35 * (F['fc'] - F['wp'])
        for i in range(n):
            if hours[i] % 24 == 6 and theta < trigger:                   # morning irrigation decision
                irr[i:i + 2] = F['irr_mm'] / 2.0
                stats['irrigations'] += 1
            ea = etp[i] * et_f * np.clip((theta - F['wp']) / (F['fc'] - F['wp']), 0, 1)
            inp = (rain[i] + irr[i]) * infl
            drain = 0.05 * max(0.0, theta - F['fc']) * depth / 100.0
            theta = theta + 100.0 * (inp - ea - drain) / depth
            theta = min(max(theta, 0.6 * F['wp']), F['sat'])            # physical bounds: residual .. saturation
            th[i] = theta
        vwc = np.clip(th + ar1(rng, n, 0.7, 0.3), 0, 100)
        wet = np.convolve(rain + irr, np.ones(4), 'full')[:n] > 0
        tsoil = F['T'] + F['A'] * np.sin(2 * np.pi * (hours - 14) / 24.0) - np.where(wet, 1.5, 0.0) + ar1(rng, n, 0.9, 0.1)
        fert = pulse(n, F['fert'], 1, 72.0)
        ecb = np.clip(F['ecw'] * (1 + 0.3 * fert) * (th / 100.0) ** 1.5 + ar1(rng, n, 0.8, 0.005), 0.0, None)
        leach = np.cumsum(rain) * 0.15                                   # N leached with cumulative rainfall (mg/kg)
        Nt = np.clip(F['N'] + rng.uniform(40, 80) * fert - leach - 0.05 * hours, 0, None)
        Pt = F['P'] + rng.uniform(5, 15) * (hours >= F['fert'])
        Kt = np.clip(F['K'] + rng.uniform(20, 50) * fert - 0.02 * hours, 0, None)
        pHt = F['pH'] - 0.1 * (hours >= F['fert']) + ar1(rng, n, 0.95, 0.02)
        spike = rng.random(n) < 0.0005
        vwc = np.where(spike, np.clip(vwc * 2.5, 0, 100), vwc)
        miss = outages(rng, n, 0.5, 3, 12)
        series = {'VWC_pct': vwc, 'soil_temperature_C': tsoil, 'bulk_EC_dSm': ecb, 'soil_pH': pHt,
                  'N_mgkg': Nt, 'P_mgkg': Pt, 'K_mgkg': Kt}
        rows = []
        for i in range(n):
            r = i + 1
            chem_round = (r - 1) % RC == 0
            w = base_row('D', 'SM', node, 'soil_monitoring', r, f'T+{i:04d}h', (node - 1) % n_fields + 1,
                         f'SYN-FIELD-{(node - 1) % n_fields + 1:02d}', 'SYNTHETIC', 0, 0, 1)
            for k in names:
                noise = rng.normal(0, 0.02 * abs(float(series[k][i]))) if k in chem_names else 0.0   # analytical noise
                w[k] = '' if miss[i] or (k in chem_names and not chem_round) else fmt(float(series[k][i]) + noise, scale[k])
            q = ['sensor_outage'] if miss[i] else []
            if not miss[i] and not chem_round:
                q.append('chem_not_scheduled')
            w['quality_flag'] = ';'.join(q) if q else 'ok'
            w['alarm_flag'] = int(alarm_check(prof, vals_of(w, names)))
            if spike[i]:
                ev = 'sensor_spike'
            elif miss[i]:
                ev = 'sensor_outage'
            elif rain[i] > 0:
                ev = 'rainfall'
            elif irr[i] > 0:
                ev = 'irrigation'
            elif F['fert'] <= i < F['fert'] + 2:
                ev = 'fertiliser_application'
            else:
                ev = 'none'
            w['event_type'] = ev
            w['anomaly_flag'] = int(spike[i])
            rows.append(w)
        add_modes(rows, prof, P, mask, names)
        out += rows
    return out, names, stats


# ----------------------------------------------------------------------------------------------- E: mixed (manifest)
def scaled_distribution(mx):
    """sensor_profiles.json gives the 200-node split; N nodes keep the same proportions (exact integers required)."""
    base = mx['distribution']
    dist = {k: v * N_NODES // sum(base.values()) for k, v in base.items()}
    assert all(v * N_NODES % sum(base.values()) == 0 for v in base.values()), 'N must keep the split integral'
    return dist


def gen_mixed(P):
    mx = P['mixed_environment']
    dist = scaled_distribution(mx)
    assert sum(dist.values()) == N_NODES and dist['water_quality'] >= 10
    rng = np.random.default_rng(mx['assignment_seed'])
    pool = list(rng.permutation(np.arange(11, N_NODES + 1)))
    assign = {k: 'water_quality' for k in range(1, 11)}
    order = ['water_quality', 'industrial_effluent', 'air_quality', 'soil_monitoring']
    need = {**dist, 'water_quality': dist['water_quality'] - 10}
    for cat in order:
        for _ in range(need[cat]):
            assign[int(pool.pop(0))] = cat
    assert not pool and len(assign) == N_NODES
    return assign


DATASET = {'water_quality': 'water_quality_200', 'industrial_effluent': 'industrial_effluent_200',
           'air_quality': 'air_quality_200', 'soil_monitoring': 'soil_monitoring_200'}
SOURCE_TEXT = {
    'water_quality': 'REAL: KSPCB River Periyar analysis reports Jan-Jul 2025 (MATLAB V2 consdata.xlsx -> data/v2_consdata_loaded.csv), '
                     'rows identical to the validated 200-node OMNeT++ workload (results_200node_optimization/final/baseline, seed 47). '
                     'Nodes 1-10 = the 10 station streams; nodes 11-{N} = virtual REPLAY nodes, node k replays station ((k-1) mod 10)+1.{W}',
    'air_quality': 'REAL: UCI Beijing Multi-Site Air Quality (Chen 2017, DOI 10.24432/C5RK5G, CC BY 4.0), hourly, 2016-12-01 00:00 + 500 h. '
                   'Nodes 1-12 = the 12 station streams (alphabetical); nodes 13-{N} = virtual REPLAY nodes, node k replays station ((k-1) mod 12)+1.',
    'industrial_effluent': 'SYNTHETIC: deterministic generator, 20 virtual outfalls x {E} nodes; not measurements.',
    'soil_monitoring': 'SYNTHETIC: deterministic generator, 10 virtual fields x {S} nodes; not measurements.'}


def write_dataset(outdir, key, rows, names, stats, P, seed):
    prof = P['profiles'][key]
    d = os.path.join(outdir, DATASET[key])
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'observations.csv')
    cols = COMMON + names + TAIL
    with open(path, 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
        wr.writeheader()
        for w in rows:
            wr.writerow(w)
    fl = {f['name']: f for f in prof['fields'] + prof.get('extension_fields', [])}
    meta = {
        'dataset': DATASET[key], 'scenario_id': prof['scenario'], 'sensor_type': key, 'description': prof['description'],
        'data_class': 'real (replayed)' if key in ('water_quality', 'air_quality') else 'synthetic',
        'source': SOURCE_TEXT[key].format(N=N_NODES, E=N_NODES // 20, S=N_NODES // 10, W='' if N_NODES <= 200 else
                  ' Nodes 201-%d copy their station node row by row (the 200-node workload covers nodes 1-200).' % N_NODES),
        'generator': 'scenario_study/generators/generate_scenarios.py',
        'generator_seed': seed, 'numpy_version': np.__version__, 'nodes': N_NODES, 'rounds': [1, N_ROUNDS],
        'rows': len(rows), 'observations_md5': md5(path),
        'columns': {
            'scenario_id': 'A water, B effluent, C air, D soil', 'sample_id': 'unique observation id <code>-n<node>-r<round>',
            'node_id': f'1..{N_NODES}, same node ids and positions as the {N_NODES}-node OMNeT++ topology', 'sensor_type': 'profile name',
            'round': 'network round 1..500', 'sim_time_s': 'OMNeT++ round start, (round-1) x 100 s (V2_200Node roundPeriod)',
            'env_time': 'environmental time: KSPCB sampling date of the carried sample / Beijing local hour / T+hours since synthetic origin',
            'source_station_id': 'station or virtual source stream the node reports', 'source_station': 'its name',
            'data_source': 'KSPCB | KSPCB-replay | UCI-Beijing | UCI-Beijing-replay | SYNTHETIC',
            'is_real': '1 = values are real measurements', 'is_replayed': '1 = virtual node replaying another real stream',
            'is_synthetic': '1 = generated values',
            'quality_flag': "'ok' or ';'-separated flags (missing:<field>, sensor_outage, no_observation_yet, DO_invalid_value, pm10_lt_pm25_in_source, chem_not_scheduled)",
            'anomaly_flag': 'synthetic: 1 inside an injected abnormal event or glitch (ground truth); real: = alarm_flag (no ground truth)',
            'alarm_flag': '1 if any profile alarm threshold is exceeded by this round value',
            'event_type': 'ground-truth event label (synthetic) or observed-exceedance label (real)',
            'm1_report': 'Mode 1 (controlled): 1 = report slot of the validated 200-node workload (identical mask in all scenarios), 4000-bit packet'
                         + ('' if N_NODES == 200 else '; retired, defined for nodes 1-200 only (0 for nodes > 200)'),
            'm2_report': 'Mode 2 (sensor-realistic): 1 = report sent this round', 'm2_trigger': 'periodic | alarm | periodic+alarm | +chem | none | no_data',
            'm2_priority': '1 = alarm report', 'm2_fields': 'measurement fields in the Mode 2 payload',
            'm2_payload_bytes': 'application payload = 10 B header + 2 B per present field',
            'm2_frame_bits': '8 x (17 B IEEE 802.15.4 PHY+MAC overhead + payload)',
            'm2_sensing_mJ': 'sensing + processing energy of this round (mJ), from sensor_profiles.json energy entries'},
        'fields': {n: {'unit': fl[n]['unit'], 'valid_rule': fl[n]['valid_rule'], 'encoding_scale': fl[n]['scale'],
                       'hardware': fl[n]['hardware'], 'spec_class': fl[n]['class']} for n in names},
        'payload_fields_mode2': [f['name'] for f in prof['fields']],
        'sampling': {'samples_per_round': prof['samples_per_round'], 'note': prof['sampling_note'],
                     'report_interval_rounds': prof['report_interval_rounds'], 'alarm_interval_rounds': prof['alarm_interval_rounds'],
                     'chem_interval_rounds': prof.get('chem_interval_rounds'), 'round_note': P['round_note']},
        'alarms': prof['alarms'],
        'missing_value_policy': 'missing = empty cell, listed in quality_flag; never converted to 0. Mode 1 still sends the slot '
                                '(missing fields flagged in the packet); Mode 2 sends only present fields and skips a round with none.',
        'stats': stats}
    with open(os.path.join(d, 'metadata.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    return meta


def write_matrix(P, path):
    cols = ['sensor_type', 'scenario', 'field', 'unit', 'operating_range', 'valid_rule', 'resolution', 'hardware', 'spec_class',
            'spec_source', 'sampling', 'samples_per_round', 'report_interval_rounds', 'alarm_threshold', 'alarm_source',
            'energy_per_reading_mJ', 'energy_basis', 'energy_class', 'missing_behaviour', 'anomaly_behaviour']
    anomaly = {'water_quality': 'real data, no injection; exceedances of CPCB criteria flagged',
               'air_quality': 'real data, no injection; NAAQS exceedances, rush-hour NO2 peaks and PM episodes flagged',
               'industrial_effluent': 'injected abnormal discharges (2-10 h) and treatment upsets (24-48 h), sensor spikes',
               'soil_monitoring': 'rainfall, irrigation and fertiliser events; rare sensor spikes'}
    with open(path, 'w', newline='') as f:
        wr = csv.writer(f, lineterminator='\n')
        wr.writerow(cols)
        for key, prof in P['profiles'].items():
            for fd in prof['fields'] + prof.get('extension_fields', []):
                al = [a for a in prof['alarms'] if a['field'] == fd['name']]
                at = '; '.join((f"outside {a['lo']}-{a['hi']}" if a['op'] == 'outside' else f"{a['op']} {a['value']}") for a in al)
                en = fd['energy']
                e = en['V'] * en['mA'] * en['ms'] / 1000.0
                ext = ' (extension, not in payload)' if fd in prof.get('extension_fields', []) else ''
                wr.writerow([key, prof['scenario'], fd['name'] + ext, fd['unit'], fd['range_sensor'], fd['valid_rule'], fd['resolution'],
                             fd['hardware'], fd['class'], fd['source'],
                             'chemistry, every %d rounds' % prof['chem_interval_rounds'] if fd.get('chem') else prof['sampling_note'],
                             prof['samples_per_round'], prof['report_interval_rounds'], at, '; '.join(a['source'] for a in al),
                             f'{e:.4g}', f"{en['V']} V x {en['mA']} mA x {en['ms']} ms; {en['note']}", en['class'],
                             'empty cell + quality_flag (never 0)', anomaly[key]])
            for x in prof.get('excluded_fields', []):
                wr.writerow([key, prof['scenario'], x['name'] + ' (EXCLUDED)', '', '', '', '', '', 'DATASET', x['reason']] + [''] * 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'scenarios'))
    ap.add_argument('--matrix', default=os.path.join(ROOT, 'scenario_study', 'SENSOR_PARAMETER_MATRIX.csv'))
    ap.add_argument('--nodes', type=int, default=200)
    a = ap.parse_args()
    global N_NODES
    N_NODES = a.nodes
    for k in DATASET: DATASET[k] = f'{k}_{N_NODES}'
    with open(PROFILES) as f:
        P = json.load(f)
    mask = load_mode1_mask()
    assert len(mask) == 96500
    metas = {}
    for key, fn in (('water_quality', lambda: gen_water(P, mask)), ('air_quality', lambda: gen_air(P, mask)),
                    ('industrial_effluent', lambda: gen_effluent(P, mask, P['seeds']['industrial_effluent'])),
                    ('soil_monitoring', lambda: gen_soil(P, mask, P['seeds']['soil_monitoring']))):
        rows, names, stats = fn()
        metas[key] = write_dataset(a.out, key, rows, names, stats, P, P['seeds'].get(key))
        print(f"{DATASET[key]:24s} rows {len(rows)}  md5 {metas[key]['observations_md5']}")
    assign = gen_mixed(P)
    d = os.path.join(a.out, f'mixed_environment_{N_NODES}')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'node_map.csv'), 'w', newline='') as f:
        wr = csv.writer(f, lineterminator='\n')
        wr.writerow(['node_id', 'sensor_type', 'profile_id', 'source_dataset', 'source_node_id', 'data_class'])
        for k in range(1, N_NODES + 1):
            c = assign[k]
            wr.writerow([k, c, P['profiles'][c]['profile_id'], DATASET[c] + '/observations.csv', k, metas[c]['data_class']])
    mx = {'dataset': f'mixed_environment_{N_NODES}', 'scenario_id': 'E', 'distribution': scaled_distribution(P['mixed_environment']),
          'assignment_seed': P['mixed_environment']['assignment_seed'], 'rule': P['mixed_environment']['rule'],
          'how_to_read': 'for node k take the rows of source_dataset with node_id == k (same node id, same position, same round). '
                         'Each node keeps its own profile fields; all nodes use the same routing configuration; no relay-only nodes.',
          'node_map_md5': md5(os.path.join(d, 'node_map.csv')),
          'source_md5': {DATASET[c]: metas[c]['observations_md5'] for c in metas}}
    with open(os.path.join(d, 'metadata.json'), 'w') as f:
        json.dump(mx, f, indent=1)
    print(f"mixed_environment_{N_NODES}    node_map md5 {mx['node_map_md5']}")
    if a.matrix:
        write_matrix(P, a.matrix)


if __name__ == '__main__':
    main()
