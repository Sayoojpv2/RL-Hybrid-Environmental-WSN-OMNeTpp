"""Mode 2 five-seed validation (run seeds 42-46): checks, per-run metrics, mean +- sample SD, Welch comparisons, figures.

Usage (from RLHybrid_Scalability_Experiment):  python -P tools/five_seed_mode2.py
Seed 42 = the existing results_multi_scenario/mode2_realistic/{traffic_4000bit,frame_802154}/<cfg>-seed42-* outputs;
seeds 43-46 = results_multi_scenario/mode2_realistic/five_seed/<same sub>/<cfg>_5S-seed<s>-*.
Writes five_seed/: per_run.csv, per_run_by_data_class.csv, summary_mean_sd.csv, by_data_class_mean_sd.csv,
comparisons.csv, five_seed_report.txt and figures/*.png. Exit 1 if a check fails.
"""
import csv, hashlib, json, math, os, re, sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
M2 = os.path.join(ROOT, 'results_multi_scenario', 'mode2_realistic')
FS = os.path.join(M2, 'five_seed')
FIG = os.path.join(FS, 'figures')
SC = os.path.join(ROOT, 'data', 'scenarios')
SCN = ['Water', 'Effluent', 'Air', 'Soil', 'Mixed']
TYPE = {'Water': 'water_quality', 'Effluent': 'industrial_effluent', 'Air': 'air_quality', 'Soil': 'soil_monitoring', 'Mixed': None}
MODES = {'M2T': 'traffic_4000bit', 'M2F': 'frame_802154'}
SEEDS = [42, 43, 44, 45, 46]
N, ROUNDS = 200, 500
EELEC, EMP, EFS, EDA, RBIT = 50e-9, 0.0013e-12, 10e-12, 5e-9, 250e3
D0 = math.sqrt(EFS / EMP)
# controller parameters allowed to differ from the seed-42 run: the run seed and the seed design of seeds 43-46
SEED_PARS = {'scenarioSeed', 'topologySeed', 'extraTopologySeed', 'channelStream', 'outputPrefix'}
out, ok = [], True


def say(s=''): out.append(s)


def check(cond, what):
    global ok
    ok &= bool(cond)
    say(f'  [{"OK" if cond else "FAIL"}] {what}')


# ---------------------------------------------------------------- Welch t-test without scipy (incomplete beta, NR 6.4)
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


assert abs(t_two_sided(2.776445, 4) - 0.05) < 1e-5 and abs(t_two_sided(2.228139, 10) - 0.05) < 1e-5
assert abs(t_two_sided(4.604095, 4) - 0.01) < 1e-5 and t_two_sided(0.0, 5) == 1.0


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    if va + vb == 0: return float('nan'), float('nan')          # no seed variance in either group
    t = (b.mean() - a.mean()) / math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    return t, t_two_sided(abs(t), df)


def tx(k, d): return k * (EELEC + (EFS * d * d if d < D0 else EMP * d ** 4))


# ---------------------------------------------------------------- node classes, frame definitions, provenance
node_map = {int(r['node_id']): r['sensor_type'] for r in csv.DictReader(open(os.path.join(SC, 'mixed_environment_200', 'node_map.csv'), newline=''))}
klass = {}
for t in [v for v in TYPE.values() if v]:
    with open(os.path.join(SC, t + '_200', 'observations.csv'), newline='') as fh:
        for w in csv.DictReader(fh):
            if w['round'] == '1':
                klass[(t, int(w['node_id']))] = 'synthetic' if w['is_synthetic'] == '1' else ('replayed' if w['is_replayed'] == '1' else 'real')


def node_info(s, nd):
    t = TYPE[s] or node_map[nd]
    return t, klass[(t, nd)]


def md5(p): return hashlib.md5(open(p, 'rb').read()).hexdigest()


