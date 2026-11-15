"""Independent audit of the scenario-study sensing energy, packet sizes and time base, plus the Mode 2 traffic table.

Recomputes every sensing-energy term in SI units (V x A x s = J) from sensor_profiles.json, checks the result against
the m2_sensing_mJ column of the datasets, audits payload / frame sizes against the datasets and IEEE 802.15.4 limits,
and states the time base. Changes no dataset.

Usage (from RLHybrid_Scalability_Experiment):  python -P scenario_study/generators/audit_energy_packets.py
Writes scenario_study/validation/energy_packet_timebase_audit.txt and results_multi_scenario/mode2_realistic/mode2_plan.csv.
"""
import csv, json, math, os, sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
P = json.load(open(os.path.join(ROOT, 'scenario_study', 'dataset_metadata', 'sensor_profiles.json')))
SC = os.path.join(ROOT, 'data', 'scenarios')
R, N, ROUND_S = 500, 200, 3600.0          # time base: 1 round = 1 h of environmental time
PROFILES = ['water_quality', 'industrial_effluent', 'air_quality', 'soil_monitoring']
M2F_FRAMES = {'water_quality': '280', 'industrial_effluent': '360', 'air_quality': '360', 'soil_monitoring': '264/328', 'mixed': 'own profile'}
PROFILE_BITS = {'water_quality': 280, 'industrial_effluent': 360, 'air_quality': 360, 'soil_monitoring': 264}   # M2F scenarioFrameBits; soil chemistry reports 328
rad = P['radio_reference']
EELEC, EFS, EDA, E0 = rad['Eelec_J_per_bit'], rad['Efs_J_per_bit_m2'], rad['Eda_J_per_bit'], 2.0
out, ok = [], True


def say(s=''):
    out.append(s)


def check(cond, what):
    global ok
    ok &= bool(cond)
    say(f'  [{"OK" if cond else "FAIL"}] {what}')


def tx(bits, d=50.0):
    return bits * (EELEC + EFS * d * d)        # first-order radio, free-space branch (d < d0 = 87.7 m)


chem_rounds = {p: ([r for r in range(1, R + 1) if (r - 1) % P['profiles'][p]['chem_interval_rounds'] == 0]
                   if P['profiles'][p].get('chem_interval_rounds') else []) for p in PROFILES}

# ------------------------------------------------------------------ 1. sensing energy, recomputed in SI units
say('SENSING ENERGY AUDIT (per node; 1 round = 1 h; 500 rounds = 500 h = 20.8 days)')
say('=' * 118)
say('E = V x I x t  [V x A x s = J]. "events/h": samples per hour for sampled sensors; 1 h on-time per hour for continuously')
say('biased sensors; chemistry events once per 24 rounds (rounds 1, 25, ..., 481 = 21 events in 500 rounds).')
per_node = {}
for p in PROFILES:
    prof = P['profiles'][p]
    spr = prof['samples_per_round']
    say()
    say(f'{p}  (sampling every {60 // spr} min = {spr} samples per 1-h round; report every {prof["report_interval_rounds"]} round(s), '
        f'alarm reports every {prof["alarm_interval_rounds"]} round)')
    say(f'  {"component":22s} {"hardware":44s} {"V":>5s} {"mA":>7s} {"on s":>7s} {"ev/500h":>8s} {"J/event":>9s} {"J/500 h":>10s} {"share":>6s}  class')
    rows, total = [], 0.0
    for f in prof['fields'] + prof.get('extension_fields', []):
        en = f['energy']
        if en['V'] == 0:
            continue
        on_s = en['ms'] / 1000.0
        if f.get('chem'):
            events = len(chem_rounds[p])
        elif en['ms'] >= 3600000:              # continuously powered: one 1-h "event" per round
            events = R * P['round_hours']
            on_s = ROUND_S
        else:
            events = R * spr
        j_event = en['V'] * (en['mA'] / 1000.0) * on_s
        rows.append((f['name'], f.get('hardware', '')[:44], en['V'], en['mA'], on_s, events, j_event, j_event * events, en['class']))
        total += j_event * events
    pr = P['processing']
    j_mcu = pr['mcu_active_V'] * pr['mcu_active_mA'] / 1000.0 * pr['mcu_ms_per_sample'] / 1000.0
    rows.append(('MCU per sample', 'MCU wake / read / scale / threshold', pr['mcu_active_V'], pr['mcu_active_mA'],
                 pr['mcu_ms_per_sample'] / 1000.0, R * spr, j_mcu, j_mcu * R * spr, pr['class']))
    total += j_mcu * R * spr
    for (n, hw, v, ma, s, ev, je, jt, cl) in rows:
        say(f'  {n:22s} {hw:44s} {v:5.1f} {ma:7.2f} {s:7.3f} {ev:8.0f} {je:9.4g} {jt:10.4g} {100 * jt / total:5.1f}%  {cl}')
    per_node[p] = total
    say(f'  {"TOTAL":22s} {"":44s} {"":5s} {"":7s} {"":7s} {"":8s} {"":9s} {total:10.4g}         '
        f'= {total / R:.4g} J/h = {1000 * total / R / ROUND_S:.4g} mW mean; {total / E0:.0f} x the 2 J radio battery')
    # cross-check against the dataset column (same model, independent arithmetic)
    col = defaultdict(float)
    with open(os.path.join(SC, p + '_200', 'observations.csv'), newline='') as fh:
        for w in csv.DictReader(fh):
            col[int(w['node_id'])] += float(w['m2_sensing_mJ']) / 1000.0
    dev = max(abs(v - total) for v in col.values())
    check(len(col) == N and dev < 0.05, f'dataset m2_sensing_mJ summed over 500 rounds = {col[1]:.4f} J per node '
          f'(all {len(col)} nodes; max |difference| to the SI recomputation {dev:.2e} J)')

