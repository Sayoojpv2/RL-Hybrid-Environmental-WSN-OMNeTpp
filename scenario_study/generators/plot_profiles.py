"""Comparison figure of the sensor profiles and their reporting behaviour -> scenario_study/figures/scenario_comparison.png

Usage: python -P scenario_study/generators/plot_profiles.py   (after generate_scenarios.py)
"""
import csv, json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
P = json.load(open(os.path.join(ROOT, 'scenario_study', 'dataset_metadata', 'sensor_profiles.json')))
CATS = [('water_quality', 'Water (A, real)'), ('industrial_effluent', 'Effluent (B, synthetic)'),
        ('air_quality', 'Air (C, real)'), ('soil_monitoring', 'Soil (D, synthetic)')]
COL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']            # reference categorical slots 1-4, fixed order
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
N, R = 200, 500

stats = {}
for key, _ in CATS:
    rows = csv.DictReader(open(os.path.join(ROOT, 'data', 'scenarios', key + '_200', 'observations.csv'), newline=''))
    per_round, per_round_alarm = [0] * R, [0] * R
    s = {'m1': 0, 'periodic': 0, 'alarm_only': 0, 'bits': 0, 'sense': 0.0, 'payload': []}
    for w in rows:
        r = int(w['round']) - 1
        s['m1'] += w['m1_report'] == '1'
        s['sense'] += float(w['m2_sensing_mJ'])
        if w['m2_report'] == '1':
            per_round[r] += 1
            per_round_alarm[r] += w['m2_priority'] == '1'
            s['bits'] += int(w['m2_frame_bits'])
            s['payload'].append(int(w['m2_payload_bytes']))
            if w['m2_trigger'].startswith('alarm'):
                s['alarm_only'] += 1
            else:
                s['periodic'] += 1
    s['per_round'] = per_round
    stats[key] = s

plt.rcParams.update({'font.size': 9, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
                     'axes.spines.top': False, 'axes.spines.right': False})
fig, ax = plt.subplots(2, 2, figsize=(12, 8.2), facecolor='#fcfcfb')
for a in ax.flat:
    a.set_facecolor('#fcfcfb')
    a.grid(axis='y', color=GRID, lw=0.8)
    a.set_axisbelow(True)
labels = [l for _, l in CATS]
x = range(len(CATS))

# (a) payload: fields and frame size per report
a = ax[0, 0]
fields = [len(P['profiles'][k]['fields']) for k, _ in CATS]
frame = [max(stats[k]['payload']) * 8 + 17 * 8 for k, _ in CATS]
mean_frame = [stats[k]['bits'] / max(1, stats[k]['periodic'] + stats[k]['alarm_only']) for k, _ in CATS]
b = a.bar(x, mean_frame, color=COL, width=0.6, edgecolor='#fcfcfb', linewidth=2)
for i, k in enumerate(CATS):
    a.text(i, mean_frame[i] + 8, f'{fields[i]} fields\n{mean_frame[i]:.0f} bits (max {frame[i]})', ha='center', va='bottom', color=INK, fontsize=8)
a.set_xticks(list(x), labels, fontsize=8)
a.set_ylabel('Mode 2 frame size per report (bits)')
a.set_ylim(0, 480)
a.set_title('(a) Measurement fields and realistic frame size\n(Mode 1 uses the fixed 4000-bit packet for every profile)', fontsize=9, color=INK, loc='left')

# (b) reports per node in 500 rounds
a = ax[0, 1]
m1 = [stats[k]['m1'] / N for k, _ in CATS]
per = [stats[k]['periodic'] / N for k, _ in CATS]
alo = [stats[k]['alarm_only'] / N for k, _ in CATS]
a.bar(x, per, color=COL, width=0.6, edgecolor='#fcfcfb', linewidth=2, label='Mode 2 periodic (incl. merged alarms)')
a.bar(x, alo, bottom=per, color=COL, width=0.6, edgecolor='#fcfcfb', linewidth=2, hatch='////', alpha=0.55, label='Mode 2 extra alarm reports')
a.scatter(x, m1, marker='_', s=900, color=INK, lw=2, label='Mode 1 (identical in all scenarios)', zorder=3)
for i in x:
    a.text(i, per[i] + alo[i] + 8, f'{per[i] + alo[i]:.0f}', ha='center', va='bottom', color=INK, fontsize=8)