say('MODE 2 FIVE-SEED VALIDATION: 200 nodes, 500 rounds (1 round = 1 h), variant C (energyGuard 0.8), retransmission off,')
say('seed-42 topology for every run seed, same BS / datasets / schedules / first-order radio / 2 J radio battery.')
say('Run seeds 42-46 drive the channel and the RL agent stream. Sensing energy is a separate ledger, never charged to the 2 J.')
say('M2T keeps the 4000-bit MATLAB packet; M2F charges every report its own profile frame. Neither is MATLAB-equivalent.')
say('=' * 118)
say('Provenance and configuration checks')
DATA_MD5 = {'water_quality_200/observations.csv': '45037423', 'industrial_effluent_200/observations.csv': 'b4b5327b',
            'air_quality_200/observations.csv': '6f2b95b6', 'soil_monitoring_200/observations.csv': '8787ec59',
            'mixed_environment_200/node_map.csv': 'f1ca07b9'}
for f, h in DATA_MD5.items():
    check(md5(os.path.join(SC, f)).startswith(h), f'dataset {f} unchanged (md5 {h}...)')
prov = {f: md5(os.path.join(ROOT, f)) for f in sorted(os.listdir(ROOT))
        if f.endswith(('.cc', '.h', '.ned', '.msg')) or f in ('omnetpp.ini', 'RLHybrid_Scalability_Experiment.exe')}


def files(m, s, seed):
    d = os.path.join(M2, MODES[m]) if seed == 42 else os.path.join(FS, MODES[m])
    c = f'{m}_{s}' if seed == 42 else f'{m}_{s}_5S'
    sca = os.path.join(d, f'{c}-seed=42-#0.sca' if seed == 42 else f'{c}-seed{seed}.sca')
    return os.path.join(d, f'{c}-seed{seed}-'), sca, c


def sca_read(p):
    pars, node_res = {}, {}
    for ln in open(p):
        if ln.startswith('par '):
            mod, name, val = ln.split(' ', 3)[1:]
            pars[(mod, name)] = val.strip()
        elif ln.startswith('scalar '):
            g = re.match(r'scalar PeriyarRiverNetwork\.node\[(\d+)\] residualEnergy (\S+)', ln)
            if g: node_res[int(g.group(1))] = float(g.group(2))
    return pars, node_res


# seed 42 re-timed in the same session as seeds 43-46 (outputs byte-identical, discarded); the screening runtimes.csv
# was measured on a less loaded machine and is not comparable
runtime = {(r['config'], 42): float(r['runtime_s']) for r in csv.DictReader(open(os.path.join(FS, 'runtimes_seed42_retimed.csv'), newline=''))}
runtime.update({(r['config'].replace('_5S', ''), int(r['seed'])): float(r['runtime_s'])
                for r in csv.DictReader(open(os.path.join(FS, 'runtimes.csv'), newline=''))})

