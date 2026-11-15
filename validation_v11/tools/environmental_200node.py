"""PRIMARY WORKFLOW analysis: the environmental WSN (V2_200Node_Environmental), five scenarios, N = 200 or 500 nodes.

Usage (from RLHybrid_Scalability_Experiment):  python -P tools/environmental_200node.py [--nodes 200|500]
Reads <res>/V2_200Node_Environmental-<scenario>-seed<s>-* and <res>/runtimes.csv, where <res> = results_environmental
(N = 200) or results_environmental_<N>. Writes into <res>: per_run.csv, per_run_by_data_class.csv, summary_mean_sd.csv,
by_data_class_mean_sd.csv, comparisons.csv (>= 3 seeds), environmental_report.txt and figures/*.png. Exit 1 if a check fails.
"""
import argparse, csv, hashlib, json, math, os, re, sys
from collections import Counter, defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ap = argparse.ArgumentParser()
ap.add_argument('--nodes', type=int, default=200)
N = ap.parse_args().nodes
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REF200 = os.path.join(ROOT, 'results_environmental')
RES = REF200 if N == 200 else os.path.join(ROOT, f'results_environmental_{N}')
BEFORE = os.path.join(ROOT, 'archive', 'audit_2026-11-12', 'results_environmental_before_frame_fix')   # fixed profile frames
FIG = os.path.join(RES, 'figures')
SC = os.path.join(ROOT, 'data', 'scenarios')
CFG = 'V2_200Node_Environmental'
SCN = ['water', 'effluent', 'air', 'soil', 'mixed']
NAME = {'water': 'Water', 'effluent': 'Effluent', 'air': 'Air', 'soil': 'Soil', 'mixed': 'Mixed'}
TYPE = {'water': 'water_quality', 'effluent': 'industrial_effluent', 'air': 'air_quality', 'soil': 'soil_monitoring', 'mixed': None}
DSDIR = {s: f'data/scenarios/{t}_{N}' for s, t in TYPE.items() if t}
DSDIR['mixed'] = f'data/scenarios/mixed_environment_{N}'
ROUNDS, E0 = 500, 2.0
VARY = {'scenario', 'scenarioDataset', 'scenarioSeed', 'outputPrefix'}   # the only parameters allowed to differ between runs
P = json.load(open(os.path.join(ROOT, 'scenario_study', 'dataset_metadata', 'sensor_profiles.json')))
out, ok = [], True


def say(s=''): out.append(s)


def check(cond, what):
    global ok
    ok &= bool(cond)
    say(f'  [{"OK" if cond else "FAIL"}] {what}')


# ---------------------------------------------------------------- paired t-test without scipy (incomplete beta, NR 6.4)
def _betacf(a, b, x):
    qab, qap, qam, c, d = a + b, a + 1, a - 1, 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > 1e-300 else 1e-300); h = d
    for m in range(1, 300):
        for aa in (m * (b - m) * x / ((qam + 2 * m) * (a + 2 * m)), -(a + m) * (qab + m) * x / ((a + 2 * m) * (qap + 2 * m))):
            d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
            c = 1 + aa / c; c = c if abs(c) > 1e-300 else 1e-300
            h *= d * c
        if abs(d * c - 1) < 1e-14: break
    return h


def _betai(a, b, x):
    if x <= 0 or x >= 1: return 0.0 if x <= 0 else 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * _betacf(b, a, 1 - x) / b


def t_two_sided(t, df): return _betai(df / 2, 0.5, df / (df + t * t))


assert abs(t_two_sided(2.776445, 4) - 0.05) < 1e-5 and abs(t_two_sided(4.604095, 4) - 0.01) < 1e-5
assert abs(t_two_sided(2.228139, 10) - 0.05) < 1e-5 and t_two_sided(0.0, 5) == 1.0


def paired(a, b):
    d = np.asarray(b, float) - np.asarray(a, float)
    sd = d.std(ddof=1)
    if sd == 0: return float('nan'), float('nan')
    t = d.mean() / (sd / math.sqrt(len(d)))
    return t, t_two_sided(abs(t), len(d) - 1)


def md5(p): return hashlib.md5(open(p, 'rb').read()).hexdigest()


# ---------------------------------------------------------------- profiles: fields, payload and frame bits
fr = P['frame']
OVH = 8 * fr['mac_phy_overhead_bytes']
def payload_bits(n): return 8 * (fr['app_header_bytes'] + fr['field_bytes'] * n)
PROFILE = {}
for t, prof in P['profiles'].items():
    base = [f['name'] for f in prof['fields'] if not f.get('chem')]
    chem = [f['name'] for f in prof['fields'] if f.get('chem')]
    PROFILE[t] = {'base': base, 'chem': chem, 'ext': [f['name'] for f in prof.get('extension_fields', [])],
                  'payload': payload_bits(len(base)), 'frame': OVH + payload_bits(len(base)),
                  'payload_chem': payload_bits(len(base) + len(chem)) if chem else None,
                  'frame_chem': OVH + payload_bits(len(base) + len(chem)) if chem else None,
                  'samples': prof['samples_per_round'], 'report': prof['report_interval_rounds'],
                  'alarm': prof['alarm_interval_rounds'], 'chem_every': prof['chem_interval_rounds']}
MAXFRAME = {t: max(p['frame'], p['frame_chem'] or 0) for t, p in PROFILE.items()}
def local_only_mJ(t):
    """mJ per round of sensors read but not transmitted (extension fields: water DO for its DO < 4 mg/L alarm)."""
    prof, e = P['profiles'][t], 0.0
    for f in prof.get('extension_fields', []):
        en = f['energy']; one = en['V'] * en['mA'] * en['ms'] / 1000.0
        e += one * P['round_hours'] if en['ms'] >= 3600000 else one * prof['samples_per_round']
    return e
LOCAL_MJ = {t: local_only_mJ(t) for t in P['profiles']}
DO_ALARM = [a for a in P['profiles']['water_quality']['alarms'] if a['field'] == 'DO_mgL']

