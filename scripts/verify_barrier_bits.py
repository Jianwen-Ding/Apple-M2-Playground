#!/usr/bin/env python3
"""Offline checks of the threadgroup-barrier gap-bit runs (results/2026-10-20-barrier-bits). No GPU access."""
import gzip, json, sys
from pathlib import Path

rec = json.load(gzip.open(Path(__file__).resolve().parents[1]/'results/2026-10-20-barrier-bits/record.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


R = {k: {x['name']: x for x in v['results']} for k, v in rec.items()}
bits = [f'68{1 << b:02x}' for b in range(8)]
subs = sum(len(v['results'])*v.get('repeats', 1) for v in rec.values())
check(f'no fault or timeout in any of the {subs} submissions ({sum(len(v) for v in R.values())} programs)', all(not x['fault'] for v in R.values() for x in v.values()) and subs > 200)
for n in (64, 128, 256):
    r = R[f'n{n}']
    check(f'{n} lanes ({n//32} SIMD groups): every single byte-1 bit (68 01..68 80) gives 0 mismatches like 6800; the no-barrier control fails',
          all(r[b]['mismatches'] == 0 for b in bits+['6800', '6800-after']) and r['wait']['mismatches'] > 10000)
t = R['n256']
check('identical cost: every variant takes the same time as 6800 at 256 lanes (within 1%)', all(abs(t[b]['fw_ms']/t['6800']['fw_ms']-1) < 0.01 for b in bits))
s = {**R['split-01'], **R['split-all']}
names = [k for k in s if k.startswith('split-6800-00')]
check(f'barrier-ID test: groups 0-3 execute 6800 and groups 4-7 68XX ({len(names)} values incl. 68ff): all 8 groups still synchronize together (0 mismatches, no hang)',
      len(names) == 9 and all(s[k]['mismatches'] == 0 for k in names) and s['split-6800-6800']['mismatches'] == 0)

# follow-up (gap closing): no fence before the barrier, 10x trips, 3 submissions, device and threadgroup memory, 16,384 threads
b68 = bits+['68ff']
for k, m in (('g2-tg16k', 'threadgroup'), ('g2-dev16k', 'device')):
    r = R[k]
    check(f'no wait / memory_barrier before the barrier ({m} memory, 2,000 trips x 3 submissions): every 0x68 byte-1 bit and 68ff give 0 '
          f'mismatches like 6800 (barrier ordering intact); no-barrier control {r["wait"]["mismatches"]:,}',
          rec[k]['pre'] == 'none' and all(r[b]['mismatches'] == 0 for b in b68+['6800', '6800-after']) and r['wait']['mismatches'] > 1e8)
pc = R['g2-split-posctl']
check('positive control for the ID test: 7809 on both halves (two separate 4-group barriers) gives errors exactly in reading groups 3 and 7',
      pc['split-7809-7809']['mismatches'] > 1e6 and [g > 0 for g in pc['split-7809-7809']['err_lanes_by_group']] == [False, False, False, True]*2)
for m in ('tg', 'dev'):
    sp = R[f'g2-split-{m}']
    check(f'split ID test without fences ({m}): all 9 byte-1 values synchronize all 8 groups (0 mismatches)',
          all(x['mismatches'] == 0 for k, x in sp.items()) and len(sp) == 11)
a128, a256 = R['g2-78-n128'], R['g2-78-n256']
b78 = [f'78{1 << b:02x}' for b in range(8)]+['78ff']
check('0x78 byte-1 sweep at 128 lanes (inside its scope): every value gives 0 mismatches like 7809, same time within 1%',
      all(a128[b]['mismatches'] == 0 for b in b78+['7809']) and a128['wait']['mismatches'] > 1e8 and
      all(abs(a128[b]['fw_ms']/a128['7809']['fw_ms']-1) < 0.01 for b in b78))
check('0x78 byte-1 sweep at 256 lanes: every value fails only in reading groups 3 and 7, the same aligned 4-group scope as 7809',
      all([g > 0 for g in a256[b]['err_lanes_by_group']] == [False, False, False, True]*2 for b in b78+['7809', '7809-after']))
print(f'{sum(ok)}/{len(ok)} barrier-bits checks passed')
sys.exit(0 if all(ok) else 1)
