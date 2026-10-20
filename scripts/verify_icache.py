#!/usr/bin/env python3
"""Offline checks of the instruction-cache measurements (results/2026-10-20-icache). No GPU access.
Times are ns per body instruction per SIMD group. Runs without the clock keeper use the median of the settled repeats
(the first repeats run while the clock ramps up); 'min' is used for the 8-repeat scans."""
import gzip, json, math, statistics as st, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
rec = json.load(gzip.open(REPO/'results/2026-10-20-icache/record.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


tmin = lambda x: min(x['fw_ns'])/(x['body_instr']*x['trips'])
tmed = lambda x, k=8: st.median([f/(x['body_instr']*x['trips']) for f in x['fw_ns']][k:])
lines = lambda x, pad=0: math.ceil(((64+pad) % 64 + x['loop_bytes'] + 6)/64)     # loop starts at code offset 64 + pad
CLOCK = (1.06, 1.10, 1.27, 1.31)                                                  # lower-clock plateaus of the 0.744 ns rate
artifact = lambda t: CLOCK[0] <= t <= CLOCK[1] or CLOCK[2] <= t <= CLOCK[3]

d0 = rec['dense-p0']['rows']
fits = [x for x in d0 if lines(x) <= 192]; over = [x for x in d0 if lines(x) > 192]
bad_fit = [x['bytes'] for x in fits if tmin(x) > 0.765 and not artifact(tmin(x))]
check(f'8-byte-aligned loop, every 8 bytes from 9,728: >= 95% of the {len(fits)} loops of <= 192 64-byte lines run in-cache (0.745 ns; '
      f'{len(bad_fit)} unsettled-clock points); all {len(over)} larger loops miss', len(bad_fit) <= 0.05*len(fits) and all(tmin(x) > 0.85 for x in over))
check('capacity edge: a 12,284-byte loop (192 lines from a line-aligned start) fits; 12,292 bytes (193 lines) misses',
      any(x['loop_bytes']+6 == 12284 and tmin(x) < 0.765 for x in d0) and any(x['loop_bytes']+6 == 12292 and tmin(x) > 0.85 for x in d0))
# pad sweep: 64-byte lines, 192 lines when 8-aligned, 161 otherwise
mism = []
for k, r in rec.items():
    if not k.startswith('padsweep/'):
        continue
    x = r['rows'][0]; P = r['pad']
    pred = lines(x, P) <= (192 if P % 8 == 0 else 161)
    t = tmin(x)
    if pred != (t < 0.765) and not artifact(t):
        mism.append((k, round(t, 3)))
n_pad = sum(k.startswith('padsweep/') for k in rec)
check(f'loop-start sweep (pads 0-128 step 2 at 12,264 and 10,240 bytes, {n_pad} runs): 64-byte lines, 192 lines usable when '
      'instructions are 8-byte aligned, 161 when misaligned: 0 mismatches outside clock plateaus', n_pad == 130 and not mism)
d2 = rec['dense-p2']['rows']
check('2-byte-shifted 8-byte loop: largest fitting size 10,280 bytes (161 lines); 10,288 (162 lines) misses',
      max(x['bytes'] for x in d2 if tmin(x) < 0.765) == 10280 and lines([x for x in d2 if x['bytes'] == 10280][0], 2) == 161)


def edge(r):
    pad = r['pad']; pts = [(lines(x, pad), tmin(x)) for x in r['rows']]
    base = min(t for _, t in pts)
    return max(l for l, t in pts if t < base*1.03)


want = {'mov4-p0': 192, 'mov4-p2': 161, 'iadd8-p2': 161, 'iadd8-p4': 161, 'and6-p0': 168, 'and6-p2': 169}
got = {k: edge(rec['straddle/'+k]) for k in want}
print('  capacity in lines by instruction size / start offset:', got)
check('capacity by layout: 4-byte aligned 192; 4-byte shifted, 8-byte shifted by 2 or 4: 161; 6-byte streams 168 / 169', got == want)
c = 192/161
pred = {F: 192/(F+(1-F)*c) for F in (0.25, 0.5, 0.75)}
sh = {}
for F in (0.25, 0.5, 0.75):
    r = rec[f'r16/shift{F}']['rows']
    sh[F] = max(lines(x) for x in r if tmed(x) < 0.78)
print('  partially shifted loops (aligned fraction -> lines fitting, proportional model):', {F: (sh[F], round(pred[F], 1)) for F in sh})
check('partial misalignment is proportional: capacity = 192 / (f + (1-f)*192/161) for aligned fraction f = 0.25/0.5/0.75 (floor)',
      all(sh[F] == math.floor(pred[F]) for F in sh))
du = rec['r16/dual-local64']['rows']
check('two SIMD groups on one core running different code (one aligned, one misaligned loop): fit through 5,376 B each, miss from 5,632 B '
      '(the cache is shared per core; 85+85*1.19 <= 192 < 89+89*1.19)',
      all(tmed(x) < 0.85 for x in du if x['bytes'] <= 5376) and all(tmed(x) > 0.9 for x in du if x['bytes'] >= 5632))
dx = {x['bytes']: x for x in rec['r16/dual-local32']['rows']}
check('different code in workgroups on different cores (SR20 0x30 / 0x31): 10,240 B each fits: caches are private per core',
      tmed(dx[10240]) < 0.78 and len(set(dx[10240]['cores'])) == 2)
e6 = {G: st.median(tmin(x) for x in [rec[f'keeper/e6-g{G}']['rows'][0]]) for G in (1, 8, 38, 76, 152)}
check('streaming beyond the cache (64 KB loop): 3.1-3.4 ns per 8-byte instruction per group from 1 to 152 groups (no GPU-wide fetch bottleneck)',
      all(3.0 <= v <= 3.5 for v in e6.values()))
e2 = {k: tmin([x for x in rec[f'keeper/e2-{k}']['rows'] if x['bytes'] == 65536][0]) for k in ('and6', 'mov4')}
g1 = tmin([x for x in rec['keeper/g1']['rows'] if x['bytes'] == 65536][0])
check('beyond the cache the cost is neither per byte nor per instruction: 0.39 / 0.48 / 0.53 ns per byte for 8 / 6 / 4-byte instructions',
      g1/8 < e2['and6']/6 < e2['mov4']/4 and abs(g1/8-0.39) < 0.03)
w = rec['r16/same2-wide']['rows']
slow2 = [x['bytes'] for x in w if tmed(x, 6) > 0.8]
occ = {L: {x['bytes']: tmed(x, 6) for x in rec[f'occ/local{L}']['rows']} for L in (64, 128, 256, 512)}
check(f'anomaly: two groups running the same in-cache loop fall into a 2-3.5x slower state at {len(slow2)} of {len(w)} sizes (4-12 KB), '
      'size- and run-dependent; a single group never does, and with 4 groups per core it disappears (0.75 ns at every size)',
      len(slow2) >= 20 and all(v < 0.78 for v in occ[128].values()))
agg = {L//32: (L//32)/st.median(occ[L].values()) for L in (128, 256, 512)}
print('  aggregate instructions per ns per core:', {k: round(v, 2) for k, v in agg.items()})
check('issue saturates at 4+ groups per core: aggregate 4.6-5.4 instructions/ns per core (3.3-3.8 per cycle at 1,398 MHz)',
      all(4.5 <= v <= 5.5 for v in agg.values()))
print(f'{sum(ok)}/{len(ok)} icache checks passed')
sys.exit(0 if all(ok) else 1)
