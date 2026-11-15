"""Mode 2 (sensor-realistic) screening table, seed 42: M2T (4000-bit packet) and M2F (per-report profile frames).

Usage (from RLHybrid_Scalability_Experiment):  python -P tools/compare_mode2.py
Reads results_multi_scenario/mode2_realistic/{traffic_4000bit,frame_802154}/ and runtimes.csv; writes
mode2_comparison.csv, mode2_by_data_class.csv and mode2_comparison.txt there. Exit 1 if a check fails.
"""
import csv, json, os, re, sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
M2 = os.path.join(ROOT, 'results_multi_scenario', 'mode2_realistic')
SC = os.path.join(ROOT, 'data', 'scenarios')
P = json.load(open(os.path.join(ROOT, 'scenario_study', 'dataset_metadata', 'sensor_profiles.json')))
SCN = {'Water': 'water_quality', 'Effluent': 'industrial_effluent', 'Air': 'air_quality', 'Soil': 'soil_monitoring', 'Mixed': None}
MODES = {'M2T': 'traffic_4000bit', 'M2F': 'frame_802154'}
out, ok = [], True


def say(s=''): out.append(s)


def check(cond, what):
    global ok
    ok &= bool(cond)
    say(f'  [{"OK" if cond else "FAIL"}] {what}')


# node -> (sensor type, data class) for every scenario
node_map = {int(r['node_id']): r['sensor_type'] for r in csv.DictReader(open(os.path.join(SC, 'mixed_environment_200', 'node_map.csv'), newline=''))}
klass = {}
for t in [v for v in SCN.values() if v]:
    with open(os.path.join(SC, t + '_200', 'observations.csv'), newline='') as fh:
        for w in csv.DictReader(fh):
            if w['round'] == '1':
                klass[(t, int(w['node_id']))] = 'synthetic' if w['is_synthetic'] == '1' else ('replayed' if w['is_replayed'] == '1' else 'real')
def node_info(s, nd):
    t = SCN[s] or node_map[nd]
    return t, klass[(t, nd)]

# expected frame bits from the profile definitions: 8 x (MAC/PHY + app header + 2 B per field)
fr = P['frame']
def frame_bits(n): return 8 * (fr['mac_phy_overhead_bytes'] + fr['app_header_bytes'] + fr['field_bytes'] * n)
expect = {}
for t, prof in P['profiles'].items():
    expect[t] = frame_bits(len([f for f in prof['fields'] if not f.get('chem')]))
    if any(f.get('chem') for f in prof['fields']):
        expect[t + '+chem'] = frame_bits(len(prof['fields']))
runtime = {r['config']: float(r['runtime_s']) for r in csv.DictReader(open(os.path.join(M2, 'runtimes.csv'), newline=''))}

say('MODE 2 screening, seed 42: 200 nodes, 500 rounds (1 round = 1 h), variant C (energyGuard 0.8), retransmission off,')
say('same topology / BS / first-order radio / 2 J radio battery. Sensing energy is a separate ledger, never charged to the 2 J.')
say('M2T keeps the 4000-bit MATLAB packet abstraction; M2F charges every report its own profile frame. Neither is MATLAB-equivalent.')
say('=' * 120)
say('Frame sizes from sensor_profiles.json (8 x (17 B MAC/PHY + 10 B header + 2 B x fields)): '
    + ', '.join(f'{k} {v}' for k, v in expect.items()))
check(expect == {'water_quality': 280, 'industrial_effluent': 360, 'air_quality': 360, 'soil_monitoring': 264, 'soil_monitoring+chem': 328},
      'profile definitions give water 280, effluent 360, air 360, soil 264 / 328 (chemistry) bit')