say()
say('Questionable assumptions and sensitivities (per node, 500 h)')
w, ef, ai, so = (P['profiles'][k] for k in PROFILES)
do_j = 3.3 * 0.015 * 1.0 * 4 * R
say(f'  - Water counts the DO probe ({do_j:.1f} J) although DO is NOT in the payload (KSPCB DO preprocessing invalid):'
    f' {per_node["water_quality"]:.1f} J with DO, {per_node["water_quality"] - do_j:.1f} J without. EZO-class currents and the')
say('    1 s on-time are ASSUMPTIONS (datasheets not readable). Each extra second of on-time per pH/EC/DO reading adds '
    f'{3.3 * 0.015 * 4 * R:.0f} J per board.')
say(f'  - Standby/sleep currents are NOT in the ledger (sensors assumed power-gated between samples). Every 1 mA left on at '
    f'3.3 V costs {3.3e-3 * ROUND_S * R:.0f} J per 500 h, so an un-gated interface board would dominate water and soil.')
pm_sleep = 5.0 * 0.0002 * (ROUND_S - 4 * 30) * R
say(f'  - PMS5003: 15 J per wake-up = 5.0 V x 100 mA x 30 s, all VERIFIED values (manual v2.3), but 100 mA is the MAXIMUM')
say(f'    working current, so 30.0 kJ is an upper bound. If the sensor sleeps instead of being power-cut, the VERIFIED')
say(f'    standby current (<= 200 uA) adds {pm_sleep:.0f} J. Running it continuously would cost {5.0 * 0.1 * ROUND_S * R / 1000:.0f} kJ (30x).')
say(f'  - Air gases: 4 electrochemical sensors biased continuously (they cannot be duty-cycled quickly); the 1 mA ISB')
say(f'    supply current is an ASSUMPTION: {4 * 3.3 * 0.001 * ROUND_S * R:.0f} J = 44 % of the air total.')
uv = 12.0 * 0.25 * 20.0 * 4 * R
say(f'  - Effluent: the UV-Vis COD/BOD probe (12 V x 250 mA x 20 s, ASSUMPTION) is {uv:.0f} J = '
    f'{100 * uv / per_node["industrial_effluent"]:.1f} % of {per_node["industrial_effluent"]:.0f} J. Such multi-watt')