say(f'ENVIRONMENTAL WSN (V2_200Node_Environmental), N = {N}: {N} sensing + forwarding nodes, one BS, 600 x 50 m, 500 rounds')
say('(1 round = 1 h of environmental time; 100 s of OMNeT++ scheduling time), 2 J radio energy per node, first-order radio,')
say('tabular Q-learning RL-Hybrid with variant C (energyGuard 0.8), no retransmission. Only the scenario workload changes.')
say('Every report is one 802.15.4 frame of its own profile (only its present fields); energy, feasibility and airtime use the')
say('actual frame bits. Sensing energy is a separate ledger, never charged to the 2 J battery: lifetimes are communication-network')
say('lifetimes. A run seed sets topology + channel + RL stream, identical in every scenario.')
say('=' * 118)
say('Sensor profiles (sensor_profiles.json): payload = 10 B header + 2 B per present field; frame = payload + 17 B 802.15.4 MAC/PHY')
for t, p in PROFILE.items():
    say(f'  {t:20s} fields {", ".join(p["base"])}' + (f'; chemistry rounds add {", ".join(p["chem"])}' if p['chem'] else ''))
    say(f'  {"":20s} full payload {p["payload"]} bit, frame {p["frame"]} bit' + (f' ({p["payload_chem"]} / {p["frame_chem"]} bit on chemistry rounds, every {p["chem_every"]} h)' if p['chem'] else '')
        + f'; {p["samples"]} samples per round, report every {p["report"]} h, alarm reports every {p["alarm"]} h'
        + (f'; sensed but not transmitted: {", ".join(p["ext"])}' if p['ext'] else ''))
say()
say('Checks')
check({t: (p['payload'], p['frame'], p['payload_chem'], p['frame_chem']) for t, p in PROFILE.items()} ==
      {'water_quality': (144, 280, None, None), 'industrial_effluent': (224, 360, None, None), 'air_quality': (224, 360, None, None),
       'soil_monitoring': (128, 264, 192, 328)}, 'profile payload / frame bits: water 144/280, effluent 224/360, air 224/360, soil 128/264 (chemistry 192/328)')

# ---------------------------------------------------------------- datasets: md5, data classes, per-report frame bits
klass, dsbits, bad = {}, {}, []
for t in [v for v in TYPE.values() if v]:
    d = os.path.join(SC, f'{t}_{N}')
    meta = json.load(open(os.path.join(d, 'metadata.json')))
    if md5(os.path.join(d, 'observations.csv')) != meta['observations_md5']: bad.append(f'{t}_{N}: md5 differs from metadata')
    with open(os.path.join(d, 'observations.csv'), newline='') as fh:
        for w in csv.DictReader(fh):
            nd = int(w['node_id'])
            if w['round'] == '1':
                klass[(t, nd)] = 'synthetic' if w['is_synthetic'] == '1' else ('replayed' if w['is_replayed'] == '1' else 'real')
            if w['m2_report'] == '1': dsbits[(t, nd, int(w['round']))] = int(w['m2_frame_bits'])
if N == 200:
    REF_MD5 = {'water_quality_200/observations.csv': '45037423', 'industrial_effluent_200/observations.csv': 'b4b5327b',
               'air_quality_200/observations.csv': '6f2b95b6', 'soil_monitoring_200/observations.csv': '8787ec59',
               'mixed_environment_200/node_map.csv': 'f1ca07b9'}
    bad += [f for f, h in REF_MD5.items() if not md5(os.path.join(SC, f)).startswith(h)]
