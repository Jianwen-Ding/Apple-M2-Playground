#!/usr/bin/env python3
"""Offline checks of software fp64 div/sqrt/rcp and cvt (results/2026-10-19-fp64-divsqrt): interpreter and simulator
replay against exact references, and the retained hardware records. Needs agx_run built for the simulator replay
(--no-sim skips it)."""
import gzip
import json
import math
import random
import struct
import sys
from pathlib import Path
import statistics as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT.parent / 'AGX-Performance-Simulator/scripts'))
import softfp64 as S  # noqa: E402
import run_drm_softfp64 as R  # noqa: E402
import run_drm_cvt as C  # noqa: E402

ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


rec = json.load(gzip.open(ROOT / 'results/2026-10-19-fp64-divsqrt/fp64-divsqrt.json.gz'))
# 1. retained hardware runs: every lane exact
for op in ('div', 'sqrt', 'rcp'):
    for mode in ('rn', 'rz', 'rm', 'rp'):
        key = f'{op}_{mode}'
        r = rec['correctness'][key]
        check(f'{key}: hardware, {r["lanes"]} lanes x {len(r["runs"])} runs, {r["instructions"]} instructions, 0 differ',
              len(r['runs']) == 3 and all(x['bad'] == 0 for x in r['runs']))
for op in sorted(C.OPS):
    r = rec['correctness'][op]
    check(f'{op}: hardware, {r["lanes"]} lanes x {len(r["runs"])} runs, {r["instructions"]} instructions, 0 differ',
          len(r['runs']) == 3 and all(x['bad'] == 0 for x in r['runs']))
# 2. cost slopes (per chained operation, per 131,072 lanes, from medians); noisy, so ranges
med = lambda k: st.median([x['fw_ns'] for x in rec['cost'][k]['runs']])
for op, lo, hi in (('div', 39000, 55000), ('sqrt', 57000, 80000)):
    ks = [1, 4, 8]
    xs = [rec['cost'][f'{op}_{k}']['chain'] for k in ks]
    ys = [med(f'{op}_{k}') for k in ks]
    mx, my = sum(xs) / 3, sum(ys) / 3
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    check(f'{op}: {slope:.0f} ns per chained operation per 131,072 lanes (accepted {lo}-{hi})', lo <= slope <= hi)
check('instructions per chained operation: div 1085, sqrt 1498 (slope of the instruction count)',
      [round((rec['cost'][f'{op}_8']['instructions'] - rec['cost'][f'{op}_1']['instructions']) / 7)
       for op in ('div', 'sqrt')] == [1085, 1498] and
      abs((rec['correctness']['rcp_rn']['instructions'] - rec['correctness']['div_rn']['instructions'])) <= 8)
# 3. interpreter vs exact reference on fresh random operands (independent of the retained data)
rng = random.Random(99)
for op, fn, k in (('div', S.fdiv64, 2), ('sqrt', S.fsqrt64, 1), ('rcp', S.frcp64, 1)):
    progs = {}
    for mode in ('rn', 'rz', 'rm', 'rp'):
        Q = S.Prog()
        insq = [(Q.input(f'{c}h'), Q.input(f'{c}l')) for c in 'abc'[:k]]
        progs[mode] = (Q, fn(Q, *insq, mode))
    bad = 0
    N = 400
    for _ in range(N):
        xs = [R.rnd(rng) if op != 'sqrt' else abs(R.rnd(rng)) for _ in range(k)]
        env = {f'{c}{w}': S.split(x)[j] for c, x in zip('abc', xs) for j, w in enumerate('hl')}
        for mode, (Q, (ohi, olo)) in progs.items():
            gr = Q.run(env)
            r = S.ref(op, *xs, mode=mode)
            h, l = gr(ohi), gr(olo)
            bad += not (math.isnan(S.join(h, l)) if math.isnan(r) else (h, l) == S.split(r))
    check(f'{op}: Python interpreter equals the exact reference on {N} fresh operand sets x 4 modes', bad == 0)
# cvt interpreter checks
for op in sorted(C.OPS):
    fn, ikind, okind, mode = C.OPS[op]
    bad = 0
    N = 200
    vals = []
    if ikind == 'f64':
        vals = [R.rnd(rng) for _ in range(N)]
    elif ikind == 'f32':
        vals = [struct.unpack('<f', struct.pack('<I', rng.getrandbits(32)))[0] for _ in range(N)]
    else:
        vals = [rng.getrandbits(32) for _ in range(N)]
    for x in vals:
        P = S.Prog()
        ins = (P.input('ah'), P.input('al'))
        hi, lo = fn(P, ins, mode) if 'mode' in fn.__code__.co_varnames else fn(P, ins)
        if ikind == 'f64':
            g = P.run({'ah': S.split(x)[0], 'al': S.split(x)[1]})
        elif ikind == 'f32':
            g = P.run({'ah': 0, 'al': C.f32bits(x)})
        else:
            g = P.run({'ah': 0, 'al': x & 0xffffffff})
        h, l = g(hi), g(lo)
        base = op.rsplit('_', 1)[0]
        if base == 'cvt_f32_f64':
            want = float(struct.unpack('<f', struct.pack('<f', x))[0])
            bad += (S.join(h, l) != want)
        elif base == 'cvt_f64_f32':
            want = S.ref('cvt_f64_f32', x, mode=mode)
            wb = struct.unpack('<I', struct.pack('<f', want))[0] if not math.isnan(want) else None
            if wb is None:
                bad += not ((l >> 23) & 0xff == 0xff and (l & 0x7fffff) != 0)
            else:
                bad += (l != wb or h != 0)
        elif base in ('cvt_s32_f64', 'cvt_u32_f64'):
            want = S.ref(base, x & 0xffffffff, mode=mode)
            bad += (S.join(h, l) != want)
        else:
            want = S.ref(base, x, mode=mode) & 0xffffffff
            bad += (l != want or h != 0)
    check(f'{op}: Python interpreter equals the exact reference on {N} fresh values', bad == 0)
# 4. simulator replay of the exact generated programs
if '--no-sim' not in sys.argv:
    import coverage as cov  # noqa: E402
    import run_drm_compute as drm  # noqa: E402
    for op in ('div', 'sqrt', 'rcp'):
        for mode in ('rn', 'rz', 'rm', 'rp'):
            tuples = R.dataset(800, op)
            n = len(tuples)
            prog, ninstr, used = R.build(op, n, 1, mode)
            o, t = cov.simulate(drm.build_main(prog), n, 32, 2 * used + 8, 0, R.table(tuples))
            bad = R.check(op, tuples, t, mode=mode)
            check(f'{op}_{mode}: Rust simulator replay of the {ninstr}-instruction program, {n} lanes, 0 differ', not bad)
    for op in sorted(C.OPS):
        tuples = C.dataset(300, op)
        n = len(tuples)
        prog, ninstr, used = C.build(op, n, 1)
        o, t = cov.simulate(drm.build_main(prog), n, 32, 2 * used + 8, 0, C.table(op, tuples))
        bad = C.check(op, tuples, t)
        check(f'{op}: Rust simulator replay, {n} lanes, 0 differ', not bad)
sys.exit(0 if all(ok) else 1)
