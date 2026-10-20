#!/usr/bin/env python3
"""Offline checks of the IEEE div.f32 measurements (results/2026-10-20-fdiv32), including the exhaustive proof that the
Newton-refined hardware reciprocal is correctly rounded for every mantissa (from the simulator repo's recorded rcp table).
No GPU access."""
import gzip, json, statistics as st, sys
from fractions import Fraction as F
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO/'results/2026-10-20-fdiv32'
RCP = Path('/save/workspace/AGX-Performance-Simulator/testsuite/transcendental/rcp.bin.gz')
sys.path.insert(0, str(REPO/'scripts'))
import softfp32 as S  # noqa: E402
from run_drm_fdiv32 import dataset  # noqa: E402
import struct  # noqa: E402

ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


def rne(n, d):
    q, r = divmod(n, d)
    return q + (2*r > d or (2*r == d and q & 1))


# 1. exhaustive: y1 = fma(fma(-b, y0, 1), y0, y0) == RN(1/b) for all 2^23 mantissas (y0 = recorded hardware rcp)
tab = gzip.open(RCP).read()
f2b = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
raw_bad = ref_bad = 0
for m in range(1, 1 << 23):
    B = (1 << 23) | m
    d = tab[m]-256 if tab[m] > 127 else tab[m]
    y0 = (f2b(1.0/(B/2**23)) + d) & 0xffffffff
    Y = (y0 & 0x7fffff) | (1 << 23); sh = 24 + (126 - ((y0 >> 23) & 0xff))
    E = (1 << (23+sh)) - B*Y                         # e = 1 - b*y0, exact
    q = rne((Y*((1 << (23+sh)) + E)) << 24, 1 << (2*sh+23))
    want = rne(1 << 47, B)
    raw_bad += Y != want
    ref_bad += q != want
check(f'raw hardware rcp is not correctly rounded on {raw_bad} of 8,388,607 mantissas (>1.5M)', raw_bad > 1_500_000)
check('Newton-refined y1 is correctly rounded (RN(1/b)) on all 8,388,607 non-trivial mantissas, so Markstein applies', ref_bad == 0)

ex = json.load(gzip.open(D/'exact.json.gz'))
edge = dataset('edge'); fast = dataset('fast', 131072)
ref_e = {m: [S.ref_div32(a, b, m) for a, b in edge] for m in ('rn', 'rz', 'rm', 'rp')}
ref_f = [S.ref_div32(a, b) for a, b in fast]
for m, k in (('rn', 'hw-soft-edge'), ('rz', 'hw-soft-edge-rz'), ('rm', 'hw-soft-edge-rm'), ('rp', 'hw-soft-edge-rp')):
    check(f'soft div .{m}: {len(edge)}/{len(edge)} edge lanes bit-exact on hardware, all runs', ex[k]['out'] == ref_e[m] and all(r['bad'] == 0 for r in ex[k]['runs']))
check('soft div .rn equals the simulator', ex['sim-soft-edge']['sim_out'] == ref_e['rn'])
check(f'hybrid div.rn (div_fast_ok ? fast sequence : soft): {len(edge)}/{len(edge)} bit-exact on hardware and in the simulator',
      ex['hw-hybrid-edge']['out'] == ref_e['rn'] and ex['sim-hybrid-edge']['sim_out'] == ref_e['rn'] and all(r['bad'] == 0 for r in ex['hw-hybrid-edge']['runs']))
check('fast sequence inside its domain: 131,072/131,072 random lanes (all-ones / all-zeros mantissas included) bit-exact, hardware and simulator',
      ex['hw-fast-fast']['out'] == ref_f and ex['sim-fast-fast']['sim_out'] == ref_f)
P = S.Prog(); a, b = P.input('a'), P.input('b'); okf = S.div_fast_ok(P, a, b)
inside = [P.run({'a': x, 'b': y})(okf) for x, y in edge]
fo = ex['hw-fast-edge']['out']
check('on the edge set the fast sequence is exact on every lane div_fast_ok accepts; all its errors are outside the domain',
      all(fo[i] == ref_e['rn'][i] for i in range(len(edge)) if inside[i]) and sum(fo[i] != ref_e['rn'][i] for i in range(len(edge))) > 1000)
mo = ex['hw-mesa-fast']['out']
worst = F(0)
for (x, y), g in zip(fast, mo):
    e = S.f32val(x)/S.f32val(y); gv = S.f32val(g); ae = abs(e)
    k = ae.numerator.bit_length()-ae.denominator.bit_length()
    k -= F(2)**k > ae
    worst = max(worst, abs(gv-e)/F(2)**(max(k, -126)-23))
mis = sum(g != r for g, r in zip(mo, ref_f))
check(f'Mesa a * rcp(b): misrounded on {mis}/131,072 in-domain lanes, max error {float(worst):.3f} ulp vs exact (< 2: within div.approx/div.full on this sample)',
      mis > 10000 and worst < 2)

cost = json.load(gzip.open(D/'cost.json.gz'))
med = lambda k: st.median(x['fw_ns'] for x in cost['cost-keeper/'+k]['runs'])
sl = lambda op, lo, hi: (med(f'{op}-k{hi}')-med(f'{op}-k{lo}'))/(hi-lo)
s = {'mesa': sl('mesa-normal', 256, 512), 'fast': sl('fast-normal', 256, 512), 'hybrid': sl('hybrid-normal', 16, 32),
     'hybrid-sparse': sl('hybrid-sparse', 16, 32), 'soft': sl('soft-normal', 16, 32)}
print('  us per dependent division (clock held, 131,072 lanes):', {k: round(v/1000, 3) for k, v in s.items()})
check('every cost run exact on its checked lanes (fast/hybrid/soft)', all(all(r['bad'] == 0 for r in v['runs']) for k, v in cost.items() if '/mesa' not in k))
check('cost order mesa < fast < hybrid < soft < hybrid-sparse; hybrid 8-16x mesa; soft 50-110x mesa',
      s['mesa'] < s['fast'] < s['hybrid'] < s['soft'] < s['hybrid-sparse'] and 8 <= s['hybrid']/s['mesa'] <= 16 and 50 <= s['soft']/s['mesa'] <= 110)
print(f'{sum(ok)}/{len(ok)} fdiv32 checks passed')
sys.exit(0 if all(ok) else 1)
