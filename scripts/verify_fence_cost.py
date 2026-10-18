#!/usr/bin/env python3
"""Offline checks of the retained fence-cost run (results/2026-10-18-fence-cost). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import statistics as st
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-fence-cost'
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def per_fence(name):
    rec = json.load(gzip.open(D/name))
    d = collections.defaultdict(list)
    for r in rec['results']:
        d[(r['ctx'], r['fence'])].append(r['fw_ns'])
    n = rec['n']
    return rec, {k: (st.median(v)-st.median(d[(k[0], None)]))/n for k, v in d.items() if k[1]}, d


rec, pf, d = per_fence('fc15.json.gz')
rec5, pf5, _ = per_fence('fc5.json.gz')
check('15 interleaved samples of 30 programs (3 contexts x (control + 9 fence sets)), n = 32 units, all outputs exact, keeper stopped',
      rec['samples'] == 15 and rec['n'] == 32 and len(rec['results']) == 450 and all(r['out_ok'] for r in rec['results']) and rec['keeper_stopped'])
check('spread: every cell max/min < 1.7 (worst 1.60, one outlier run of store/f599; medians are used)', all(max(v)/min(v) < 1.7 for v in d.values()))
check('the independent 5-sample run agrees within 50 ns per fence on every cell (max |diff| = %.0f, on the 7-barrier sequence after a load)' % max(abs(pf[k]-pf5[k]) for k in pf),
      all(abs(pf[k]-pf5[k]) < 50 for k in pf))
for f in ('f533', 'f503', 'f59a'):
    check(f'back to back, {f}: 15-45 ns per fence', 15 <= pf[('none', f)] <= 45)
for f in ('f596', 'f59d', 'f59e', 'f599'):
    check(f'back to back, {f}: 80-100 ns per fence', 80 <= pf[('none', f)] <= 100)
check('back to back f533 + f59d: 110-125 ns', 110 <= pf[('none', 'f533+f59d')] <= 125)
check("Mesa's seven-barrier sequence: 430-440 ns back to back, 560-570 after a store, 640-650 after a load (+-15)",
      abs(pf[('none', 'mesa_qf')]-434) < 15 and abs(pf[('store', 'mesa_qf')]-564) < 15 and abs(pf[('load', 'mesa_qf')]-646) < 15)
check('after a coherent store: f533 costs under 15 ns, f503 under 35 ns, f59e costs 290-320 ns', pf[('store', 'f533')] < 15 and pf[('store', 'f503')] < 35 and 290 <= pf[('store', 'f59e')] <= 320)
check('after a coherent load: f533, f503, f59d, f599 and f533 + f59d cost 245-320 ns each (the next load misses); f596, f59a, f59e under 100 ns',
      all(245 <= pf[('load', f)] <= 320 for f in ('f533', 'f503', 'f59d', 'f599', 'f533+f59d')) and all(pf[('load', f)] < 100 for f in ('f596', 'f59a', 'f59e')))
sys.exit(0 if all(ok) else 1)
