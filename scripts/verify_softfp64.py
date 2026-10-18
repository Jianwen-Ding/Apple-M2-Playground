#!/usr/bin/env python3
"""Offline checks of the software fp64 (results/2026-10-18-fp64): interpreter and simulator replay against IEEE, and the retained
hardware records. Needs agx_run built for the simulator replay (--no-sim skips it)."""
import gzip
import json
import math
import random
from pathlib import Path
import statistics as st
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts')); sys.path.insert(0, str(ROOT.parent/'AGX-Performance-Simulator/scripts'))
import softfp64 as S  # noqa: E402
import run_drm_softfp64 as R  # noqa: E402

ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


rec = json.load(gzip.open(ROOT/'results/2026-10-18-fp64/fp64.json.gz'))
# 1. retained hardware runs: every lane exact
for op, n_instr, lanes in (('mul', 176, 14304), ('add', 213, 14304), ('fma', 403, 20000)):
    r = rec['correctness'][op]
    check(f'{op}: hardware, {lanes} lanes x 3 runs, {n_instr} instructions, 0 lanes differ from IEEE binary64',
          r['lanes'] == lanes and r['instructions'] == n_instr and len(r['runs']) == 3 and all(x['bad'] == 0 for x in r['runs']))
for k, r in rec['cost'].items():
    if k.startswith(('mul', 'add', 'fma')):
        check(f'cost run {k}: {r["lanes"]} lanes ({r["checked_lanes"]} checked) x {len(r["runs"])} runs, keeper stopped, 0 lanes differ',
              len(r['runs']) == 9 and r.get('keeper_stopped') and all(x['bad'] == 0 for x in r['runs']))
# 2. cost slopes (per chained operation, per 131,072 lanes, from medians; noisy, so ranges)
med = lambda k: st.median([x['fw_ns'] for x in rec['cost'][k]['runs']])
for op, lo, hi in (('mul', 4500, 7500), ('add', 5500, 9500), ('fma', 12500, 19500)):
    ks = [1, 4, 8]
    xs = [rec['cost'][f'{op}_{k}']['chain'] for k in ks]
    ys = [med(f'{op}_{k}') for k in ks]
    mx, my = sum(xs)/3, sum(ys)/3
    slope = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/sum((x-mx)**2 for x in xs)
    check(f'{op}: {slope:.0f} ns per chained operation per 131,072 lanes (least squares over K = 1, 4, 8; accepted {lo}-{hi})', lo <= slope <= hi)
check('instructions per chained operation: mul 162, add 197, fma 387 (slope of the instruction count)',
      [round((rec['cost'][f'{op}_8']['instructions']-rec['cost'][f'{op}_1']['instructions'])/7) for op in ('mul', 'add', 'fma')] == [162, 197, 387])
# 3. interpreter vs IEEE on fresh random operands (independent of the retained data)
rng = random.Random(77)
for op, k, fn in (('mul', 2, S.fmul64), ('add', 2, S.fadd64), ('fma', 3, S.ffma64)):
    P = S.Prog()
    ins = [(P.input(f'{c}h'), P.input(f'{c}l')) for c in 'abc'[:k]]
    hi, lo = fn(P, *ins)
    bad = 0
    N = 3000
    for _ in range(N):
        xs = [R.rnd(rng) for _ in range(k)]
        g = P.run({f'{c}{w}': S.split(x)[j] for c, x in zip('abc', xs) for j, w in enumerate('hl')})
        r = S.ref(op, *xs)
        h, l = g(hi), g(lo)
        bad += not (math.isnan(S.join(h, l)) if math.isnan(r) else (h, l) == S.split(r))
    check(f'{op}: Python interpreter equals IEEE on {N} fresh random operand sets', bad == 0)
# 4. simulator replay of the exact generated programs
if '--no-sim' not in sys.argv:
    import coverage as cov  # noqa: E402
    import run_drm_compute as drm  # noqa: E402
    for op in ('mul', 'add', 'fma'):
        tuples = R.dataset(8000, op)
        n = len(tuples)
        prog, ninstr, used = R.build(op, n)
        o, t = cov.simulate(drm.build_main(prog), n, 32, 2*used+8, 0, R.table(tuples))
        bad = R.check(op, tuples, t)
        check(f'{op}: Rust simulator replay of the {ninstr}-instruction program, {n} lanes, 0 differ from IEEE', not bad)
sys.exit(0 if all(ok) else 1)