rows, cls_rows = [], []
for m, sub in MODES.items():
    for s in SCN:
        cfg = f'{m}_{s}'
        pre = os.path.join(M2, sub, f'{cfg}-seed42-')
        mt = dict(zip(*list(csv.reader(open(pre + 'metrics.csv', newline='')))))
        summ = open(pre + 'summary.txt').read()
        tr = re.search(r'radio traffic\s*: ([\d.]+) Mbit on air in (\d+) report transmissions \(mean ([\d.]+) bit\); mean generated frame ([\d.]+) bit', summ)
        led = list(csv.DictReader(open(pre + 'sensing_ledger.csv', newline='')))
        wl = list(csv.DictReader(open(pre + 'workload.csv', newline='')))
        if m == 'M2F':                                   # every report's frame bits against the profile definition
            bad = 0
            for w in wl:
                t, _ = node_info(s, int(w['sourceNode']))
                bad += int(w['frameBits']) not in (expect[t], expect.get(t + '+chem', -1))
            check(bad == 0, f'{cfg}: all {len(wl)} reports carry their own profile frame bits')
        gen, dlv, emi = int(mt['workloadAvailable']), int(mt['delivered']), int(mt['sourceAvailable'])
        row = {'config': cfg, 'mode': m, 'scenario': s, 'scheduled': int(mt['scheduled']), 'generated': gen,
               'emitted': emi, 'delivered': dlv,
               'delivered_per_generated_pct': 100 * dlv / gen, 'delivered_per_scheduled_pct': float(mt['PDR']),
               'source_packet_pdr_pct': 100 * dlv / emi, 'operational_nodes_r500': int(mt['finalAlive']),
               'FND_round': int(mt['FND']), 'residual_radio_J': float(mt['residualJ']), 'spent_radio_J': float(mt['spentJ']),
               'energy_per_delivered_mJ': 1000 * float(mt['energyPerDeliveredJ']), 'mean_delay_ms': 1000 * float(mt['meanDelayS']),
               'mean_hops': float(mt['meanHops']), 'mean_generated_frame_bits': float(tr.group(4)),
               'mean_bits_per_report_tx': float(tr.group(3)), 'report_transmissions': int(tr.group(2)),
               'radio_traffic_Mbit': float(tr.group(1)),
               'sensing_ledger_kJ_operational': sum(float(x['sensingJ_operational']) for x in led) / 1000,
               'runtime_s': runtime[cfg]}
        rows.append(row)
        # data-class split (real station streams / replayed virtual sensors / synthetic)
        c = defaultdict(lambda: {'gen': 0, 'dlv': 0, 'delay': 0.0, 'nodes': set(), 'ledJ': 0.0})
        for x in led:
            t, k = node_info(s, int(x['node']))
            c[(t, k)]['nodes'].add(int(x['node'])); c[(t, k)]['ledJ'] += float(x['sensingJ_operational'])
        for r in csv.DictReader(open(pre + 'reports.csv', newline='')):
            t, k = node_info(s, int(r['sourceNode']))
            e = c[(t, k)]
            e['gen'] += 1
            if r['fate'] == 'delivered':
                e['dlv'] += 1; e['delay'] += float(r['pathDelayS'])
        for (t, k), e in sorted(c.items()):
            cls_rows.append({'config': cfg, 'sensor_type': t, 'data_class': k, 'nodes': len(e['nodes']), 'generated': e['gen'],
                             'delivered': e['dlv'], 'delivered_per_generated_pct': 100 * e['dlv'] / e['gen'] if e['gen'] else float('nan'),
                             'mean_delay_ms': 1000 * e['delay'] / e['dlv'] if e['dlv'] else float('nan'),
                             'sensing_ledger_kJ_operational': e['ledJ'] / 1000})
        check(sum(x['generated'] for x in cls_rows if x['config'] == cfg) == gen, f'{cfg}: class split covers all {gen} generated reports')

for name, data in (('mode2_comparison.csv', rows), ('mode2_by_data_class.csv', cls_rows)):
    with open(os.path.join(M2, name), 'w', newline='') as fo:
        w = csv.DictWriter(fo, fieldnames=list(data[0]))
        w.writeheader()
        for r in data:
            w.writerow({k: (f'{v:.4f}' if isinstance(v, float) else v) for k, v in r.items()})

say()
hd = (f'{"config":13s} {"sched":>6s} {"gener":>6s} {"deliv":>6s} {"d/gen%":>6s} {"d/sch%":>6s} {"srcPDR%":>7s} {"oper":>4s} {"FND":>4s} '
      f'{"resid J":>8s} {"mJ/dlv":>7s} {"delay ms":>8s} {"frame b":>7s} {"traffic Mbit":>12s} {"sensing kJ":>10s} {"run s":>5s}')
for m in MODES:
    say(hd)
    for r in [x for x in rows if x['mode'] == m]:
        say(f'{r["config"]:13s} {r["scheduled"]:6d} {r["generated"]:6d} {r["delivered"]:6d} {r["delivered_per_generated_pct"]:6.2f} '
            f'{r["delivered_per_scheduled_pct"]:6.2f} {r["source_packet_pdr_pct"]:7.2f} {r["operational_nodes_r500"]:4d} {r["FND_round"]:4d} '
            f'{r["residual_radio_J"]:8.2f} {r["energy_per_delivered_mJ"]:7.3f} {r["mean_delay_ms"]:8.2f} {r["mean_generated_frame_bits"]:7.1f} '
            f'{r["radio_traffic_Mbit"]:12.1f} {r["sensing_ledger_kJ_operational"]:10.1f} {r["runtime_s"]:5.1f}')
    say()
say('d/gen = delivered / generated; d/sch = delivered / scheduled (MATLAB PDR; Mode 2 slots = generated reports, so equal);')
say('srcPDR = delivered / reports emitted by sources operational at round start; oper = operational nodes after round 500;')
say('FND = first round with a node down (-1 = none); traffic = bits on air over all hops (report-preserving); sensing = ledger')
say('of operational node-rounds (kJ). Mode 1 reference (every scenario): 96,500 generated, 33,846 delivered, FND 250, 107 operational.')
say()
say('By data class (real station streams / replayed virtual sensors / synthetic)')
say(f'{"config":13s} {"sensor type":20s} {"class":9s} {"nodes":>5s} {"gener":>6s} {"deliv":>6s} {"d/gen%":>7s} {"delay ms":>8s} {"sensing kJ":>10s}')
for r in cls_rows:
    say(f'{r["config"]:13s} {r["sensor_type"]:20s} {r["data_class"]:9s} {r["nodes"]:5d} {r["generated"]:6d} {r["delivered"]:6d} '
        f'{r["delivered_per_generated_pct"]:7.2f} {r["mean_delay_ms"]:8.2f} {r["sensing_ledger_kJ_operational"]:10.2f}')
say()
say('RESULT: ' + ('all checks passed' if ok else 'FAILURES - see above'))
open(os.path.join(M2, 'mode2_comparison.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
sys.exit(0 if ok else 1)