say(f'    analysers are normally mains- or solar-powered; without it the node needs {per_node["industrial_effluent"] - uv:.0f} J.')
say('  - Soil: probe (5 V x 10 mA x 150 ms) and pH/NPK readings are ASSUMPTIONS; low-cost RS485 "NPK" probes infer')
say('    nutrients indirectly and their accuracy is unverified.')
say('  - Units: every term is V x mA x ms = uJ (generator) = V x A x s = J (this audit); both agree (checks above).')
say('  - All four profiles exceed the 2 J radio battery (soil 14x, water 152x, air 26,910x, effluent 60,451x), so')
say('    sensing is kept in a SEPARATE ledger. The runs measure communication-network lifetime, not node battery life.')

# ------------------------------------------------------------------ 2. time base
say()
say('TIME BASE')
say('=' * 118)
say('  1 round = 1 h of environmental time for sampling, reporting and the sensing ledger. 500 rounds = 500 h = 20.8 days.')
say('  OMNeT++ reserves 100 s of simulated time per round (scheduling only; the network work of a round ends far earlier);')
say('  path delay is a physical per-report time (k/Rbit + Tproc + d/c per hop), independent of the round slot.')
for p in PROFILES:
    prof = P['profiles'][p]
    spr = prof['samples_per_round']
    extra = f'; chemistry every {prof["chem_interval_rounds"]} rounds = daily' if prof.get('chem_interval_rounds') else ''
    say(f'  {p:20s} {spr} samples/round = every {60 // spr} min; periodic report every {prof["report_interval_rounds"]} h;'
        f' alarm report at most every {prof["alarm_interval_rounds"]} h while an alarm is active{extra}')
dates = sorted({r['Date'] for r in csv.DictReader(open(os.path.join(ROOT, 'data', 'v2_consdata_loaded.csv'), newline=''))})
span = len(dates) - 1
say(f'  Water VALUES keep the validated KSPCB schedule: {len(dates)} sampling dates ({dates[0]} .. {dates[-1]}) spread over')
say(f'    1000 rounds, i.e. one KSPCB date every {999 / span:.3f} rounds; rounds 1-500 replay the dates up to ~date index'
    f' {int(499 / (999 / span))} (mid-April 2025).')
say(f'    The value stream is therefore time-compressed {24 / (999 / span):.2f}x relative to the 1-h round (daily grab samples,')
say('    sample-and-hold). This affects which values / alarms appear, never energy or the schedule. If the round were taken')
say(f'    as the KSPCB slot (~{24 / (999 / span):.2f} h) instead, water sensing would rise to '
    f'{per_node["water_quality"] * 24 / (999 / span):.0f} J: this inconsistency is removed by fixing 1 round = 1 h.')
say('  Air: 500 consecutive UCI hours (2016-12-01 00:00 + 0..499 h). Effluent, soil: synthetic hourly series T+0..499 h.')

# ------------------------------------------------------------------ 3. packets
say()
say('PACKET SIZE AUDIT')
say('=' * 118)
fr = P['frame']
hdr, fb, ovh = fr['app_header_bytes'], fr['field_bytes'], fr['mac_phy_overhead_bytes']
say(f'  Application header {hdr} B: {fr["app_header_layout"]}.')
say(f'  Each field: {8 * fb}-bit scaled integer (value / scale); absent fields are cleared in the presence bitmap and not sent.')
say(f'  MAC/PHY overhead {ovh} B: {fr["mac_phy_overhead_note"]}.')
say('  IEEE 802.15.4 limit: PSDU <= 127 B, i.e. <= 116 B of MAC payload with this 11 B MAC header + FCS.')
stats = {}
for p in PROFILES + ['mixed']:
    stats[p] = {'rep': 0, 'bits': 0, 'pay': 0, 'pri': 0, 'per_node': defaultdict(int), 'fmin': 10 ** 9, 'fmax': 0, 'sense': 0.0, 'pbits': 0}