# ---------------------------------------------------------------- per-run metrics
runs, cls_runs, series, minres, bad_cfg = [], [], {}, {}, []
for m in MODES:
    for s in SCN:
        cfg = f'{m}_{s}'
        p42, sca42, _ = files(m, s, 42)
        pars42, _ = sca_read(sca42)
        for seed in SEEDS:
            pre, sca, cname = files(m, s, seed)
            pars, node_res = sca_read(sca)
            # configuration: every recorded parameter equals the seed-42 run except the seed design
            diff = {k for k in set(pars) | set(pars42) if pars.get(k) != pars42.get(k)}
            diff_names = {k[1] for k in diff}
            exp_seed = {'scenarioSeed': str(seed), 'topologySeed': '-1' if seed == 42 else '42',
                        'extraTopologySeed': '-1' if seed == 42 else '900042',
                        'channelStream': '"\\"matlab\\""' if seed == 42 else '"\\"independent\\""'}   # .sca string format
            ctl = 'PeriyarRiverNetwork.controller'
            if not (diff_names <= SEED_PARS and all(pars[(ctl, k)] == v for k, v in exp_seed.items())
                    and len(node_res) == N and pars[(ctl, 'energyGuard')] == '0.8' and pars[(ctl, 'numRounds')] == '500'
                    and pars[(ctl, 'enableRetransmission')] == 'false'):
                bad_cfg.append(f'{cname} seed {seed}: {sorted(diff_names - SEED_PARS)}')
            if seed != 42:   # same topology and same report schedule (incl. frame bits) as seed 42
                for f in ('nodes.csv', 'workload.csv'):
                    if open(pre + f, 'rb').read() != open(p42 + f, 'rb').read(): bad_cfg.append(f'{cname} seed {seed}: {f} differs')
            mt = dict(zip(*list(csv.reader(open(pre + 'metrics.csv', newline='')))))
            summ = open(pre + 'summary.txt').read()
            if 'energy closes OK; slot accounting OK; per-round MATLAB invariants OK' not in summ:
                bad_cfg.append(f'{cname} seed {seed}: run checks missing')
            tr = re.search(r'radio traffic\s*: ([\d.]+) Mbit on air in (\d+) report transmissions \(mean ([\d.]+) bit\); mean generated frame ([\d.]+) bit', summ)
            led = list(csv.DictReader(open(pre + 'sensing_ledger.csv', newline='')))
            pr = list(csv.DictReader(open(pre + 'per_round.csv', newline='')))
            series[(cfg, seed)] = (np.array([int(r['aliveCount']) for r in pr]), np.array([float(r['residualJ']) for r in pr]))
            minres[(cfg, seed)] = min(node_res.values())
            gen, dlv, emi = int(mt['workloadAvailable']), int(mt['delivered']), int(mt['sourceAvailable'])
            nr = sum(int(x['operationalRounds']) for x in led)
            fnd = int(mt['FND'])
            runs.append({'config': cfg, 'mode': m, 'scenario': s, 'seed': seed,
                         'scheduled': int(mt['scheduled']), 'generated': gen, 'emitted': emi, 'delivered': dlv,
                         'delivered_per_generated_pct': 100 * dlv / gen, 'delivered_per_scheduled_pct': 100 * dlv / int(mt['scheduled']),
                         'source_packet_pdr_pct': 100 * dlv / emi, 'FND_round': fnd if fnd > 0 else float('nan'),
                         'alive_r500': int(mt['finalAlive']), 'operational_node_rounds': nr,
                         'availability_pct': 100 * nr / (N * ROUNDS), 'residual_radio_J': float(mt['residualJ']),
                         'spent_radio_J': float(mt['spentJ']), 'min_node_residual_J': minres[(cfg, seed)],
                         'energy_per_delivered_mJ': 1000 * float(mt['spentJ']) / dlv,
                         'mean_delay_ms': 1000 * float(mt['meanDelayS']), 'mean_hops': float(mt['meanHops']),
                         'mean_generated_frame_bits': float(tr.group(4)), 'report_transmissions': int(tr.group(2)),
                         'radio_traffic_Mbit': float(tr.group(1)),
                         'sensing_ledger_kJ_operational': sum(float(x['sensingJ_operational']) for x in led) / 1000,
                         'sensing_ledger_kJ_all_rounds': sum(float(x['sensingJ_allRounds']) for x in led) / 1000,
                         'runtime_s': runtime[(cfg, seed)]})
            if abs(1000 * float(mt['energyPerDeliveredJ']) - runs[-1]['energy_per_delivered_mJ']) > 1e-6:
                bad_cfg.append(f'{cname} seed {seed}: energy per delivered != spent / delivered')
            c = defaultdict(lambda: [0, 0])
            for r in csv.DictReader(open(pre + 'reports.csv', newline='')):
                e = c[node_info(s, int(r['sourceNode']))]
                e[0] += 1; e[1] += r['fate'] == 'delivered'
            if sum(v[0] for v in c.values()) != gen: bad_cfg.append(f'{cname} seed {seed}: class split incomplete')
            for (t, k), (g, d) in sorted(c.items()):
                cls_runs.append({'config': cfg, 'seed': seed, 'sensor_type': t, 'data_class': k, 'generated': g,
                                 'delivered': d, 'delivered_per_generated_pct': 100 * d / g})
