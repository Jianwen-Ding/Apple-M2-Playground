#!/usr/bin/env python3
"""Offline checks of the retained SB minimal-fence-set evidence (results/2026-10-19-sb-minimal). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-sb-minimal'
checks = []


def check(name, ok):
    checks.append(bool(ok))
    print('PASS' if ok else 'FAIL', name)


def load(n):
    return json.load(gzip.open(D/f'{n}.json.gz'))['results']


def group(rs):
    g = collections.defaultdict(list)
    for r in rs:
        g[(r['fence'], r['store_coherent'])].append(r['violations'])
    return g


sb5 = group(load('sb5'))
check('matrix complete: 13 fences x 2 store policies x 10 repeats', len(load('sb5')) == 260)
check('all runs: 32,768 pairs, wait_between=1, no same-core violations',
      all(r['pairs'] == 32768 and r['wait_between'] == 1 and r['violations_same_core'] == 0 for r in load('sb5')))
check('f533+f59a normal stores: 0 violations in 10 runs', max(sb5[('f533+f59a', 0)]) == 0)
check('f533+f59a coherent stores: at most 32 per run, nonzero in exactly 2 of 10',
      max(sb5[('f533+f59a', 1)]) == 32 and sum(1 for v in sb5[('f533+f59a', 1)] if v > 0) == 2)
for f in ('f533+f59a+f59d', 'f533+f59a+f59e', 'f533+f59a+f599', 'f533+f59a+f596'):
    check(f'{f}: 0 violations in all 20 runs (both store policies)',
          max(sb5[(f, 0)] + sb5[(f, 1)]) == 0 and len(sb5[(f, 0)]) == 10 and len(sb5[(f, 1)]) == 10)
check('f596+f533+f59a normal: 0 in 10 runs; coherent: at most 16, exactly 2 nonzero',
      max(sb5[('f596+f533+f59a', 0)]) == 0 and max(sb5[('f596+f533+f59a', 1)]) == 16
      and sum(1 for v in sb5[('f596+f533+f59a', 1)] if v > 0) == 2)
check('f533+f59e coherent: 0 in 10 runs; normal: at most 48, exactly 4 nonzero',
      max(sb5[('f533+f59e', 1)]) == 0 and max(sb5[('f533+f59e', 0)]) == 48
      and sum(1 for v in sb5[('f533+f59e', 0)] if v > 0) == 4)
for f, coh, lo, hi in (('f533', 0, 464, 752), ('f533', 1, 208, 1936),
                       ('f533+f503', 0, 160, 624), ('f533+f503', 1, 272, 1600)):
    check(f'{f} coherent={coh}: every run violates ({lo}-{hi})',
          len(sb5[(f, coh)]) == 10 and min(sb5[(f, coh)]) == lo and max(sb5[(f, coh)]) == hi)
for f in ('f533+f596', 'f533+f599', 'f533+f59d'):
    check(f'{f}: leaks in both store policies',
          all(any(v > 0 for v in sb5[(f, c)]) for c in (0, 1)))
check('mesa_qf: 0 violations in all 20 runs', max(sb5[('mesa_qf', 0)] + sb5[('mesa_qf', 1)]) == 0)
sys.exit(0 if all(checks) else 1)
