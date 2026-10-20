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

# cheaper check (CHECK9) and the out-of-line slow-path layout
for k in ('hybrid2', 'hybrid3'):
    check(f'{k}: {n}/{n} bit-exact on hardware (3 runs) and in the simulator', ex[k]['hw']['out'] == refs['rn'] and ex[k]['sim']['sim_out'] == refs['rn'] and
          all(x['bad'] == 0 for x in ex[k]['hw']['runs']))
M1 = 0xffffffff


def check9(a, b, c, r):
    ta, tb, tc = [(M1 + ((x << 1) & M1)) & M1 for x in (a, b, c)]
    cond = max(ta, tb) if (r << 1) & M1 == 0 else M1
    return (0 if min(ta, tb, tc) < 0xfffffe else cond) != M1


check('CHECK9 (9 ops, 2|x|-1 trick) flags exactly the same lanes as the 14-op needs_ieee on all dataset lanes', [check9(*x, w) for x, w in zip(t, nat)] == flag)
lm = lambda k: st.median(x['fw_ns'] for x in cost['layout/'+k]['runs'])
lsl = lambda op, lo, hi: (lm(f'{op}-k{hi}')-lm(f'{op}-k{lo}'))/(hi-lo)
L = {'hybrid2': lsl('hybrid2-normal', 64, 128), 'hybrid3': lsl('hybrid3-normal', 64, 128), 'native': lsl('hw-normal', 1024, 2048),
     'nocf': lsl('nocf-normal', 128, 256), 'cfnojmp': lsl('cfnojmp-normal', 128, 256), 'cfonly': lsl('cfonly-normal', 128, 256),
     'cftaken': lsl('cftaken-normal', 128, 256), 'stub': lsl('stub-normal', 128, 256)}
print('  layout study, us per step:', {k: round(v/1000, 3) for k, v in L.items()})
check('a taken jmp_exec_none costs >= 0.7 us per step more than the untaken one (>= 12 native fma), the jump not the skipped code: a 1-instruction stub costs the same as the full hybrid',
      L['cftaken'] - L['cfonly'] >= 700 and (L['cftaken']-L['cfonly'])/L['native'] >= 12 and abs(L['stub']/L['hybrid2']-1) < 0.25)
check('out-of-line slow path (untaken jmp_exec_any on the common path): >= 1.5x faster than the if-skip layout on normal data, and exact under sparse subnormals',
      L['hybrid2']/L['hybrid3'] >= 1.5 and all(all(x['bad'] == 0 for x in cost[f'layout/hybrid3-sparse-k{K}']['runs']) for K in (16, 32)))

# constant-condition branch probes against the simulator cost model (AGX-Performance-Simulator agx_cost, if built)
pg = lambda us: us/1000*1398/(4096/38)                          # us per step at 131,072 lanes -> cycles per SIMD group
K = {k: pg(lsl(f'{k}-normal', 128, 256)) for k in ('ktaken', 'kuntaken', 'kany')}
print('  hardware cycles per group per step:', {k: round(v, 2) for k, v in K.items()})
check('a taken jmp_exec_none over one instruction costs >= 6 cycles per group more than the untaken form (full occupancy)', K['ktaken']-K['kuntaken'] >= 6)
import subprocess, tempfile, os
B = '/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_cost'
if os.path.exists(B):
    from run_drm_softfp32 import build
    pred = {}
    with tempfile.TemporaryDirectory() as td:
        for k in K:
            cyc = []
            for KK in (128, 256):
                prog, _, _ = build(k, 4096, KK)
                fn = os.path.join(td, f'{k}{KK}.bin'); open(fn, 'wb').write(prog+bytes.fromhex('8800'))
                o = subprocess.run([B, fn, '--groups', '16', '--allow-unknown'], capture_output=True, text=True).stdout
                cyc.append(json.loads(o.splitlines()[0])['cycles'])
            pred[k] = (cyc[1]-cyc[0])/128/16
    print('  cost model (16 groups):', {k: round(v, 2) for k, v in pred.items()})
    check('cost model with the 2026-10-20 forward-branch rule predicts each probe within 30% per group and the taken penalty within 25%',
          all(abs(pred[k]/K[k]-1) <= 0.3 for k in K) and abs((pred['ktaken']-pred['kuntaken'])/(K['ktaken']-K['kuntaken'])-1) <= 0.25)
print(f'{sum(ok)}/{len(ok)} fp32-ieee checks passed')
sys.exit(0 if all(ok) else 1)
