#!/usr/bin/env python3
"""Offline checks of the directed-rounding fp64 add / mul / fma runs (results/2026-10-20-fp64-modes), plus an interpreter
replay of the generated programs against the exact rational reference on a sample. No GPU access."""
import gzip, json, math, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import softfp64 as S  # noqa: E402
from run_drm_softfp64 import dataset  # noqa: E402

rec = json.load(gzip.open(REPO/'results/2026-10-20-fp64-modes/record.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


for op in ('add', 'mul', 'fma'):
    for m in ('rz', 'rm', 'rp'):
        r = rec[f'{op}-{m}']
        check(f'{op}.{m}.f64: {r["checked_lanes"]} lanes bit-exact on hardware in all {len(r["runs"])} runs ({r["instructions"]} instructions)',
              r['round'] == m and len(r['runs']) == 3 and all(x['bad'] == 0 for x in r['runs']) and r['checked_lanes'] >= 14000)
bad = 0
for op, k, fn in (('add', 2, S.fadd64), ('mul', 2, S.fmul64), ('fma', 3, S.ffma64)):
    data = dataset(300, op)[::7]
    for m in ('rz', 'rm', 'rp'):
        P = S.Prog(); ins = [(P.input(f'{c}h'), P.input(f'{c}l')) for c in 'abc'[:k]]; hi, lo = fn(P, *ins, mode=m)
        for xs in data:
            v = {}
            for c, x in zip('abc', xs):
                v[c+'h'], v[c+'l'] = S.split(x)
            g = P.run(v); got = (g(hi), g(lo)); r = S.ref(op, *xs, mode=m)
            bad += not (math.isnan(S.join(*got)) if math.isnan(r) else got == S.split(r))
check('interpreter replay of all 9 programs on a dataset sample equals the exact rational reference', bad == 0)
check('rational reference in rn reproduces host IEEE add / mul on 2,000 pairs (validates the rounding helper)',
      all(S.split(S._ref_mode2(o, x, y, 'rn')) == S.split(x+y if o == 'add' else x*y) or math.isnan(x+y if o == 'add' else x*y)
          for x, y in dataset(1000, 'add')[:2000] for o in ('add', 'mul')))
print(f'{sum(ok)}/{len(ok)} fp64-modes checks passed')
sys.exit(0 if all(ok) else 1)