a.set_xticks(list(x), labels, fontsize=8)
a.set_ylabel('reports per node in 500 rounds')
a.set_ylim(0, 720)
a.legend(fontsize=7.5, frameon=False, loc='upper left', ncol=1)
a.set_title('(b) Offered reports per node', fontsize=9, color=INK, loc='left')

# (c) sensing energy vs radio energy and the 2 J budget (log scale)
a = ax[1, 0]
sense = [stats[k]['sense'] / N / 1000.0 for k, _ in CATS]        # J per node over 500 rounds
radio = P['radio_reference']
tx_own = [stats[k]['bits'] / N * (radio['Eelec_J_per_bit'] + radio['Efs_J_per_bit_m2'] * 50 ** 2) for k, _ in CATS]
w = 0.36
a.bar([i - w / 2 for i in x], sense, width=w, color=COL, edgecolor='#fcfcfb', linewidth=2, label='sensing + processing (assumed / datasheet)')
a.bar([i + w / 2 for i in x], tx_own, width=w, color=COL, edgecolor='#fcfcfb', linewidth=2, hatch='....', alpha=0.55,
      label='radio TX of own Mode 2 reports, 1 hop at 50 m')
a.axhline(2.0, color=INK, lw=1.2, ls='--')
a.text(3.45, 2.3, '2 J initial energy per node', ha='right', va='bottom', color=INK, fontsize=8)
for i in x:
    a.text(i - w / 2, sense[i] * 1.25, (f'{sense[i] / 1000:.1f} kJ' if sense[i] >= 1000 else f'{sense[i]:.3g} J'), ha='center', va='bottom', color=INK, fontsize=7.5)
    a.text(i + w / 2, tx_own[i] * 1.25, f'{tx_own[i]:.2g} J', ha='center', va='bottom', color=INK, fontsize=7.5)
a.set_yscale('log')
a.set_ylim(1e-3, 1e9)
a.set_xticks(list(x), labels, fontsize=8)
a.set_ylabel('energy per node over 500 rounds (J, log scale)')
a.legend(fontsize=7.5, frameon=False, loc='upper left')
a.set_title('(c) Sensing energy vs own-report radio energy', fontsize=9, color=INK, loc='left')

# (d) Mode 2 reports per round over time
a = ax[1, 1]
for (k, l), c in zip(CATS, COL):
    pr = stats[k]['per_round']
    ma = [sum(pr[max(0, i - 23):i + 1]) / (i + 1 - max(0, i - 23)) for i in range(R)]   # trailing 24-round mean
    a.plot(range(1, R + 1), ma, color=c, lw=2, label=l)
a.set_xlabel('round')
a.set_ylabel('Mode 2 reports per round, 24-round trailing mean')
a.set_xlim(1, R)
a.set_ylim(0, 215)
a.legend(fontsize=7.5, frameon=False, loc='lower right', ncol=2)
a.set_title('(d) Traffic over time: periodic schedules and alarm bursts', fontsize=9, color=INK, loc='left')

fig.suptitle('Scenario study: sensor profiles and reporting behaviour (200 nodes, 500 rounds; datasets in data/scenarios)', fontsize=10.5, color=INK, x=0.01, ha='left')
fig.text(0.01, 0.005, 'Real: KSPCB Periyar (water), UCI Beijing CC BY 4.0 (air), replayed onto 200 nodes. Synthetic: effluent, soil. '
         'ASSUMPTION-class energies are not device measurements (SENSOR_PARAMETER_MATRIX.csv).', fontsize=7.5, color=INK2)
fig.tight_layout(rect=(0, 0.02, 1, 0.96))
out = os.path.join(ROOT, 'scenario_study', 'figures')
os.makedirs(out, exist_ok=True)
fig.savefig(os.path.join(out, 'scenario_comparison.png'), dpi=150, facecolor=fig.get_facecolor())
print('wrote', os.path.join(out, 'scenario_comparison.png'))