nodemap = {int(r['node_id']): r['sensor_type'] for r in csv.DictReader(open(os.path.join(SC, 'mixed_environment_200', 'node_map.csv'), newline=''))}
for p in PROFILES:
    with open(os.path.join(SC, p + '_200', 'observations.csv'), newline='') as fh:
        for w_ in csv.DictReader(fh):
            nd = int(w_['node_id'])
            targets = [p] + (['mixed'] if nodemap[nd] == p else [])
            for t in targets:
                st = stats[t]
                st['sense'] += float(w_['m2_sensing_mJ']) / 1000.0
                if w_['m2_report'] != '1':
                    continue
                b = int(w_['m2_frame_bits'])
                st['rep'] += 1; st['bits'] += b; st['pay'] += int(w_['m2_payload_bytes']); st['pri'] += int(w_['m2_priority'])
                st['per_node'][nd] += 1; st['fmin'] = min(st['fmin'], b); st['fmax'] = max(st['fmax'], b)
                st['pbits'] += 328 if '+chem' in w_['m2_trigger'] else PROFILE_BITS[p]   # frame charged in M2F
say(f'  {"profile":27s} {"fields":>6s} {"payload B":>9s} {"frame B":>7s} {"frame bit":>9s} {"reports/127B frame":>18s}  '
    f'Mode 2 data: mean frame bit (min-max)')
for p in PROFILES:
    prof = P['profiles'][p]
    nf = len([f for f in prof['fields'] if not f.get('chem')])
    nc = len(prof['fields'])
    for k, n_ in ([('', nf)] if nf == nc else [(' no chem', nf), (' chem', nc)]):
        pay = hdr + fb * n_
        say(f'  {p + k:27s} {n_:6d} {pay:9d} {pay + ovh:7d} {8 * (pay + ovh):9d} {116 // pay:18d}'
            + (f'  {stats[p]["bits"] / stats[p]["rep"]:.1f} ({stats[p]["fmin"]}-{stats[p]["fmax"]})' if k != ' chem' else ''))
    check(stats[p]['fmax'] <= 8 * (hdr + fb * nc + ovh), f'{p}: no Mode 2 frame larger than the full-profile frame')
say('  Mode 1 / Mode 2T: the reference 4000-bit packet (500 B) of the MATLAB first-order radio model. It is an abstraction:')
say('    500 B exceeds the 127 B 802.15.4 PSDU (it would need 5 frames). The 18-28 B measurement payload is carried inside it.')
say('  Aggregation: the cluster head concatenates reports without compression and is charged per report (report-preserving')
say('    energy: m reports = m x packetSize on TX and RX, plus E_DA x packetSize x m). Aggregation never changes the bits per')
say('    report. Real 802.15.4 concatenation could share the 17 B overhead (up to the reports/127B column), which the model')
say('    does not credit, so Mode 2F radio energy is an upper bound for the given traffic.')
say('  Mode 2F charges every report its own profile frame (scenarioFrameBits: water 280, effluent 360, air 360, soil 264,')
say('    328 on chemistry rounds; mixed nodes keep their own profile). One-packet thresholds use the frame mean report bits;')
say('    the minimum-energy rule uses packetSize = the smallest frame of the scenario. Missing fields do not shrink M2F frames.')
say('    Side effects of a smaller packetSize inside the unchanged model (documented, not hidden):')
say(f'    - TX of one report over 50 m: {tx(4000) * 1e3:.3f} mJ at 4000 bit vs {tx(280) * 1e3:.4f}-{tx(360) * 1e3:.4f} mJ; the reward energy term')
say('      min(1, E/1 mJ) shrinks by the same 11-14x factor, so the learned trade-off shifts towards link quality/progress.')
say(f'    - minimum-operation rule E < E_elec x packetSize: {EELEC * 4000 * 1e6:.0f} uJ at 4000 bit vs {EELEC * 280 * 1e6:.0f}-{EELEC * 360 * 1e6:.0f} uJ.')
say('    - hop delay k/Rbit: 16 ms at 4000 bit vs 1.1-1.4 ms; Tproc = 5 ms then dominates.')
say('    Mode 2T keeps all three exactly as in Mode 1; compare M2T with Mode 1 for the schedule effect and M2F with M2T for')
say('    the frame-size effect.')

