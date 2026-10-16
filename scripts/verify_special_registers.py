#!/usr/bin/env python3
"""Offline check of novel-results/2026-10-16-special-registers against results/2026-10-16-special-registers.

  vm-slot-sr113.json.gz  SR21 across concurrent / sequential VMs (run_sr_vm_slot.py), SR113 in large dispatches
                         (run_drm_sr_scan.py occupancy configs) and per submission (run_sr113_reps.py)
  divergence.json.gz     all 256 selectors inside nested ifs (run_sr_divergence.py)
"""
import gzip, json, sys
from pathlib import Path

E = Path(__file__).resolve().parents[1]/'results/2026-10-16-special-registers'
fails = 0


def check(ok, msg):
    global fails
    print(('ok   ' if ok else 'FAIL ')+msg)
    fails += not ok


v = json.load(gzip.open(E/'vm-slot-sr113.json.gz', 'rt'))
procs = [(r['utc'], ph, i, x) for r in v['vm_slot_runs'] for ph, xs in r['phases'].items() for i, x in enumerate(xs)]
check(all(x['buffer_ok'] and x['normal'] for *_, x in procs), f'{len(procs)} processes: every oracle passed, no hang signature')
check(all(x['sr21_uniform_all_lanes'] and x['sr113_uniform_all_lanes'] for *_, x in procs), 'SR21 and SR113 are uniform over every lane of a dispatch')
slots = [x['sr21'][0] for *_, x in procs]
check(all(1 <= s <= 63 for s in slots), f'SR21 always in 1..63 ({len(set(slots))} distinct values seen, never 0)')
for r in v['vm_slot_runs']:
    c = r['phases'].get('concurrent', [])
    if len(c) >= 2:
        vals = [x['sr21'][0] for x in c]
        # distinct VMs that were live together must hold distinct slots
        check(len(set(vals)) == len(vals), f'{len(c)} concurrent VMs ({r["utc"]}): {len(vals)} distinct SR21 values')
seq = [x['sr21'][0] for r in v['vm_slot_runs'] if r['args']['sequential'] >= 64 for x in r['phases']['sequential']]
check(len(seq) >= 64, f'a run with {len(seq)} sequential VMs (more than 63 slots)')
first_repeat = next((i for i in range(1, len(seq)) if seq[i] in seq[:i]), None)
check(first_repeat is not None and first_repeat >= 55, f'sequential VMs take {first_repeat} different slots before one repeats (least-recently-used cycling)')

runs_seq = [[x['sr21'][0] for x in r['phases']['sequential']] for r in v['vm_slot_runs'] if r['args']['sequential'] >= 8]
best = 0
for i in range(len(runs_seq[-1])):
    for j in range(len(runs_seq[-2])):
        k = 0
        while i+k < len(runs_seq[-1]) and j+k < len(runs_seq[-2]) and runs_seq[-1][i+k] == runs_seq[-2][j+k]:
            k += 1
        best = max(best, k)
check(best >= 20, f'two separate sequential runs share an identical stretch of {best} consecutive slots (the same LRU order recurs)')

big = v['sr113_large_dispatches']
check(all(len(d['sr113_distinct']) == 1 and len(d['cores']) == 38 for d in big.values()),
      'SR113 is one value over a whole 65,536-lane dispatch on all 38 cores: ' + ', '.join(f'{k}={d["sr113_distinct"]}' for k, d in big.items()))
reps = v['sr113_reps']
check(all(r['buffer_ok'] and r['ran_ok'] for r in reps), f'{len(reps)} SR113 counter processes: every submission ran (atomic count = lanes x submissions)')
tot = sum(r['R'] for r in reps)
eights = sum(r['reps_reading_8'] for r in reps)
check(tot >= 2000 and 0 < eights < 0.05*tot, f'SR113 = 8 in {eights:.0f} of {tot} submissions (rare, but not never)')
alone = [r for r in reps if r['set'] == 'alone-default' or r['proc'] == 'alone']
check(all(r['reps_reading_8'] == 0 for r in alone), f'alone, short and long kernels: 0 of {sum(r["R"] for r in alone)} submissions read 8')
single = [r for r in reps if r['set'] == 's113b']
check(len(single) >= 90 and all(r['reps_reading_8'] == 0 for r in single),
      f'{len(single)} single-submission processes in bursts of 16 (some overlapping another dispatch): all read 0')
conc = [r for r in reps if r['set'] == 's113' and r['proc'].startswith('c')]
check(len(conc) == 12 and sum(r['reps_reading_8'] for r in conc) > 0,
      f'12 processes submitting long kernels together: {sum(r["reps_reading_8"] for r in conc):.0f} of {sum(r["R"] for r in conc)} submissions read 8')
mixed = [r for r in reps if 0 < r['reps_reading_8'] < r['R']]
check(len(mixed) >= 1, f'{len(mixed)} processes read both 0 and 8 across their submissions: not a per-process constant')

d = json.load(gzip.open(E/'divergence.json.gz', 'rt'))
P = d['patterns']
check(all(p['buffer_ok'] and p['inactive_untouched'] and p['active_written'] for p in P.values()),
      f'{len(P)} divergence patterns: oracle passed, inactive lanes wrote nothing, active lanes wrote all 256 selectors')
base = P['uniform']
pos = {i: k for k, i in enumerate(base['active_lanes'])}
changed = set()
for n, p in P.items():
    for s in range(256):
        if [base['values'][str(s)][pos[i]] for i in p['active_lanes']] != p['values'][str(s)]:
            changed.add(s)
check(changed == {21, 56, 57, 58, 59}, f'selectors that differ from the uniform scan on the same lanes: {sorted(changed)} '
      '(SR21 only because each pattern is a new VM)')


def quad_rank(act, i):
    return sum(1 for u in range(i & ~3, i) if u in act)


ok = True
for n, p in P.items():
    act = set(p['active_lanes'])
    for k, i in enumerate(p['active_lanes']):
        g = i & ~31
        want = {56: quad_rank(act, i), 57: sum(1 for u in range(i & ~3, (i & ~3)+4) if u in act),
                58: sum(1 for u in range(g, i) if u in act), 59: sum(1 for u in range(g, g+32) if u in act), 16: i % 4, 60: 15, 63: 1}
        for s, w in want.items():
            ok &= p['values'][str(s)][k] == w
check(ok, 'every pattern: SR56 / SR57 = active rank / count in the quad, SR58 / SR59 = in the SIMD group, SR16 = lane & 3, SR60 = 15, SR63 = 1')
print(f'{fails} failures')
sys.exit(1 if fails else 0)