check(not bad_cfg, f'{len(runs)} runs: every recorded parameter equals the seed-42 run except scenarioSeed / topologySeed / '
      'extraTopologySeed / channelStream / outputPrefix; seeds 43-46 = topologySeed 42, extraTopologySeed 900042 (the seed-42 '
      'defaults), independent channel; nodes.csv and workload.csv byte-identical to seed 42; run invariants OK')
for b in bad_cfg: say('      ' + b)
check(len({(r['config'], r['generated'], r['scheduled']) for r in runs}) == 10, 'scheduled and generated reports identical across seeds (fixed schedule)')

# ---------------------------------------------------------------- aggregation
MET = ['scheduled', 'generated', 'delivered', 'delivered_per_generated_pct', 'delivered_per_scheduled_pct', 'source_packet_pdr_pct',
       'FND_round', 'alive_r500', 'operational_node_rounds', 'availability_pct', 'residual_radio_J', 'spent_radio_J',
       'min_node_residual_J', 'energy_per_delivered_mJ', 'mean_delay_ms', 'mean_hops', 'mean_generated_frame_bits',
       'radio_traffic_Mbit', 'sensing_ledger_kJ_operational', 'sensing_ledger_kJ_all_rounds', 'runtime_s']
by = defaultdict(list)
for r in runs: by[r['config']].append(r)
agg = {}
for cfg, rs in by.items():
    a = {'config': cfg, 'mode': rs[0]['mode'], 'scenario': rs[0]['scenario'], 'seeds': len(rs)}
    for k in MET:
        v = np.array([r[k] for r in rs], float)
        f = v[~np.isnan(v)]
        a[k + '_mean'] = f.mean() if len(f) else float('nan')
        a[k + '_sd'] = f.std(ddof=1) if len(f) > 1 else float('nan')
        if k == 'FND_round': a['FND_seeds_with_failure'] = len(f)
    agg[cfg] = a
cls_by = defaultdict(list)
for r in cls_runs: cls_by[(r['config'], r['sensor_type'], r['data_class'])].append(r)
cls_agg = [{'config': k[0], 'sensor_type': k[1], 'data_class': k[2], 'generated': v[0]['generated'],
            'delivered_mean': np.mean([x['delivered'] for x in v]),
            'delivered_per_generated_pct_mean': np.mean([x['delivered_per_generated_pct'] for x in v]),
            'delivered_per_generated_pct_sd': np.std([x['delivered_per_generated_pct'] for x in v], ddof=1)}
           for k, v in cls_by.items()]

# ---------------------------------------------------------------- comparisons (Welch, two-sided, Holm over the whole table)
CMP_MET = ['delivered_per_generated_pct', 'source_packet_pdr_pct', 'alive_r500', 'operational_node_rounds', 'residual_radio_J',
           'energy_per_delivered_mJ', 'mean_delay_ms', 'radio_traffic_Mbit']
pairs = []
for m in MODES:
    pairs += [(f'{m}_Water', f'{m}_{b}') for b in ('Effluent', 'Air', 'Soil')]
    pairs += [(f'{m}_{b}', f'{m}_Mixed') for b in ('Water', 'Effluent', 'Air', 'Soil')]
pairs += [(f'M2T_{s}', f'M2F_{s}') for s in SCN]
cmp_rows = []
for a, b in pairs:
    for k in CMP_MET:
        va, vb = [r[k] for r in by[a]], [r[k] for r in by[b]]
        t, p = welch(va, vb)
        cmp_rows.append({'A': a, 'B': b, 'metric': k, 'mean_A': np.mean(va), 'sd_A': np.std(va, ddof=1), 'mean_B': np.mean(vb),
                         'sd_B': np.std(vb, ddof=1), 'diff_B_minus_A': np.mean(vb) - np.mean(va),
                         'diff_pct_of_A': 100 * (np.mean(vb) - np.mean(va)) / np.mean(va) if np.mean(va) else float('nan'),
                         'welch_t': t, 'p': p})
