#!/usr/bin/env python3
"""Offline checks of the retained fp32 compare record (results/2026-10-18-fcmp) and its replay in the Rust simulator."""
import gzip
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts')); sys.path.insert(0, str(ROOT.parent/'AGX-Performance-Simulator/scripts'))
import run_drm_fcmp as F  # noqa: E402
import run_drm_compute as drm  # noqa: E402
import coverage as cov  # noqa: E402

rec = json.load(gzip.open(ROOT/'results/2026-10-18-fcmp/fcmp.json.gz'))
V = rec['vals']; N = len(V); n = N*N
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


f = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
flush = lambda b: b & 0x80000000 if (b & 0x7f800000) == 0 else b
isnan = lambda b: (b & 0x7f800000) == 0x7f800000 and b & 0x7fffff
pairs = [(V[i//N], V[i % N]) for i in range(n)]
by = {}
for r in rec['results']:
    by.setdefault(r['cond'], []).append(r['out'])

check('48 values, 2,304 pairs, 7 conditions x 3 repeats, inputs read back intact', N == 48 and len(rec['results']) == 21 and all(r['inputs_intact'] for r in rec['results']))
check('every condition identical in all 3 repeats', all(all(o == v[0] for o in v) for v in by.values()))
out = {k: v[0] for k, v in by.items()}


def model(cond, a, b):
    a, b = flush(a), flush(b)
    na, nb = bool(isnan(a)), bool(isnan(b))
    x, y = f(a), f(b)
    nan = na or nb
    if cond == 'ltn':
        return int((not nan and x < y) or (nb and not na))
    if cond == 'gtn':
        return int((not nan and x > y) or (nb and not na))
    if nan:
        return 0
    return int({'eq': x == y, 'lt': x < y, 'gt': x > y, 'gte': x >= y, 'lte': x <= y}[cond])


for cond in F.CONDS:
    bad = sum(1 for (a, b), o in zip(pairs, out[cond]) if model(cond, a, b) != o)
    check(f'{cond}: hardware = model (subnormal inputs read as +-0; NaN compares false; ltn/gtn true when only B is NaN), 0 of 2,304 pairs differ', bad == 0)
# the flush matters: the IEEE model disagrees on subnormal operands
ieee_bad = sum(1 for (a, b), o in zip(pairs, out['lt']) if (0 if (isnan(a) or isnan(b)) else int(f(a) < f(b))) != o)
check('without the flush an IEEE compare disagrees with hardware on %d `lt` pairs (subnormal vs 0 or vs another subnormal)' % ieee_bad, ieee_bad == 189)
table = [x for x in rec['results'][0]['out'][:0]]
A = [V[i//N] for i in range(n)]; B = [V[i % N] for i in range(n)]
tab_in = A+B+[0xcdcdcdcd]*n
for cond in F.CONDS:
    o, t = cov.simulate(drm.build_main(F.body(cond, n)), n, 32, 48, 0, tab_in)
    check(f'Rust simulator replay of {cond}: all 2,304 result words equal hardware', t[2*n:] == out[cond])

# Integer fix-up programs (run_drm_fcmp_fixup.py): exact on hardware.
import run_drm_fcmp_fixup as X  # noqa: E402
fx = json.load(gzip.open(ROOT/'results/2026-10-18-fcmp/fixup.json.gz'))
Aa = [V[i//N] for i in range(n)]; Bb = [V[i % N] for i in range(n)]
check('fix-up record: 3 runs, 7 operations (setp eq lt gt le ge, min, max)', len(fx['results']) == 3 and fx['names'] == X.NAMES)
for nm in X.NAMES:
    want = [X.ieee(nm, a, b) for a, b in zip(Aa, Bb)]
    check(f'integer fix-up {nm}: all 2,304 results of all 3 hardware runs equal the PTX (non-ftz) host model',
          all(X.same(nm, r['out'][nm], want) for r in fx['results']))
native = {'lt': 189, 'gt': 189, 'eq': 378, 'le': 189, 'ge': 189}
for nm, cond in (('lt', 'lt'), ('gt', 'gt'), ('eq', 'eq'), ('le', 'lte'), ('ge', 'gte')):
    bad = sum(1 for (a, b), o in zip(pairs, out[cond]) if X.ieee(nm, a, b) != o)
    check(f'native {cond} differs from exact PTX setp.{nm} on {native[nm]} of 2,304 pairs (all with a subnormal operand)', bad == native[nm])
sub = lambda b: (b & 0x7f800000) == 0 and b & 0x7fffff
check('every native setp difference involves a subnormal operand',
      all(sub(a) or sub(b) for (a, b), o in zip(pairs, out['lt']) if X.ieee('lt', a, b) != o))
mn = sum(1 for (a, b), o in zip(pairs, out['ltn']) if not X.same('min', [a if o else b], [X.ptx_minmax('min', a, b)]))
mx = sum(1 for (a, b), o in zip(pairs, out['gtn']) if not X.same('max', [a if o else b], [X.ptx_minmax('max', a, b)]))
check('native compare-and-select min / max (Mesa: fcmpsel ltn / gtn) is wrong on 190 / 190 of 2,304 pairs vs PTX min / max', (mn, mx) == (190, 190))
sys.exit(0 if all(ok) else 1)
