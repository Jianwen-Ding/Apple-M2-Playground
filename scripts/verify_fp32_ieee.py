#!/usr/bin/env python3
"""Offline checks of the IEEE fp32 (non-ftz and directed-rounding) fma measurements (results/2026-10-20-fp32-ieee).
The dataset is regenerated (fixed seed) and every retained hardware output is compared with the exact reference. No GPU access."""
import gzip, json, statistics as st, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO/'results/2026-10-20-fp32-ieee'
sys.path.insert(0, str(REPO/'scripts'))
import softfp32 as S  # noqa: E402
from run_drm_softfp32 import dataset  # noqa: E402

ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


ex = json.load(gzip.open(D/'exact.json.gz'))
cost = json.load(gzip.open(D/'cost.json.gz'))
t = dataset(12000)
n = len(t)
refs = {m: [S.ref_fma32(a, b, c, m) for a, b, c in t] for m in ('rn', 'rz', 'rm', 'rp')}
for m in ('rn', 'rz', 'rm', 'rp'):
    r = ex[f'soft-{m}']
    check(f'soft fma .{m}: {n}/{n} lanes bit-exact on hardware in all {len(r["hw"]["runs"])} runs, and equal to the simulator',
          r['hw']['out'] == refs[m] and all(x['bad'] == 0 for x in r['hw']['runs']) and r['sim']['sim_out'] == refs[m])
h = ex['hybrid']
check(f'hybrid non-ftz fma (native fmadd32 + needs_ieee + soft path under if): {n}/{n} bit-exact, 3 runs, equals the simulator',
      h['hw']['out'] == refs['rn'] and all(x['bad'] == 0 for x in h['hw']['runs']) and h['sim']['sim_out'] == refs['rn'])
nat = ex['native']['hw']['out']
normal = lambda x: 0 < (x >> 23) & 0xff < 255
dom = [i for i, (a, b, c) in enumerate(t) if normal(a) and normal(b) and normal(c) and normal(refs['rn'][i])]
check(f'independent check of the reference: native fmadd32 equals it on all {len(dom)} normal-domain lanes', all(nat[i] == refs['rn'][i] for i in dom) and len(dom) > 5000)
wrong = [i for i in range(n) if nat[i] != refs['rn'][i]]


def tiny_exact(a, b, c):
    va, vb, vc = S.f32val(a), S.f32val(b), S.f32val(c)
    if any(isinstance(v, (str, tuple)) for v in (va, vb, vc)):
        return False
    return 0 < abs(va*vb+vc) < S.Fraction(1, 2**126)


check(f'native fmadd32 differs from IEEE non-ftz on {len(wrong)} lanes, all with a subnormal operand or an exact result in (0, 2^-126) '
      '(including results IEEE rounds up to 2^-126, which the unit flushes)',
      len(wrong) > 1000 and all(any(0 < (x & 0x7fffffff) < 0x800000 for x in t[i]) or tiny_exact(*t[i]) for i in wrong))
P = S.Prog(); a, b, c, r = (P.input(k) for k in 'abcr'); nd = S.needs_ieee(P, a, b, c, r)
flag = [P.run({'a': x, 'b': y, 'c': z, 'r': w})(nd) for (x, y, z), w in zip(t, nat)]
check('needs_ieee flags every lane where the native result is wrong (no false negatives)', all(flag[i] for i in wrong))
check('needs_ieee does not flag zero results of zero factors with normal c (e.g. 0 * b + c)',
      all(not flag[i] for i, (x, y, z) in enumerate(t) if (x & 0x7fffffff) == 0 and normal(y) and normal(z)))
med = lambda k: st.median(x['fw_ns'] for x in cost[k]['runs'])  # first sweep: clock not held
nat_s = (med('hw-normal-k2048')-med('hw-normal-k1'))/2047
sl = {k: (med(f'{k}-k32')-med(f'{k}-k1'))/31 for k in ('hybrid-normal', 'hybrid-sparse', 'hybrid-dense', 'soft-normal')}
print('  us per dependent fma step, 131,072 lanes: native %.3f,' % (nat_s/1000), {k: round(v/1000, 2) for k, v in sl.items()})
check('every cost run was exact on its checked lanes', all(all(x['bad'] == 0 for x in r['runs']) for r in cost.values()))
check('native fmadd32: 0.12-0.22 us per step', 120 <= nat_s <= 220)
check('hybrid on all-normal data: 2-3.2 us per step (10-25x native)', 2000 <= sl['hybrid-normal'] <= 3200 and 10 <= sl['hybrid-normal']/nat_s <= 25)
check('soft path alone: 30-45 us per step; hybrid with one subnormal lane per SIMD group costs the same as every lane (35-50 us)',
      30000 <= sl['soft-normal'] <= 45000 and all(35000 <= sl[k] <= 50000 for k in ('hybrid-sparse', 'hybrid-dense')) and abs(sl['hybrid-sparse']/sl['hybrid-dense']-1) < 0.1)
kmed = lambda k: st.median(x['fw_ns'] for x in cost['keeper/'+k]['runs'])
knat = (kmed('hw-normal-k2048')-kmed('hw-normal-k1024'))/1024
ksl = {k: (kmed(f'{k}-k32')-kmed(f'{k}-k16'))/16 for k in ('hybrid-normal', 'hybrid-sparse', 'hybrid-dense', 'soft-normal')}
print('  clock held (keeper): native %.3f us,' % (knat/1000), {k: round(v/1000, 2) for k, v in ksl.items()})
check('clock held: hybrid on normal data 15-30x native, soft 150-300x, a subnormal lane per group 180-320x; all keeper runs exact',
      15 <= ksl['hybrid-normal']/knat <= 30 and 150 <= ksl['soft-normal']/knat <= 300 and 180 <= ksl['hybrid-sparse']/knat <= 320 and
      all(all(x['bad'] == 0 for x in v['runs']) for k, v in cost.items() if k.startswith('keeper/')))
print(f'{sum(ok)}/{len(ok)} fp32-ieee checks passed')
sys.exit(0 if all(ok) else 1)