tested = sorted([r for r in cmp_rows if not math.isnan(r['p'])], key=lambda r: r['p'])
run_max = 0.0
for i, r in enumerate(tested):                     # Holm step-down, monotone
    run_max = max(run_max, min(1.0, (len(tested) - i) * r['p']))
    r['p_holm'] = run_max
for r in cmp_rows:
    r.setdefault('p_holm', float('nan'))
    r['significant_holm_0.05'] = ('n/a (no seed variance)' if math.isnan(r['p']) else ('yes' if r['p_holm'] < 0.05 else 'no'))

# ---------------------------------------------------------------- M2F one-packet feasibility: can the definition matter?
pos = np.array([[float(r['x']), float(r['y'])] for r in csv.DictReader(open(files('M2F', 'Mixed', 42)[0] + 'nodes.csv', newline=''))])
bs = np.array([float(v) for v in re.search(r'BS \(([\d.]+), ([\d.]+)\)', open(files('M2F', 'Mixed', 42)[0] + 'summary.txt').read()).groups()])
dmax = max(np.sqrt(((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1)).max(), np.sqrt(((pos - bs) ** 2).sum(-1)).max())
max_round_reports = max(int(r['scheduled']) for c in ('M2F_Mixed', 'M2F_Soil', 'M2F_Effluent', 'M2F_Air', 'M2F_Water')
                        for r in csv.DictReader(open(files('M2F', c[4:], 42)[0] + 'per_round.csv', newline='')))
thr_tx = tx(360, dmax)                               # largest one-packet sender threshold any report size could give
thr_rx = EELEC * 360 + EDA * 360 * max_round_reports  # one-packet RX + aggregation of every report of a round
m2f_min = min(v for (c, _), v in minres.items() if c.startswith('M2F'))
check(m2f_min > max(thr_tx, thr_rx), f'M2F: lowest node residual energy in any run {m2f_min:.3f} J > largest possible one-packet '
      f'threshold {max(thr_tx, thr_rx) * 1000:.1f} mJ (TX 360 bit over {dmax:.0f} m; RX + aggregation of {max_round_reports} reports)')

# ---------------------------------------------------------------- files
os.makedirs(FIG, exist_ok=True)


def write(name, data):
    with open(os.path.join(FS, name), 'w', newline='') as fo:
        w = csv.DictWriter(fo, fieldnames=list(data[0]))
        w.writeheader()
        for r in data: w.writerow({k: (f'{v:.6g}' if isinstance(v, (float, np.floating)) else v) for k, v in r.items()})


write('per_run.csv', runs)
write('per_run_by_data_class.csv', cls_runs)
write('summary_mean_sd.csv', list(agg.values()))
write('by_data_class_mean_sd.csv', cls_agg)
write('comparisons.csv', cmp_rows)
json.dump({'source_md5': prov, 'note': 'md5 at analysis time; seed-42 outputs reproduced byte for byte with these sources'},
          open(os.path.join(FS, 'provenance.json'), 'w'), indent=1)


# ---------------------------------------------------------------- report tables
def ms(cfg, k, f='.2f'):
    a = agg[cfg]
    if k == 'FND_round':
        return 'none' if a['FND_seeds_with_failure'] == 0 else f"{a[k + '_mean']:.0f}+-{a[k + '_sd']:.0f}"
    return f"{a[k + '_mean']:{f}}+-{a[k + '_sd']:{f}}"


say()
say('Five-seed results (mean +- sample SD over seeds 42-46; scheduled = generated in Mode 2, identical in every seed)')
hd = (f'{"config":13s} {"generated":>9s} {"delivered":>14s} {"d/gen %":>12s} {"srcPDR %":>12s} {"FND":>9s} {"alive500":>11s} '
      f'{"node-rounds":>15s} {"resid J":>13s} {"mJ/dlv":>13s} {"delay ms":>12s} {"traffic Mbit":>14s} {"sense kJ":>14s} {"run s":>9s}')
for m in MODES:
    say(hd)
    for s in SCN:
        c = f'{m}_{s}'
        say(f'{c:13s} {agg[c]["generated_mean"]:9.0f} {ms(c, "delivered", ".0f"):>14s} {ms(c, "delivered_per_generated_pct"):>12s} '
            f'{ms(c, "source_packet_pdr_pct"):>12s} {ms(c, "FND_round"):>9s} {ms(c, "alive_r500", ".1f"):>11s} '
            f'{ms(c, "operational_node_rounds", ".0f"):>15s} {ms(c, "residual_radio_J", ".1f"):>13s} {ms(c, "energy_per_delivered_mJ", ".3f"):>13s} '
            f'{ms(c, "mean_delay_ms"):>12s} {ms(c, "radio_traffic_Mbit", ".1f"):>14s} {ms(c, "sensing_ledger_kJ_operational", ".0f"):>14s} '
            f'{ms(c, "runtime_s", ".1f"):>9s}')
    say()
say('d/gen = delivered / generated (= delivered / scheduled, the MATLAB PDR); srcPDR = delivered / reports emitted by sources')
say('operational at round start; FND = first round with a node down, mean over seeds that had one ("none" = no seed);')
say('node-rounds = cumulative operational node-rounds (sensing-ledger count, max 100,000); mJ/dlv = radio energy spent /')
say('delivered; traffic = bits on air over all hops; sense kJ = sensing ledger over operational node-rounds (not on the 2 J).')
say()
say('Workload drivers (identical in every seed)')
say(f'{"config":13s} {"reports":>8s} {"rep/node-h":>10s} {"frame bit":>9s} {"offered Mbit":>12s} {"spent J":>12s} {"FND":>9s}')
for m in MODES:
    for s in SCN:
        c = f'{m}_{s}'
        say(f'{c:13s} {agg[c]["generated_mean"]:8.0f} {agg[c]["generated_mean"] / (N * ROUNDS):10.3f} {agg[c]["mean_generated_frame_bits_mean"]:9.1f} '
            f'{agg[c]["generated_mean"] * agg[c]["mean_generated_frame_bits_mean"] / 1e6:12.1f} {ms(c, "spent_radio_J", ".1f"):>12s} {ms(c, "FND_round"):>9s}')
say()
say('Delivered / generated by data class (mean +- SD %; routing never reads measurement values)')
for r in cls_agg:
    say(f'  {r["config"]:13s} {r["sensor_type"]:20s} {r["data_class"]:9s} generated {r["generated"]:6d}  '
        f'{r["delivered_per_generated_pct_mean"]:6.2f} +- {r["delivered_per_generated_pct_sd"]:.2f}')
say()
say(f'Comparisons: Welch two-sided t-test, n = 5 + 5, Holm-adjusted over all {len(tested)} tests of this table')
NAMES = {'delivered_per_generated_pct': 'd/gen %', 'source_packet_pdr_pct': 'srcPDR %', 'alive_r500': 'alive500',
         'operational_node_rounds': 'node-rounds', 'residual_radio_J': 'resid J', 'energy_per_delivered_mJ': 'mJ/dlv',
         'mean_delay_ms': 'delay ms', 'radio_traffic_Mbit': 'traffic Mbit'}
say(f'{"A":13s} {"B":13s} {"metric":12s} {"mean A":>10s} {"mean B":>10s} {"B-A":>10s} {"B-A %":>8s} {"p":>9s} {"p Holm":>9s}  sig')
for r in cmp_rows:
    say(f'{r["A"]:13s} {r["B"]:13s} {NAMES[r["metric"]]:12s} {r["mean_A"]:10.3f} {r["mean_B"]:10.3f} {r["diff_B_minus_A"]:10.3f} '
        f'{r["diff_pct_of_A"]:8.1f} {r["p"]:9.2g} {r["p_holm"]:9.2g}  {r["significant_holm_0.05"]}')
say()
mh = max(agg[c]['mean_hops_mean'] for c in ('M2F_Mixed', 'M2F_Soil'))
say('Mixed / soil M2F modelling note: every report is charged its own frame bits (TX, RX, aggregation, reward energy). The')
say('one-packet admission checks inherited from MATLAB (routeCandidates sender TX and receiver RX, cheapestAllowedTx, and the')
say('minimum-energy rule) use one report of the frame = frame bits / reports (smallest frame for the minimum-energy rule).')
say(f'They bind only below {max(thr_tx, thr_rx) * 1000:.1f} mJ; the lowest node energy in any M2F run was {m2f_min:.3f} J, so no')
say('choice of single-report size (mean, smallest, largest) can change any decision in these runs. Per-hop airtime uses the same')
say(f'one-report size: bound on its effect (360 - 264) / 250 kbit/s x {mh:.2f} mean hops = {96 / RBIT * mh * 1000:.2f} ms of the mean delay.')
say()
say('RESULT: ' + ('all checks passed' if ok else 'FAILURES - see above'))
open(os.path.join(FS, 'five_seed_report.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))

# ---------------------------------------------------------------- figures (validated categorical palette slots 1-5, light surface)
COL = dict(zip(SCN, ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']))
INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': AXIS, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'axes.facecolor': SURF, 'figure.facecolor': SURF, 'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6,
                     'axes.axisbelow': True, 'axes.spines.top': False, 'axes.spines.right': False, 'legend.frameon': False,
                     'axes.titlesize': 11, 'axes.titlecolor': INK})
NOTE = 'mean ± sample SD over run seeds 42–46; solid = M2T (4000-bit packet), hatched = M2F (profile frames)'


def bars(ax, k, ylabel, title, modes=('M2T', 'M2F')):
    w = 0.38 if len(modes) == 2 else 0.6
    for i, s in enumerate(SCN):
        for j, m in enumerate(modes):
            c = f'{m}_{s}'
            x = i + (j - (len(modes) - 1) / 2) * (w + 0.02)
            mu, sd = agg[c][k + '_mean'], agg[c][k + '_sd']
            ax.bar(x, mu, w, color=COL[s] if m == 'M2T' else SURF, edgecolor=COL[s], hatch=None if m == 'M2T' else '////', linewidth=1.2)
            ax.errorbar(x, mu, yerr=sd, color=INK, capsize=3, linewidth=1, capthick=1)
    ax.set_xticks(range(len(SCN))); ax.set_xticklabels(SCN); ax.grid(axis='x', visible=False)
    ax.set_ylabel(ylabel); ax.set_title(title, loc='left')


def mode_legend(fig):
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(facecolor=MUTED, edgecolor=MUTED, label='M2T: 4000-bit packet'),
                        Patch(facecolor=SURF, edgecolor=MUTED, hatch='////', label='M2F: profile frames')],
               loc='upper right', ncol=2, fontsize=9)


def save(fig, name, note=NOTE):
    fig.text(0.01, 0.01, note, color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(os.path.join(FIG, name), dpi=150)
    plt.close(fig)


fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
bars(ax[0], 'delivered', 'delivered reports', 'Delivered reports')
bars(ax[1], 'delivered_per_generated_pct', 'delivered / generated (%)', 'Delivered / generated reports')
fig.suptitle('Five-scenario delivery comparison', x=0.01, ha='left', color=INK, fontsize=12); mode_legend(fig)
save(fig, 'fig1_delivery.png')

fig, ax = plt.subplots(figsize=(7.5, 4.2))
bars(ax, 'source_packet_pdr_pct', 'source-packet PDR (%)', 'Delivered / reports emitted by operational sources')
fig.suptitle('Five-scenario PDR comparison', x=0.01, ha='left', color=INK, fontsize=12); mode_legend(fig)
save(fig, 'fig2_pdr.png')

for name, idx, ylabel, title in (('fig3_operational_nodes.png', 0, 'operational nodes', 'Operational nodes versus round'),
                                 ('fig4_residual_energy.png', 1, 'residual radio energy (J)', 'Residual radio energy versus round')):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for a, m in zip(ax, MODES):
        for s in SCN:
            y = np.array([series[(f'{m}_{s}', sd)][idx] for sd in SEEDS], float)
            mu, sdv, r = y.mean(0), y.std(0, ddof=1), np.arange(1, y.shape[1] + 1)
            a.fill_between(r, mu - sdv, mu + sdv, color=COL[s], alpha=0.18, linewidth=0)
            a.plot(r, mu, color=COL[s], linewidth=2, label=s)
        a.set_title(f'{m}: ' + ('4000-bit packet' if m == 'M2T' else 'profile frames'), loc='left'); a.set_xlabel('round (1 round = 1 h)')
        a.set_xlim(1, ROUNDS)
    ax[0].set_ylabel(ylabel); ax[0].legend(loc='lower left')
    fig.suptitle(title, x=0.01, ha='left', color=INK, fontsize=12)
    save(fig, name, 'line = mean over run seeds 42–46, band = ± sample SD' +
         ('; every M2F run keeps all 200 nodes (lines overlap at 200)' if idx == 0 else ''))

fig, ax = plt.subplots(figsize=(7.5, 4.2))
bars(ax, 'availability_pct', 'operational node-rounds (% of 200 × 500)', 'Cumulative operational node-rounds')
fig.suptitle('Network availability', x=0.01, ha='left', color=INK, fontsize=12); mode_legend(fig)
save(fig, 'fig5_availability.png')

fig, ax = plt.subplots(figsize=(7.5, 4.2))
bars(ax, 'mean_delay_ms', 'mean end-to-end delay (ms)', 'Mean path delay of delivered reports')
fig.suptitle('End-to-end delay', x=0.01, ha='left', color=INK, fontsize=12); mode_legend(fig)
save(fig, 'fig6_delay.png')

fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
bars(ax[0], 'energy_per_delivered_mJ', 'radio energy / delivered report (mJ)', 'M2T: 4000-bit packet', modes=('M2T',))
bars(ax[1], 'energy_per_delivered_mJ', 'radio energy / delivered report (mJ)', 'M2F: profile frames', modes=('M2F',))
fig.suptitle('Energy per delivered report (separate y-scales)', x=0.01, ha='left', color=INK, fontsize=12)
save(fig, 'fig7_energy_per_delivered.png', 'mean ± sample SD over run seeds 42–46; radio energy only (sensing ledger excluded)')

fig, axs = plt.subplots(2, 3, figsize=(13, 7.2))
for a, (k, yl, t) in zip(axs.flat, [('delivered_per_generated_pct', '%', 'Delivered / generated'),
                                     ('alive_r500', 'nodes', 'Operational nodes at round 500'),
                                     ('residual_radio_J', 'J', 'Residual radio energy (of 400 J)'),
                                     ('mean_delay_ms', 'ms', 'Mean end-to-end delay'),
                                     ('energy_per_delivered_mJ', 'mJ', 'Radio energy per delivered report'),
                                     ('radio_traffic_Mbit', 'Mbit', 'Radio traffic on air')]):
    bars(a, k, yl, t)
fig.suptitle('Mode 2T versus Mode 2F', x=0.01, ha='left', color=INK, fontsize=12); mode_legend(fig)
save(fig, 'fig8_mode2t_vs_mode2f.png')
print('figures written to', FIG)
sys.exit(0 if ok else 1)