# ------------------------------------------------------------------ 4. Mode 2 plan table
plan = os.path.join(ROOT, 'results_multi_scenario', 'mode2_realistic')
os.makedirs(plan, exist_ok=True)
hdrs = ['scenario', 'reports_m2', 'priority_reports', 'reports_per_node_mean', 'reports_per_node_min', 'reports_per_node_max',
        'payload_B_mean', 'frame_bits_mean', 'frame_bits_max', 'M2T_packet_bits', 'M2F_frame_bits',
        'offered_MB_M2T', 'offered_MB_M2F', 'own_TX_J_per_node_50m_M2T', 'own_TX_J_per_node_50m_M2F',
        'sensing_J_per_node_500h', 'mode1_reports', 'mode1_offered_MB']
say()
say('MODE 2 PLAN: offered traffic at the sources; relaying multiplies transmissions by the hop count (Mode 1: 4.6)')
say('=' * 118)
say(f'  {"scenario":20s} {"reports":>7s} {"priority":>8s} {"per node":>14s} {"payload B":>9s} {"frame bit":>12s} {"M2F frame":>11s} '
    f'{"MB M2T":>7s} {"MB M2F":>7s} {"own TX J/node":>15s} {"sensing J/node":>14s}')
with open(os.path.join(plan, 'mode2_plan.csv'), 'w', newline='') as fo:
    wr = csv.writer(fo)
    wr.writerow(hdrs)
    for p in PROFILES + ['mixed']:
        st = stats[p]
        pn = [st['per_node'].get(k, 0) for k in range(1, N + 1)]
        mb_t, mb_f = st['rep'] * 4000 / 8e6, st['pbits'] / 8e6
        txt, txf = tx(st['rep'] * 4000) / N, tx(st['pbits']) / N
        row = [p, st['rep'], st['pri'], f'{st["rep"] / N:.1f}', min(pn), max(pn), f'{st["pay"] / st["rep"]:.2f}',
               f'{st["bits"] / st["rep"]:.1f}', st['fmax'], 4000, M2F_FRAMES[p], f'{mb_t:.2f}', f'{mb_f:.3f}', f'{txt:.4f}',
               f'{txf:.5f}', f'{st["sense"] / N:.1f}', 96500, f'{96500 * 4000 / 8e6:.2f}']
        wr.writerow(row)
        say(f'  {p:20s} {st["rep"]:7d} {st["pri"]:8d} {st["rep"] / N:6.1f} ({min(pn)}-{max(pn)}) {st["pay"] / st["rep"]:9.2f} '
            f'{st["bits"] / st["rep"]:6.1f}/{st["fmax"]:<5d} {M2F_FRAMES[p]:>11s} {mb_t:7.2f} {mb_f:7.3f} {txt:6.3f}/{txf:7.4f} {st["sense"] / N:14.1f}')
m1 = defaultdict(int)
with open(os.path.join(SC, 'water_quality_200', 'observations.csv'), newline='') as fh:
    for w_ in csv.DictReader(fh):
        m1[int(w_['node_id'])] += w_['m1_report'] == '1'
say(f'  {"Mode 1 (every scenario)":20s} {sum(m1.values()):7d} {"-":>8s} {sum(m1.values()) / N:6.1f} ({min(m1.values())}-{max(m1.values())}) '
    f'{"-":>9s} {4000:>12d} {"-":>7s} {sum(m1.values()) * 4000 / 8e6:7.2f}')
say('  Radio model (all modes): first-order, E_elec 50 nJ/bit, eps_fs 10 pJ/bit/m^2, eps_mp 0.0013 pJ/bit/m^4, E_DA 5 nJ/bit,')
say('  d0 = 87.7 m, 2 J per node, report-preserving energy. "own TX" = one 50 m hop of the node\'s own reports only.')
say()
say('RESULT: ' + ('all checks passed' if ok else 'FAILURES - see above'))
os.makedirs(os.path.join(ROOT, 'scenario_study', 'validation'), exist_ok=True)
open(os.path.join(ROOT, 'scenario_study', 'validation', 'energy_packet_timebase_audit.txt'), 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
sys.exit(0 if ok else 1)
