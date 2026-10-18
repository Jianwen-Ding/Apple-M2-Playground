#!/usr/bin/env python3
"""Offline checks of the retained SB / LB litmus evidence (results/2026-10-18-sb-lb). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-sb-lb'
checks = []


def check(name, ok):
    checks.append(bool(ok))
    print('PASS' if ok else 'FAIL', name)


def load(n):
    return json.load(gzip.open(D/f'{n}.json.gz'))['results']


def group(rs, kind=None):
    g = collections.defaultdict(list)
    for r in rs:
        if kind is None or r['kind'] == kind:
            g[(r['fence'], r['store_coherent'], r['wait_between'])].append(r['violations'])
    return g


matrix = load('sblb')
sb, lb = group(matrix, 'sb'), group(matrix, 'lb')
check('matrix complete: 2 kinds x 6 fences x 2 store policies x 2 wait modes x 3 repeats', len(matrix) == 144)
check('all runs: 32,768 pairs, no fault', all(r['pairs'] == 32768 for r in matrix))
lbv = [v for vs in lb.values() for v in vs]
check('LB: at most 32 violating pairs in any of 72 runs, 71 runs with none', len(lbv) == 72 and max(lbv) <= 32 and lbv.count(0) == 71)
check('SB never violates between lanes of one core in any run', all(r['violations_same_core'] == 0 for r in matrix))
for f in ('none', 'f596', 'f59d'):
    vs = [v for k, x in sb.items() if k[0] == f for v in x]
    check(f'SB with {f} alone: every run violates on 31,000+ of 32,768 pairs', len(vs) == 12 and min(vs) > 31000)
vs = [v for k, x in sb.items() if k[0] == 'f533' for v in x]
check('SB with f533 alone: every run violates, but on at most 1,264 pairs (<4%)', len(vs) == 12 and 0 < min(vs) and max(vs) <= 1264)
vs = [v for k, x in sb.items() if k[0] == 'f596+f533' for v in x]
check('SB with f596 + f533: 208-928 violating pairs per run', len(vs) == 12 and 0 < min(vs) and max(vs) <= 928)
vs = [v for k, x in sb.items() if k[0] == 'mesa_qf' for v in x]
check("SB with Mesa's queue-family sequence: 0 violations in 12 runs", len(vs) == 12 and max(vs) == 0)

sb2 = group(load('sb2'))
for f, coh, ok in (('f533+f59a', 0, 0), ('f533+f59a', 1, 0), ('f533+f59d+f59a', 0, 0), ('f533+f59d+f59a', 1, 0)):
    check(f'SB {f} (store coherent={coh}): 0 violations in 3 runs', max(sb2[(f, coh, 1)]) == 0)
check('SB f59d then f533 (wrong order) still violates in every run', all(v > 0 for k, x in sb2.items() if k[0] == 'f59d+f533' for v in x))
check('SB f533 + f503: violates in every run (256-1,120 pairs)', all(v > 0 for k, x in sb2.items() if k[0] == 'f533+f503' for v in x))

sb3 = group(load('sb3'))
check('SB f59a alone: ~half of the pairs violate in every one of 40 runs', all(min(x) > 31000 and len(x) == 10 for k, x in sb3.items() if k[0] == 'f59a'))
check('SB f533 + f59a: 0 in all 20 normal-store runs, at most 48 per run with coherent stores',
      all(max(sb3[('f533+f59a', 0, w)]) == 0 for w in (0, 1)) and all(max(sb3[('f533+f59a', 1, w)]) <= 48 for w in (0, 1)))
check('SB f59a then f533 (wrong order) violates (up to 608 pairs)', any(max(x) > 0 for k, x in sb3.items() if k[0] == 'f59a+f533'))

sb4 = group(load('sb4'))
full = ('f596', 'f533', 'f59a', 'f59e', 'f503', 'f599', 'f59d')
check('SB Mesa sequence: 0 violations in 16 further runs', max(sb4[('mesa_qf', 0, 1)]+sb4[('mesa_qf', 1, 1)]) == 0)
dropped = {k[0]: x for k, x in sb4.items() if k[0] != 'mesa_qf' and k[1] == 0}
check('drop-one: removing any single barrier from the sequence keeps 0 violations (normal stores, 8 runs each) except removing f533',
      all(max(x) == 0 for k, x in dropped.items() if 'f533' in k.split('+')) and len(dropped) == 7)
nof533 = [k for k in dropped if 'f533' not in k.split('+')][0]
check('sequence without f533: normal stores reach 20,000+ violating pairs in a run; coherent stores 0 in 8 runs',
      max(sb4[(nof533, 0, 1)]) > 20000 and max(sb4[(nof533, 1, 1)]) == 0)
sys.exit(0 if all(checks) else 1)
