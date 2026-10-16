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
# ---- SR113 timeline (run_sr113_reps.py --timeline: SR113 read before and after the work, per submission) ------
import math, random, statistics
tl = json.load(gzip.open(E/'sr113-timeline.json.gz', 'rt'))['sets']
allsubs = [(name, p['worker'], s) for name, st in tl.items() for p in st['procs'] for s in p['subs']]
check(len(allsubs) >= 20000, f'{len(allsubs)} timed submissions in {len(tl)} sets')
small = [s for n, _, s in allsubs if tl[n]['lanes'] == 64 and s[2] and s[1] < 2]
check(small and all(s[0] == 0 and s[1] == 1 and s[2] == 64 for s in small),
      f'{len(small)} 64-lane submissions changed SR113 while running: every one 0 -> 8, all 64 lanes')
big = [s for n, _, s in allsubs if tl[n]['lanes'] == 65536 and s[2]]
check(big and all(0 < s[2] < 65536 for s in big),
      f'{len(big)} 65,536-lane submissions changed while running on only part of their lanes '
      f'({min(s[2] for s in big)}-{max(s[2] for s in big)}): lanes read it at different moments of one global change')
an = json.load(gzip.open(E/'sr113-timeline.json.gz', 'rt'))['anomalies']['events']
odd = [(n, s) for n, _, s in allsubs if s[1] > 1]
later = sum(len(p['subs']) for k in ('preload', 'repeat') for p in tl[k]['procs'])
check(len(an) == 3 and all(n == 'ts2' for n, _ in odd) and len(odd) == 3 and
      all((e['peek_after'][2]-e['peek_before'][2]) & 0xffffffff == 64*60002 for e in an) and
      not any(s[1] > 1 or s[0] > 1 for k in ('preload', 'repeat') for p in tl[k]['procs'] for s in p['subs']),
      f'3 end reads of 60002 (0xEA62) on all 64 lanes, all in ts2; none in {later} later submissions (with and without a preload)')
ov = dis = 0
for name in ('tl3', 'ts1'):
    subs = sorted(((p['worker'], s) for p in tl[name]['procs'] for s in p['subs']), key=lambda x: x[1][3])
    for i, (wa, a) in enumerate(subs):
        for wb, b in subs[i+1:i+40]:
            if b[3] >= a[4]:
                break
            if wa != wb and a[0] == a[1] and b[0] == b[1]:
                ov += 1
                dis += a[0] != b[0]
check(ov > 1000 and dis == 0, f'{ov} pairs of submissions from different processes running at the same time: they never disagree (one global state)')
for kind, name in (('alu', 'ts2'), ('chase', 'mc1')):
    d0 = [(s[4]-s[3])/1e3 for p in tl[name]['procs'] for s in p['subs'] if s[0] == s[1] == 0]
    d8 = [(s[4]-s[3])/1e3 for p in tl[name]['procs'] for s in p['subs'] if s[0] == s[1] == 1]  # 60002 reads excluded
    m0, m8 = statistics.median(d0), statistics.median(d8)
    check(abs(m0-m8)/m0 < 0.01, f'{kind} kernel ({name}): median duration {m0:.1f} us at SR113 = 0, {m8:.1f} us at 8 (no speed difference)')


def entries(name):
    L = tl[name]['lanes']
    out = []
    for p in tl[name]['procs']:
        last = None
        for k, s in enumerate(p['subs']):
            if s[0] == 0 and s[1] == 1:
                out.append((s[3], s[4]))
            elif s[0] == 1 and last == 0:
                out.append((p['subs'][k-1][4], s[3]))
            last = s[1]
    return [((a+b)/2)/1e6 for a, b in out if b-a < 1e6]


ts = [t for n in ('mc1', 'mcA', 'mcB') for t in entries(n)]
conc = lambda xs, P: abs(sum(complex(math.cos(2*math.pi*t/P), math.sin(2*math.pi*t/P)) for t in xs))/len(xs)
c56 = conc(ts, 56.0)
random.seed(1)
null = max(max(conc([t+random.uniform(-100, 100) for t in ts], P/100) for P in range(500, 20001, 7)) for _ in range(5))
check(len(ts) >= 30 and c56 > 0.75 and c56 > null+0.15,
      f'{len(ts)} 0 -> 8 entries (window < 1 ms) phase-lock to a 56.0 ms period (7 x the 8 ms power-sample period): '
      f'concentration {c56:.2f}, best of shuffled controls {null:.2f}')
gaps = []
for name, st in tl.items():
    if not name.startswith('gap/'):
        continue
    for p in st['procs']:
        for a, b in zip(p['subs'], p['subs'][1:]):
            if a[1] == 1:
                gaps.append(((b[3]-a[4])/1e3, b[0]))
short = [v for g, v in gaps if g < 1000]
long_ = [v for g, v in gaps if g > 1800]
check(short and long_ and all(short) and not any(long_),
      f'8 survives every GPU idle gap under 1.0 ms ({len(short)}) and none over 1.8 ms ({len(long_)}) (driver idle-off delay 2 ms)')
print(f'{fails} failures')
sys.exit(1 if fails else 0)
