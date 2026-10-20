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
check('no fault or timeout in any of the 46 submissions', all(not x['fault'] for v in R.values() for x in v.values()) and sum(len(v) for v in R.values()) == 46)
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
print(f'{sum(ok)}/{len(ok)} barrier-bits checks passed')
sys.exit(0 if all(ok) else 1)
