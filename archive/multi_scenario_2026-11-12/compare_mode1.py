"""Mode 1 (controlled) multi-scenario check: are the five scenario runs identical at network level, and is the
water run identical to the validated variant-C seed-42 run of the original loader?

Usage (from RLHybrid_Scalability_Experiment):  python -P tools/compare_mode1.py
Writes results_multi_scenario/mode1_controlled/mode1_comparison.txt and mode1_metrics.csv. Exit 1 on a mismatch.
"""
import csv, hashlib, os, sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
D = os.path.join(ROOT, 'results_multi_scenario', 'mode1_controlled')
SCN = ['Water', 'Effluent', 'Air', 'Soil', 'Mixed']
REF = os.path.join(ROOT, 'results_200node_optimization', 'dev', 'energy_aware_routing', 'V2_200Node_EnergyAwareRouting-guard0.8-seed42')
EXACT = ['decisions.csv', 'per_round.csv', 'metrics.csv', 'unavailability.csv', 'unavailability_events.csv', 'nodes.csv']
out, ok = [], True


def path(s, f): return os.path.join(D, f'M1_{s}-seed42-{f}')
def md5(p): return hashlib.md5(open(p, 'rb').read()).hexdigest()
def rows(p): return list(csv.reader(open(p, newline='')))


def say(line=''):
    out.append(line)


def check(cond, what):
    global ok
    ok &= cond
    say(f'  [{"OK" if cond else "MISMATCH"}] {what}')


def strip_cols(p, drop):                 # file content without the label columns (station, date)
    r = rows(p)
    keep = [i for i, h in enumerate(r[0]) if h not in drop]
    return [[x[i] for i in keep] for x in r]


say('MODE 1 controlled multi-scenario comparison (200 nodes, 500 rounds, seed 42, variant C energyGuard 0.8, retx off, 4000 bit)')
say('=' * 110)
say('1. Network-level outputs, all five scenarios against M1_Water')
for f in EXACT:
    h = {s: md5(path(s, f)) for s in SCN}
    check(len(set(h.values())) == 1, f'{f:28s} byte-identical in all 5 scenarios (md5 {h["Water"][:12]})')
rep = {s: strip_cols(path(s, 'reports.csv'), {'station', 'date'}) for s in SCN}
check(all(rep[s] == rep['Water'] for s in SCN), f'reports.csv without station/date labels identical ({len(rep["Water"]) - 1} report fates)')
summ = {s: [l for l in open(path(s, 'summary.txt')) if not l.startswith('sensing ledger')] for s in SCN}
check(all(summ[s] == summ['Water'] for s in SCN), 'summary.txt identical apart from the sensing-ledger line')
wl = {s: rows(path(s, 'workload.csv')) for s in SCN}
slots = {s: [x[:3] for x in wl[s]][1:] for s in SCN}
check(all(slots[s] == slots['Water'] for s in SCN), f'generated report slots identical (reportIndex, round, sourceNode: {len(slots["Water"])} reports)')
def vals(x):                             # payload values without the NaN padding of the mixed layout
    v = x[5:]
    while v and v[-1] == 'NaN':
        v = v[:-1]
    return v


for s in SCN[1:]:
    diff = sum(vals(a) != vals(b) for a, b in zip(wl[s][1:], wl['Water'][1:]))
    say(f'      payload content differs from water in {diff} of {len(wl[s]) - 1} reports ({s}: fields {",".join(wl[s][0][5:])})')

say()
say('2. M1_Water against the validated run of the original KSPCB loader (old binary)')
say(f'   reference: {os.path.relpath(REF, ROOT)}-*')
for f in [x for x in EXACT if x != 'decisions.csv']:            # the reference run did not export decisions
    check(md5(path('Water', f)) == md5(f'{REF}-{f}'), f'{f:28s} byte-identical to the reference')
check(strip_cols(path('Water', 'reports.csv'), {'station'}) == strip_cols(f'{REF}-reports.csv', {'station'}),
      'reports.csv identical except the source label (REPLAY-n<k>:<station> vs water_quality:<station>)')
