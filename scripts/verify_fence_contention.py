#!/usr/bin/env python3
"""Offline checks of the retained multi-group fence-contention evidence
(results/2026-10-19-fence-contention). No GPU access."""
import collections
import gzip
import json
import statistics as st
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-fence-contention'
checks = []


def check(name, ok):
    checks.append(bool(ok))
    print('PASS' if ok else 'FAIL', name)


rec = json.load(gzip.open(D/'contention.json.gz'))
rs = rec['results']
check('matrix complete: 2 configs x 3 contexts x 7 programs x 5 samples', len(rs) == 210)
check('every dispatch output-correct with firmware timestamps',
      all(r['out_ok'] and r['fw_ns'] for r in rs))
check('keeper stopped cleanly', rec.get('keeper_stopped') is True)

g = collections.defaultdict(list)
for r in rs:
    g[(r['lanes'], r['ctx'], str(r['fence']))].append(r['fw_ns'])
med = {k: st.median(v) for k, v in g.items()}
check('all 42 cells have 5 samples', all(len(v) == 5 for v in g.values()))

# Exact medians from the 2026-10-19 run (firmware ns).
expected = {
    (32, 'none', 'None'): 7209, (32, 'none', 'f533'): 9250, (32, 'none', 'f59d'): 15875,
    (32, 'none', 'f59a'): 10458, (32, 'none', 'f533+f59a'): 12500,
    (32, 'none', 'f533+f59a+f59e'): 15625, (32, 'none', 'mesa_qf'): 40542,
    (32, 'store', 'None'): 11875, (32, 'store', 'f533'): 12417, (32, 'store', 'f59d'): 19083,
    (32, 'store', 'f59a'): 15000, (32, 'store', 'f533+f59a'): 15541,
    (32, 'store', 'f533+f59a+f59e'): 26875, (32, 'store', 'mesa_qf'): 53917,
    (32, 'load', 'None'): 13541, (32, 'load', 'f533'): 27292, (32, 'load', 'f59d'): 34042,
    (32, 'load', 'f59a'): 16459, (32, 'load', 'f533+f59a'): 30416,
    (32, 'load', 'f533+f59a+f59e'): 34625, (32, 'load', 'mesa_qf'): 63667,
    (256, 'none', 'None'): 7542, (256, 'none', 'f533'): 9458, (256, 'none', 'f59d'): 15542,
    (256, 'none', 'f59a'): 10667, (256, 'none', 'f533+f59a'): 12417,
    (256, 'none', 'f533+f59a+f59e'): 19042, (256, 'none', 'mesa_qf'): 40500,
    (256, 'store', 'None'): 11709, (256, 'store', 'f533'): 12583, (256, 'store', 'f59d'): 19125,
    (256, 'store', 'f59a'): 14917, (256, 'store', 'f533+f59a'): 15792,
    (256, 'store', 'f533+f59a+f59e'): 27666, (256, 'store', 'mesa_qf'): 55833,
    (256, 'load', 'None'): 13375, (256, 'load', 'f533'): 26042, (256, 'load', 'f59d'): 31125,
    (256, 'load', 'f59a'): 16250, (256, 'load', 'f533+f59a'): 28417,
    (256, 'load', 'f533+f59a+f59e'): 35291, (256, 'load', 'mesa_qf'): 57458,
}
check('all 42 medians match the retained record', all(med[k] == v for k, v in expected.items()))

# The contention claim: 8-group wall time within 25% of the 1-group twin in all 18
# fence cells (17 of 18 within 12%; serialization would be 8x).
worst, worstk = 0.0, None
for ctx in ('none', 'store', 'load'):
    for f in ('f533', 'f59d', 'f59a', 'f533+f59a', 'f533+f59a+f59e', 'mesa_qf'):
        a, b = med[(32, ctx, f)], med[(256, ctx, f)]
        r = abs(b - a) / a
        if r > worst:
            worst, worstk = r, (ctx, f)
check(f'8-group wall time within 25% of 1-group in all 18 fence cells (worst {worstk} {worst:.1%})',
      worst < 0.25)
check('17 of 18 fence cells within 12%',
      sum(1 for ctx in ('none', 'store', 'load') for f in ('f533', 'f59d', 'f59a', 'f533+f59a', 'f533+f59a+f59e', 'mesa_qf')
          if abs(med[(256, ctx, f)] - med[(32, ctx, f)]) / med[(32, ctx, f)] < 0.12) >= 17)

cores = json.load(open(D/'cores.json'))['results']
check('core placement: 32/32 and 256/256 each ran on exactly one core with correct outputs',
      len(cores) == 2 and all(c['distinct_cores'] == [0] and c['output_ok'] and c['rc'] == 0 for c in cores))
sys.exit(0 if all(checks) else 1)