check(not bad, f'the five scenario datasets for N = {N} match their recorded md5' + (' (validated 200-node checksums)' if N == 200 else ''))
node_map = {int(r['node_id']): r['sensor_type'] for r in csv.DictReader(open(os.path.join(SC, f'mixed_environment_{N}', 'node_map.csv'), newline=''))}
cnt = Counter(node_map.values())
check(len(node_map) == N and set(cnt.values()) == {N // 4} and all(node_map[k] == 'water_quality' for k in range(1, 11)),
      f'mixed node map: {N // 4} water + {N // 4} effluent + {N // 4} air + {N // 4} soil nodes; nodes 1-10 (KSPCB stations) water')


def node_info(s, nd):
    t = TYPE[s] or node_map[nd]
    return t, klass[(t, nd)]


def sca_read(p):
    pars, node, ctl = {}, defaultdict(dict), {}
    for ln in open(p):
        if ln.startswith('par '):
            mod, name, val = ln.split(' ', 3)[1:]
            pars[(mod, name)] = val.strip()
        elif ln.startswith('scalar '):
            g = re.match(r'scalar PeriyarRiverNetwork\.node\[(\d+)\] (\w+) (\S+)', ln)
            if g: node[g.group(2)][int(g.group(1))] = float(g.group(3)); continue
            g = re.match(r'scalar PeriyarRiverNetwork\.controller (\w+) (\S+)', ln)
            if g: ctl[g.group(1)] = float(g.group(2))
    return pars, node, ctl


runtime = {(r['scenario'], int(r['seed'])): r for r in csv.DictReader(open(os.path.join(RES, 'runtimes.csv'), newline=''))}
SEEDS = sorted({sd for (_, sd) in runtime})
check(all((s, sd) in runtime for s in SCN for sd in SEEDS), f'runs present for all five scenarios and seeds {SEEDS}')

# ---------------------------------------------------------------- per-run metrics
runs, cls_runs, series, ref_pars, topo, sched, fdist = [], [], {}, None, {}, {}, defaultdict(Counter)
bad, CTL = [], 'PeriyarRiverNetwork.controller'
for seed in SEEDS:
    for s in SCN:
        pre = os.path.join(RES, f'{CFG}-{s}-seed{seed}-')
        sca = os.path.join(RES, f'{CFG}-{s}-seed{seed}.sca')
        pars, node, ctl = sca_read(sca)
        flat = {k: v for k, v in pars.items() if k[1] not in VARY}
        if ref_pars is None: ref_pars = flat
        diffk = sorted({k[1] for k in set(flat) | set(ref_pars) if flat.get(k) != ref_pars.get(k)})
        if diffk: bad.append(f'{s} seed {seed}: parameters differ from the first run: {diffk}')
        profile = DSDIR[s].split('/')[-1].rsplit('_', 1)[0]
        exp = {'scenario': f'"\\"{s}\\""', 'scenarioDataset': f'"\\"data/scenarios/{profile}_{N}\\""', 'scenarioSeed': str(seed),
               'packetSize': '4000', 'energyGuard': '0.8', 'enableRetransmission': 'false', 'numRounds': '500',
               'scenarioMode': '"\\"m2\\""', 'scenarioFrameBits': '"\\"dataset\\""', 'topologySeed': '-1', 'extraTopologySeed': '-1',
               'channelStream': '"\\"matlab\\""', 'initialEnergy': '2', 'reportPreservingEnergy': 'true', 'qPriorInit': 'false'}
        for k, v in exp.items():
            if pars.get((CTL, k)) != v: bad.append(f'{s} seed {seed}: {k} = {pars.get((CTL, k))}, expected {v}')
        if pars.get(('PeriyarRiverNetwork', 'numNodes')) != str(N) or len(node['residualEnergy']) != N:
            bad.append(f'{s} seed {seed}: not {N} node modules')
        rt = runtime[(s, seed)]
        if rt['exit'] != '0' or rt['checks_ok'] != '1': bad.append(f'{s} seed {seed}: exit {rt["exit"]}, invariant line {rt["checks_ok"]}')
        nodes_b = open(pre + 'nodes.csv', 'rb').read()
        if topo.setdefault(seed, nodes_b) != nodes_b: bad.append(f'{s} seed {seed}: topology differs between scenarios')
        pos = [(int(r['node']), float(r['x']), float(r['y'])) for r in csv.DictReader(open(pre + 'nodes.csv', newline=''))]
        if ([p[0] for p in pos] != list(range(1, N + 1)) or len({(x, y) for _, x, y in pos}) != N
                or not all(0 <= x <= 600 and 0 <= y <= 50 and (x, y) != (600, 25) for _, x, y in pos)):
            bad.append(f'{s} seed {seed}: node ids / positions invalid or duplicated')
        if N != 200 and os.path.exists(os.path.join(REF200, f'{CFG}-{s}-seed{seed}-nodes.csv')):
            ref = open(os.path.join(REF200, f'{CFG}-{s}-seed{seed}-nodes.csv'), 'rb').read().splitlines()
            if nodes_b.splitlines()[:len(ref)] != ref: bad.append(f'{s} seed {seed}: first 200 nodes differ from the 200-node layout')
        wl = list(csv.DictReader(open(pre + 'workload.csv', newline='')))
        wlb = open(pre + 'workload.csv', 'rb').read()
        if sched.setdefault(s, wlb) != wlb: bad.append(f'{s} seed {seed}: report schedule differs between seeds')
        fb_bad = 0
        for w in wl:
            t = node_info(s, int(w['sourceNode']))[0]
            b = int(w['frameBits'])
            fb_bad += b != dsbits.get((t, int(w['sourceNode']), int(w['round']))) or b > MAXFRAME[t]
            if seed == SEEDS[0]: fdist[(s, t)][b] += 1
        if fb_bad: bad.append(f'{s} seed {seed}: {fb_bad} reports whose frame bits differ from the dataset or exceed the profile')
        reporting = len({int(w['sourceNode']) for w in wl})
        mt = dict(zip(*list(csv.reader(open(pre + 'metrics.csv', newline='')))))
        summ = open(pre + 'summary.txt').read()
        if 'energy closes OK; slot accounting OK; per-round MATLAB invariants OK' not in summ: bad.append(f'{s} seed {seed}: run checks')
        tr = re.search(r'radio traffic\s*: ([\d.]+) Mbit on air in (\d+) report transmissions \(mean ([\d.]+) bit\); mean generated frame ([\d.]+) bit', summ)
        bsxy = re.search(r'BS \(([\d.]+), ([\d.]+)\), ([\d.]+) x ([\d.]+) m, E0 = ([\d.]+) J', summ).groups()
        if bsxy != ('600.000000', '25.000000', '600', '50', '2'): bad.append(f'{s} seed {seed}: BS / area / E0 {bsxy}')
        qx = re.search(r'Q updates / explorations : (\d+) / (\d+)\s+\(exploitation (\d+)', summ)
        led = list(csv.DictReader(open(pre + 'sensing_ledger.csv', newline='')))
        pr = list(csv.DictReader(open(pre + 'per_round.csv', newline='')))
        alive = np.array([int(r['aliveCount']) for r in pr])
        series[(s, seed)] = (alive, np.array([float(r['residualJ']) for r in pr]))
        round_s = max(float(r['roundEndTime']) - (int(r['round']) - 1) * 100 for r in pr)
        txJ, rxJ, agJ = (sum(float(r[k]) for r in pr) for k in ('txJ', 'rxJ', 'aggJ'))
        gen, dlv, emi = int(mt['workloadAvailable']), int(mt['delivered']), int(mt['sourceAvailable'])
        if abs(txJ + rxJ + agJ - float(mt['spentJ'])) > 1e-6: bad.append(f'{s} seed {seed}: TX + RX + aggregation != spent')
        nr = sum(int(x['operationalRounds']) for x in led)
        fnd, hnd = int(mt['FND']), next((i + 1 for i, a in enumerate(alive) if a <= N // 2), -1)
        mean_frame = float(tr.group(4))
        out_mb = sum(os.path.getsize(os.path.join(RES, f)) for f in os.listdir(RES) if f.startswith(f'{CFG}-{s}-seed{seed}')) / 1e6
        runs.append({'scenario': s, 'seed': seed, 'nodes': N, 'scheduled': int(mt['scheduled']), 'generated': gen, 'emitted': emi,
                     'delivered': dlv, 'delivery_ratio_pct': 100 * dlv / gen, 'source_packet_pdr_pct': 100 * dlv / emi,
                     'FND_round': fnd if fnd > 0 else float('nan'), 'HND_round': hnd if hnd > 0 else float('nan'),
                     'alive_r500': int(mt['finalAlive']), 'operational_node_rounds': nr, 'availability_pct': 100 * nr / (N * ROUNDS),
                     'reporting_nodes': reporting, 'relaying_nodes': sum(1 for v in node['reportsReceivedFromOthers'].values() if v > 0),
                     'residual_radio_J': float(mt['residualJ']), 'residual_pct_of_initial': 100 * float(mt['residualJ']) / (E0 * N),
                     'spent_radio_J': float(mt['spentJ']), 'tx_J': txJ, 'rx_J': rxJ, 'aggregation_J': agJ,
                     'min_node_residual_J': min(node['residualEnergy'].values()),
                     'sensing_kJ_operational': sum(float(x['sensingJ_operational']) for x in led) / 1000,
                     'sensing_kJ_local_only': sum(int(x['operationalRounds']) * LOCAL_MJ[x['sensorType']] for x in led) / 1e6,
                     'energy_per_delivered_mJ': 1000 * float(mt['spentJ']) / dlv, 'mean_delay_ms': 1000 * float(mt['meanDelayS']),
                     'mean_hops': float(mt['meanHops']), 'mean_frame_bits': mean_frame, 'mean_payload_bits': mean_frame - OVH,
                     'report_transmissions': int(tr.group(2)), 'transmitted_Mbit': float(tr.group(1)),
                     'physical_frames': ctl.get('physicalFrames'), 'frames_received': int(sum(node['rxFrames'].values())),
                     'routing_decisions': int(qx.group(2)) + int(qx.group(3)), 'q_updates': int(qx.group(1)),
                     'q_table_entries': int(sum(node['qTableNonZeroEntries'].values())), 'max_round_duration_s': round_s,
                     'loss_channel': ctl.get('lossChannel'), 'loss_energy': ctl.get('lossEnergy'),
                     'loss_no_candidate': ctl.get('lossNoCandidate'), 'loss_TTL': ctl.get('lossTTL'),
                     'runtime_s': float(rt['runtime_s']), 'peak_memory_MB': float(rt.get('peak_MB') or 'nan'), 'output_MB': out_mb})
        c = defaultdict(lambda: [0, 0, 0.0])
        for r in csv.DictReader(open(pre + 'reports.csv', newline='')):
            e = c[node_info(s, int(r['sourceNode']))]
            e[0] += 1
            if r['fate'] == 'delivered': e[1] += 1; e[2] += float(r['pathDelayS'])
        if sum(v[0] for v in c.values()) != gen: bad.append(f'{s} seed {seed}: data-class split incomplete')
        for (t, k), (g, d, dl) in sorted(c.items()):
            cls_runs.append({'scenario': s, 'seed': seed, 'sensor_type': t, 'data_class': k, 'generated': g, 'delivered': d,
                             'delivery_ratio_pct': 100 * d / g, 'mean_delay_ms': 1000 * dl / d if d else float('nan')})
check(not bad, f'{len(runs)} runs: identical parameters except scenario / dataset / seed / output prefix; {N} node modules, BS (600, 25), '
      '600 x 50 m, 2 J, 500 rounds, variant C 0.8, no retransmission, node-death k = 4000 bit, frames from the dataset; valid unique '
      'positions, same topology for a seed in every scenario' + ('' if N == 200 else ', first 200 nodes = the 200-node layout') +
      '; same schedule in every seed; every report carries its own dataset frame bits; TX + RX + aggregation = spent; run invariants OK')
for b in bad: say('      ' + b)
check(all(r['reporting_nodes'] == N for r in runs), f'every one of the {N} nodes generates reports (no relay-only nodes)')

# ---------------------------------------------------------------- aggregation and paired comparisons
MET = [k for k in runs[0] if k not in ('scenario', 'seed', 'nodes')]
by = defaultdict(list)
for r in runs: by[r['scenario']].append(r)
agg = {}
for s in SCN:
    a = {'scenario': s, 'nodes': N, 'seeds': len(by[s])}
    for k in MET:
        v = np.array([np.nan if r[k] is None else r[k] for r in by[s]], float)
        f = v[~np.isnan(v)]
        a[k + '_mean'] = f.mean() if len(f) else float('nan')
        a[k + '_sd'] = f.std(ddof=1) if len(f) > 1 else float('nan')
        if k in ('FND_round', 'HND_round'): a[k.replace('_round', '') + '_seeds_reached'] = len(f)
    agg[s] = a
cls_by = defaultdict(list)
for r in cls_runs: cls_by[(r['scenario'], r['sensor_type'], r['data_class'])].append(r)
cls_agg = [{'scenario': k[0], 'sensor_type': k[1], 'data_class': k[2], 'nodes_in_class': sum(1 for (t, nd), c in klass.items() if t == k[1] and c == k[2] and (TYPE[k[0]] or node_map[nd]) == k[1]),
            'generated': v[0]['generated'], 'delivered_mean': np.mean([x['delivered'] for x in v]),
            'delivery_ratio_pct_mean': np.mean([x['delivery_ratio_pct'] for x in v]),
            'delivery_ratio_pct_sd': np.std([x['delivery_ratio_pct'] for x in v], ddof=1) if len(v) > 1 else float('nan'),
            'mean_delay_ms_mean': np.mean([x['mean_delay_ms'] for x in v])} for k, v in cls_by.items()]
CMP = ['delivery_ratio_pct', 'source_packet_pdr_pct', 'residual_radio_J', 'energy_per_delivered_mJ', 'mean_delay_ms', 'transmitted_Mbit']
pairs = [('water', b) for b in ('effluent', 'air', 'soil')] + [(b, 'mixed') for b in ('water', 'effluent', 'air', 'soil')]
cmp_rows = []
if len(SEEDS) >= 3:
    for a, b in pairs:
        for k in CMP:
            va, vb = [r[k] for r in by[a]], [r[k] for r in by[b]]   # seed order: paired by seed (same topology and channel)
            t, p = paired(va, vb)
            cmp_rows.append({'A': a, 'B': b, 'metric': k, 'mean_A': np.mean(va), 'mean_B': np.mean(vb), 'diff_B_minus_A': np.mean(vb) - np.mean(va),
                             'diff_sd': np.std(np.subtract(vb, va), ddof=1), 'diff_pct_of_A': 100 * (np.mean(vb) - np.mean(va)) / np.mean(va),
                             'paired_t': t, 'p': p})
    tested = sorted([r for r in cmp_rows if not math.isnan(r['p'])], key=lambda r: r['p'])
    run_max = 0.0
    for i, r in enumerate(tested):
        run_max = max(run_max, min(1.0, (len(tested) - i) * r['p']))
        r['p_holm'] = run_max
    for r in cmp_rows:
        r.setdefault('p_holm', float('nan'))
        r['significant_holm_0.05'] = 'n/a (identical in every seed)' if math.isnan(r['p']) else ('yes' if r['p_holm'] < 0.05 else 'no')

# ---------------------------------------------------------------- files
os.makedirs(FIG, exist_ok=True)


def write(name, data):
    if not data: return
    with open(os.path.join(RES, name), 'w', newline='') as fo:
        w = csv.DictWriter(fo, fieldnames=list(data[0]))
        w.writeheader()
        for r in data: w.writerow({k: (f'{v:.6g}' if isinstance(v, (float, np.floating)) else v) for k, v in r.items()})


write('per_run.csv', runs)
write('per_run_by_data_class.csv', cls_runs)
write('summary_mean_sd.csv', list(agg.values()))
write('by_data_class_mean_sd.csv', cls_agg)
write('comparisons.csv', cmp_rows)


def ms(s, k, f='.2f'):
    a = agg[s]
    if k in ('FND_round', 'HND_round'):
        n = a[k.replace('_round', '') + '_seeds_reached']
        return 'not reached' if n == 0 else f"{a[k + '_mean']:.0f}" + ('' if math.isnan(a[k + '_sd']) else f"+-{a[k + '_sd']:.0f}") + ('' if n == len(SEEDS) else f' ({n}/{len(SEEDS)})')
    return f"{a[k + '_mean']:{f}}" + ('' if math.isnan(a[k + '_sd']) else f"+-{a[k + '_sd']:{f}}")


say()
say(f'Results (mean +- sample SD over seeds {SEEDS}; generated = scheduled = valid reports, identical in every seed)')
cols = [('generated', 'generated', '.0f'), ('delivered', 'delivered', '.0f'), ('delivery_ratio_pct', 'deliv. ratio %', '.2f'),
        ('source_packet_pdr_pct', 'srcPDR %', '.2f'), ('FND_round', 'FND', ''), ('HND_round', 'HND', ''), ('alive_r500', 'alive500', '.1f'),
        ('operational_node_rounds', 'node-rounds', '.0f'), ('residual_radio_J', 'resid J', '.2f'), ('residual_pct_of_initial', 'resid % of 2N J', '.2f'),
        ('sensing_kJ_operational', 'sensing kJ', '.0f'), ('energy_per_delivered_mJ', 'mJ/deliv', '.3f'), ('mean_delay_ms', 'delay ms', '.2f'),
        ('mean_hops', 'hops', '.2f'), ('mean_frame_bits', 'frame bit', '.1f'), ('mean_payload_bits', 'payload bit', '.1f'),
        ('transmitted_Mbit', 'tx Mbit', '.1f'), ('runtime_s', 'run s', '.1f'), ('peak_memory_MB', 'peak MB', '.0f')]
say(f'  {"":15s} ' + ' '.join(f'{NAME[s]:>16s}' for s in SCN))
for k, h, f in cols:
    say(f'  {h:15s} ' + ' '.join(f'{(format(agg[s][k + "_mean"], ".0f") if k == "generated" else ms(s, k, f)):>16s}' for s in SCN))
say()
say('Radio energy by component (J) and network losses (reports, mean over seeds)')
for s in SCN:
    a = agg[s]
    say(f'  {NAME[s]:9s} TX {ms(s, "tx_J")}  RX {ms(s, "rx_J")}  aggregation {ms(s, "aggregation_J", ".3f")}  | lost: channel {a["loss_channel_mean"]:.0f}, '
        f'energy {a["loss_energy_mean"]:.1f}, no candidate {a["loss_no_candidate_mean"]:.1f}, TTL {a["loss_TTL_mean"]:.1f}  | lowest node residual {a["min_node_residual_J_mean"]:.3f} J')
say('  Node-death rule E < E_elec x 4000 bit = 0.2 mJ (validated threshold, unchanged).')
say()
say('Sensing-energy ledger (separate estimate, never charged to the 2 J radio battery), kJ over operational node-rounds')
for s in SCN:
    a = agg[s]
    say(f'  {NAME[s]:9s} total {a["sensing_kJ_operational_mean"]:10.2f} = transmitted-field sensors '
        f'{a["sensing_kJ_operational_mean"] - a["sensing_kJ_local_only_mean"]:10.2f} + local-only sensors {a["sensing_kJ_local_only_mean"]:8.2f}')
say(f'  local-only = the water DO probe ({LOCAL_MJ["water_quality"]:.1f} mJ per water node-round): read every round for the alarm '
    f'{DO_ALARM[0]["field"]} {DO_ALARM[0]["op"]} {DO_ALARM[0]["value"]} mg/L, which raises alarm reports, but DO is not in the 4-field payload')
say()
say('Scalability (mean over seeds)')
for s in SCN:
    a = agg[s]
    say(f'  {NAME[s]:9s} routing decisions {a["routing_decisions_mean"]:.0f}, Q updates {a["q_updates_mean"]:.0f}, Q-table entries '
        f'{a["q_table_entries_mean"]:.0f} ({a["q_table_entries_mean"] / N:.0f} per node), physical frames {a["physical_frames_mean"]:.0f}, '
        f'frames received {a["frames_received_mean"]:.0f}, relaying nodes {a["relaying_nodes_mean"]:.0f}/{N}, longest round {a["max_round_duration_s_mean"]:.2f} s of 100 s, '
        f'output {a["output_MB_mean"]:.1f} MB per run')
say()
say('Actual frame sizes per report (first seed; bits: count)')
for (s, t), c in sorted(fdist.items(), key=lambda x: (SCN.index(x[0][0]), x[0][1])):
    say(f'  {NAME[s]:9s} {t:20s} ' + ', '.join(f'{b}: {n}' for b, n in sorted(c.items(), reverse=True)))
say()
say('Delivery by data source (delivered / generated %, mean +- SD; routing never reads measurement values)')
for r in cls_agg:
    sd = '' if math.isnan(r['delivery_ratio_pct_sd']) else f' +- {r["delivery_ratio_pct_sd"]:.2f}'
    say(f'  {NAME[r["scenario"]]:9s} {r["sensor_type"]:20s} {r["data_class"]:9s} {r["nodes_in_class"]:4d} nodes, generated {r["generated"]:6d}  '
        f'{r["delivery_ratio_pct_mean"]:6.2f}{sd}   delay {r["mean_delay_ms_mean"]:6.2f} ms')
if cmp_rows:
    say()
    say(f'Paired comparisons by seed (same topology and channel stream per seed): paired t-test, df {len(SEEDS) - 1}, Holm over {len(tested)} tests')
    say(f'  {"A":9s} {"B":9s} {"metric":24s} {"mean A":>10s} {"mean B":>10s} {"B-A":>9s} {"B-A %":>7s} {"p Holm":>8s}  sig')
    for r in cmp_rows:
        say(f'  {r["A"]:9s} {r["B"]:9s} {r["metric"]:24s} {r["mean_A"]:10.3f} {r["mean_B"]:10.3f} {r["diff_B_minus_A"]:9.3f} '
            f'{r["diff_pct_of_A"]:7.1f} {r["p_holm"]:8.2g}  {r["significant_holm_0.05"]}')
say()
say('Workload drivers (identical in every seed)')
for s in SCN:
    a = agg[s]
    say(f'  {NAME[s]:9s} {a["generated_mean"]:7.0f} reports = {a["generated_mean"] / (N * ROUNDS):.3f} per node-hour; mean frame '
        f'{a["mean_frame_bits_mean"]:.1f} bit (payload {a["mean_payload_bits_mean"]:.1f}); offered {a["generated_mean"] * a["mean_frame_bits_mean"] / 1e6:.1f} Mbit')
if N == 200 and os.path.exists(os.path.join(BEFORE, 'per_run.csv')):
    old = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(BEFORE, 'per_run.csv'), newline='')): old[r['scenario']].append(r)
    say()
    say('Effect of the per-report dataset frame sizes (archived run with one fixed frame per profile -> now, mean over the same seeds)')
    for s in SCN:
        f = lambda rows, k: np.mean([float(r[k]) for r in rows])
        say(f'  {NAME[s]:9s} frame {f(old[s], "mean_frame_bits"):6.1f} -> {agg[s]["mean_frame_bits_mean"]:6.1f} bit   delivery {f(old[s], "delivery_ratio_pct"):6.2f} -> '
            f'{agg[s]["delivery_ratio_pct_mean"]:6.2f} %   residual {f(old[s], "residual_radio_J"):7.2f} -> {agg[s]["residual_radio_J_mean"]:7.2f} J   delay '
            f'{f(old[s], "mean_delay_ms"):6.2f} -> {agg[s]["mean_delay_ms_mean"]:6.2f} ms')
ref = defaultdict(list)
CMPK = [('delivery_ratio_pct', 'delivery ratio %', '.2f'), ('delivered', 'delivered reports', '.0f'), ('source_packet_pdr_pct', 'source-packet PDR %', '.2f'),
        ('residual_radio_J', 'residual radio J', '.1f'), ('residual_pct_of_initial', 'residual % of initial', '.2f'),
        ('energy_per_delivered_mJ', 'mJ per delivered', '.3f'), ('mean_delay_ms', 'delay ms', '.2f'), ('alive_r500', 'operational nodes r500', '.0f'),
        ('operational_node_rounds', 'operational node-rounds', '.0f'), ('transmitted_Mbit', 'transmitted Mbit', '.1f'),
        ('runtime_s', 'runtime s', '.1f'), ('peak_memory_MB', 'peak memory MB', '.0f')]
if N != 200 and os.path.exists(os.path.join(REF200, 'per_run.csv')):
    for r in csv.DictReader(open(os.path.join(REF200, 'per_run.csv'), newline='')): ref[r['scenario']].append(r)
    S200 = sorted({int(r['seed']) for v in ref.values() for r in v})
    def msd(vals, f):
        v = np.array(vals, float)
        return f'{v.mean():{f}}' + (f' +- {v.std(ddof=1):{f}}' if len(v) > 1 else '')
    rows = []
    say()
    say(f'200 versus {N} nodes: mean +- sample SD, 200 nodes over seeds {S200}, {N} nodes over seeds {SEEDS} (same per-node workload,')
    say('area, BS, radio and routing; residual energy also as % of the initial 2 J x N; runtime and peak memory from different sessions)')
    for s in SCN:
        say(f'  {NAME[s]}')
        for k, h, f in CMPK:
            a200 = [float(r[k]) for r in ref[s]]; aN = [r[k] for r in by[s]]
            say(f'    {h:26s} 200: {msd(a200, f):>20s}   {N}: {msd(aN, f):>20s}')
            rows.append({'scenario': s, 'metric': k, 'nodes_200_seeds': len(a200), 'mean_200': np.mean(a200), 'sd_200': np.std(a200, ddof=1) if len(a200) > 1 else float('nan'),
                         f'nodes_{N}_seeds': len(aN), f'mean_{N}': np.mean(aN), f'sd_{N}': np.std(aN, ddof=1) if len(aN) > 1 else float('nan')})
    write(f'comparison_200_vs_{N}.csv', rows)
say()
say('RESULT: ' + ('all checks passed' if ok else 'FAILURES - see above'))
open(os.path.join(RES, 'environmental_report.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))

# ---------------------------------------------------------------- figures (validated categorical palette, light surface)
COL = dict(zip(SCN, ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']))
TCOL = {'water_quality': COL['water'], 'industrial_effluent': COL['effluent'], 'air_quality': COL['air'], 'soil_monitoring': COL['soil']}
INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': AXIS, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'axes.facecolor': SURF, 'figure.facecolor': SURF, 'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6,
                     'axes.axisbelow': True, 'axes.spines.top': False, 'axes.spines.right': False, 'legend.frameon': False,
                     'axes.titlesize': 11, 'axes.titlecolor': INK})
SD_NOTE = f'mean ± sample SD over run seeds {SEEDS[0]}–{SEEDS[-1]}' if len(SEEDS) > 1 else f'single run seed {SEEDS[0]} (no error bars)'
NOTE = f'{SD_NOTE}; one {N}-node network, only the scenario workload changes'
X = np.arange(len(SCN))


def err(s, k): v = agg[s][k + '_sd']; return 0 if math.isnan(v) else v


def bar1(ax, k, ylabel, title):
    for i, s in enumerate(SCN):
        ax.bar(i, agg[s][k + '_mean'], 0.62, color=COL[s])
        if len(SEEDS) > 1: ax.errorbar(i, agg[s][k + '_mean'], yerr=err(s, k), color=INK, capsize=3, linewidth=1)
    ax.set_xticks(X); ax.set_xticklabels([NAME[s] for s in SCN]); ax.grid(axis='x', visible=False)
    ax.set_ylabel(ylabel); ax.set_title(title, loc='left')


def finish(fig, name, title, note=NOTE):
    fig.suptitle(title if 'versus' in title else f'{title} ({N} nodes)', x=0.01, ha='left', color=INK, fontsize=12)
    fig.text(0.01, 0.01, note, color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(os.path.join(FIG, name), dpi=150)
    plt.close(fig)


fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
bar1(ax[0], 'delivered', 'delivered reports', 'Delivered reports')
for i, s in enumerate(SCN):
    for j, (k, h) in enumerate((('delivery_ratio_pct', None), ('source_packet_pdr_pct', '////'))):
        x = i + (j - 0.5) * 0.4
        ax[1].bar(x, agg[s][k + '_mean'], 0.38, color=COL[s] if h is None else SURF, edgecolor=COL[s], hatch=h, linewidth=1.2)
        if len(SEEDS) > 1: ax[1].errorbar(x, agg[s][k + '_mean'], yerr=err(s, k), color=INK, capsize=3, linewidth=1)
ax[1].set_xticks(X); ax[1].set_xticklabels([NAME[s] for s in SCN]); ax[1].grid(axis='x', visible=False)
ax[1].set_ylabel('%'); ax[1].set_title('Delivery ratio and source-packet PDR', loc='left'); ax[1].set_ylim(0, 62)
ax[1].legend(handles=[Patch(facecolor=MUTED, label='delivered / generated'),
                      Patch(facecolor=SURF, edgecolor=MUTED, hatch='////', label='delivered / emitted by operational sources')], loc='upper right', fontsize=8)
finish(fig, 'fig1_delivery.png', 'Five-scenario delivery comparison')

for name, idx, ylabel, title in (('fig2_operational_nodes.png', 0, 'operational nodes', 'Operational nodes versus round'),
                                 ('fig3_residual_energy.png', 1, f'residual radio energy (J, of {E0 * N:.0f})', 'Residual radio energy versus round')):
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for s in SCN:
        y = np.array([series[(s, sd)][idx] for sd in SEEDS], float)
        mu, r = y.mean(0), np.arange(1, y.shape[1] + 1)
        if len(SEEDS) > 1:
            sdv = y.std(0, ddof=1)
            ax.fill_between(r, mu - sdv, mu + sdv, color=COL[s], alpha=0.18, linewidth=0)
        ax.plot(r, mu, color=COL[s], linewidth=2, label=NAME[s])
    ax.set_xlabel('round (1 round = 1 h)'); ax.set_ylabel(ylabel); ax.set_xlim(1, ROUNDS); ax.legend(loc='lower left', ncol=5 if idx == 0 else 1)
    if idx == 0: ax.set_ylim(0, N * 1.05)
    allup = all(r['alive_r500'] == N for r in runs)
    finish(fig, name, title, ('line = mean over run seeds, band = ± sample SD' if len(SEEDS) > 1 else SD_NOTE) +
           (f'; all {N} nodes stay operational in every run, so the five lines overlap at {N}' if idx == 0 and allup else ''))

fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
bottom = np.zeros(len(SCN))
for k, lab, c in (('tx_J', 'transmission', '#008300'), ('rx_J', 'reception', '#6250d6'), ('aggregation_J', 'aggregation', MUTED)):
    v = np.array([agg[s][k + '_mean'] for s in SCN])
    ax[0].bar(X, v, 0.62, bottom=bottom, color=c, label=lab, edgecolor=SURF, linewidth=1)
    bottom += v
if len(SEEDS) > 1: ax[0].errorbar(X, bottom, yerr=[err(s, 'spent_radio_J') for s in SCN], fmt='none', color=INK, capsize=3, linewidth=1)
ax[0].set_xticks(X); ax[0].set_xticklabels([NAME[s] for s in SCN]); ax[0].grid(axis='x', visible=False)
ax[0].set_ylabel(f'J (network, of {E0 * N:.0f} J)'); ax[0].set_title('Radio energy spent (2 J battery per node)', loc='left'); ax[0].legend(fontsize=8)
bar1(ax[1], 'sensing_kJ_operational', 'kJ (network)', 'Sensing-energy ledger (separate, not on the radio battery)')
for i, s in enumerate(SCN):   # water and soil are invisible at this scale: label every bar
    ax[1].annotate(f'{agg[s]["sensing_kJ_operational_mean"]:,.0f} kJ', (i, agg[s]['sensing_kJ_operational_mean']), xytext=(0, 4),
                   textcoords='offset points', ha='center', fontsize=8, color=INK2)
finish(fig, 'fig4_energy_breakdown.png', 'Radio and sensing energy (different scales)', NOTE)

fig, ax = plt.subplots(figsize=(7.5, 4.2)); bar1(ax, 'energy_per_delivered_mJ', 'mJ', 'Radio energy per delivered report')
finish(fig, 'fig5_energy_per_delivered.png', 'Energy per delivered report')
fig, ax = plt.subplots(figsize=(7.5, 4.2)); bar1(ax, 'mean_delay_ms', 'ms', 'Mean end-to-end delay of delivered reports')
finish(fig, 'fig6_delay.png', 'End-to-end delay')

fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
pay = np.array([agg[s]['mean_payload_bits_mean'] for s in SCN])
ax[0].bar(X, pay, 0.62, color=[COL[s] for s in SCN], edgecolor=SURF, linewidth=1)
ax[0].bar(X, OVH, 0.62, bottom=pay, color=AXIS, edgecolor=SURF, linewidth=1)
ax[0].set_xticks(X); ax[0].set_xticklabels([NAME[s] for s in SCN]); ax[0].grid(axis='x', visible=False)
ax[0].set_ylabel('bits per report'); ax[0].set_title(f'Mean frame = application payload + {OVH}-bit MAC/PHY', loc='left')
ax[0].legend(handles=[Patch(facecolor=MUTED, label='application payload (scenario colour)'), Patch(facecolor=AXIS, label='802.15.4 MAC/PHY overhead')],
             loc='lower right', fontsize=8)
bar1(ax[1], 'transmitted_Mbit', 'Mbit', 'Total transmitted bits (all hops)')
finish(fig, 'fig7_frames_and_traffic.png', 'Frame size and radio traffic')

fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
HATCH = {'real': None, 'replayed': '////', 'synthetic': '....'}
for a, rows, title in ((ax[0], [r for r in cls_agg if r['scenario'] != 'mixed'], 'Single-profile scenarios'),
                       (ax[1], sorted([r for r in cls_agg if r['scenario'] == 'mixed'], key=lambda r: (list(TCOL).index(r['sensor_type']), r['data_class'])),
                        f'Mixed scenario ({N // 4} nodes per profile)')):
    for i, r in enumerate(rows):
        h = HATCH[r['data_class']]
        a.bar(i, r['delivery_ratio_pct_mean'], 0.7, color=TCOL[r['sensor_type']] if h is None else SURF, edgecolor=TCOL[r['sensor_type']], hatch=h, linewidth=1.2)
        if not math.isnan(r['delivery_ratio_pct_sd']):
            a.errorbar(i, r['delivery_ratio_pct_mean'], yerr=r['delivery_ratio_pct_sd'], color=INK, capsize=3, linewidth=1)
    a.set_xticks(range(len(rows))); a.set_xticklabels([f'{r["sensor_type"].split("_")[0]}\n{r["data_class"]}\n({r["nodes_in_class"]} nodes)' for r in rows], fontsize=8)
    a.grid(axis='x', visible=False); a.set_ylabel('delivered / generated (%)'); a.set_title(title, loc='left')
fig.legend(handles=[Patch(facecolor=MUTED, label='real station stream'), Patch(facecolor=SURF, edgecolor=MUTED, hatch='////', label='replayed real stream'),
                    Patch(facecolor=SURF, edgecolor=MUTED, hatch='....', label='synthetic')], loc='upper right', ncol=3, fontsize=8)
finish(fig, 'fig8_data_sources.png', 'Delivery by data source (real / replayed / synthetic)')

def cmp_fig(name, title, panels):
    fig, axs = plt.subplots(1, len(panels), figsize=(3.8 * len(panels), 4.0))
    for a, (k, yl, t) in zip(axs, panels):
        for i, s in enumerate(SCN):
            v2, vN = np.array([float(r[k]) for r in ref[s]]), np.array([r[k] for r in by[s]], float)
            a.bar(i - 0.2, v2.mean(), 0.38, color=COL[s], edgecolor=COL[s], linewidth=1.2)
            a.bar(i + 0.2, vN.mean(), 0.38, color=SURF, edgecolor=COL[s], hatch='////', linewidth=1.2)
            for x, v in ((i - 0.2, v2), (i + 0.2, vN)):
                if len(v) > 1: a.errorbar(x, v.mean(), yerr=v.std(ddof=1), color=INK, capsize=3, linewidth=1)
        a.set_xticks(X); a.set_xticklabels([NAME[s] for s in SCN], fontsize=8); a.grid(axis='x', visible=False); a.set_ylabel(yl); a.set_title(t, loc='left')
    fig.legend(handles=[Patch(facecolor=MUTED, label='200 nodes'), Patch(facecolor=SURF, edgecolor=MUTED, hatch='////', label=f'{N} nodes')],
               loc='upper right', ncol=2, fontsize=9)
    n2 = len(next(iter(ref.values())))
    finish(fig, name, title, f'mean ± sample SD: 200 nodes over {n2} seeds, {N} nodes over {len(SEEDS)} seeds; same area, BS, radio, routing and per-node workload')


if ref:
    cmp_fig('fig9_200_vs_500.png', f'200 versus {N} nodes: performance',
            [('delivery_ratio_pct', '%', 'Delivery ratio'), ('residual_pct_of_initial', '% of initial', 'Residual radio energy'),
             ('energy_per_delivered_mJ', 'mJ', 'Energy per delivered report'), ('mean_delay_ms', 'ms', 'Mean delay')])
    cmp_fig('fig10_200_vs_500_cost.png', f'200 versus {N} nodes: traffic and cost',
            [('transmitted_Mbit', 'Mbit', 'Total transmitted bits'), ('runtime_s', 's', 'Runtime per run'), ('peak_memory_MB', 'MB', 'Peak memory')])
print('figures written to', FIG)
sys.exit(0 if ok else 1)