ref_wl = rows(f'{REF}-workload.csv')
same_vals = all(a[:3] == b[:3] and a[4:9] == b[4:9] for a, b in zip(wl['Water'][1:], ref_wl[1:])) and len(ref_wl) == len(wl['Water'])
check(same_vals, f'workload.csv: same {len(ref_wl) - 1} reports, dates and T, pH, EC, TDS values (DO extension column added)')

say()
say('3. Network metrics (identical in all five scenarios)')
m = {s: dict(zip(*rows(path(s, 'metrics.csv')))) for s in SCN}
pr = {s: rows(path(s, 'per_round.csv')) for s in SCN}
dec = {s: sum(1 for _ in open(path(s, 'decisions.csv'))) - 1 for s in SCN}
cols = ['scheduled', 'workloadAvailable', 'sourceAvailable', 'attempts', 'delivered', 'PDR', 'FND', 'finalAlive',
        'residualJ', 'spentJ', 'meanDelayS', 'meanHops', 'qUpdates', 'explorations', 'physicalFrames']
with open(os.path.join(D, 'mode1_metrics.csv'), 'w', newline='') as fo:
    w = csv.writer(fo)
    w.writerow(['scenario'] + cols + ['routingDecisions', 'txJ', 'rxJ', 'aggJ'])
    for s in SCN:
        hdr = pr[s][0]
        tot = {k: sum(float(x[hdr.index(k)]) for x in pr[s][1:]) for k in ('txJ', 'rxJ', 'aggJ')}
        w.writerow([s] + [m[s][c] for c in cols] + [dec[s]] + [f'{tot[k]:.6f}' for k in ('txJ', 'rxJ', 'aggJ')])
mw = m['Water']
say(f'   generated reports (valid-data slots) {mw["workloadAvailable"]} of {mw["scheduled"]} slots; emitted {mw["sourceAvailable"]}; '
    f'attempted {mw["attempts"]}; delivered {mw["delivered"]}')
say(f'   PDR {float(mw["PDR"]):.3f} %   FND round {mw["FND"]}   operational nodes at round 500: {mw["finalAlive"]}')
say(f'   residual {float(mw["residualJ"]):.4f} J   spent {float(mw["spentJ"]):.4f} J   mean path delay {float(mw["meanDelayS"]) * 1000:.2f} ms   '
    f'mean hops {float(mw["meanHops"]):.3f}')
say(f'   routing decisions logged {dec["Water"]}   Q updates {mw["qUpdates"]}   explorations {mw["explorations"]}   frames {mw["physicalFrames"]}')

say()
say('4. Separate sensing-energy ledger (NOT charged to the 2 J radio battery; 1 round = 1 h)')
say(f'   {"scenario":9s} {"sensor type":20s} {"nodes":>5s} {"J/node, operational rounds":>27s} {"J/node, all 500 rounds":>23s} {"x radio energy spent":>21s}')
radio = float(mw['spentJ'])
for s in SCN:
    g = defaultdict(lambda: [0, 0.0, 0.0])
    for x in list(csv.DictReader(open(path(s, 'sensing_ledger.csv'), newline=''))):
        e = g[x['sensorType']]
        e[0] += 1; e[1] += float(x['sensingJ_operational']); e[2] += float(x['sensingJ_allRounds'])
    tot = sum(v[1] for v in g.values())
    for k, (n, op, al) in sorted(g.items()):
        say(f'   {s:9s} {k:20s} {n:5d} {op / n:27.1f} {al / n:23.1f}')
    say(f'   {s:9s} {"total (operational)":20s} {sum(v[0] for v in g.values()):5d} {tot:27.1f} {"":23s} {tot / radio:21.0f}')
say()
say('RESULT: ' + ('identical network-level metrics and routing decisions in all five scenarios; only payload values, '
                  'labels and the sensing ledger differ' if ok else 'MISMATCH - see above'))
open(os.path.join(D, 'mode1_comparison.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
sys.exit(0 if ok else 1)
