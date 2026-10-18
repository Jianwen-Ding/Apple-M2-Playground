#!/usr/bin/env python3
"""Offline checks of the retained threadgroup-memory litmus run (results/2026-10-18-tg-litmus). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-tg-litmus'
rec = json.load(gzip.open(D/'tg.json.gz'))
rs = rec['results']
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


g = collections.Counter((r['kind'], r['fence']) for r in rs)
check('72 runs: sb, lb, mp x 8 fence variants x 3 repeats, 16,384 lanes in 64-lane workgroups',
      len(rs) == 72 and len(g) == 24 and all(v == 3 for v in g.values()) and rec['total'] == 16384 and rec['wg'] == 64)
check('no lane left an unset result word', all(r['unset'] == 0 for r in rs))
check('zero violations in every run, every variant (including no fence at all)', all(r['violations'] == 0 for r in rs))
n = rec['total']
check('SB: every lane read its partner\'s store (16,384 of 16,384 reads returned 1) in every run', all(r['sum_r0'] == n for r in rs if r['kind'] == 'sb'))
check('LB: no lane ever read a store that follows the partner\'s load (all reads 0)', all(r['sum_r0'] == 0 for r in rs if r['kind'] == 'lb'))
check('MP: the flag was visible on all 8 reads of every lane (131,072 flag reads per run)', all(r['sum_r0'] == 8*n for r in rs if r['kind'] == 'mp'))
sys.exit(0 if all(ok) else 1)
