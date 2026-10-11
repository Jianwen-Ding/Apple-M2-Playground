#!/usr/bin/env python3
"""Offline checks of the sub-op space sweeps (results/2026-10-11-subop-spaces). No GPU access."""
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identify_funop as F  # noqa: E402
import identify_simd_op as S  # noqa: E402

D = Path(__file__).resolve().parents[1]/'results/2026-10-11-subop-spaces'
checks = []


def check(name, ok):
    checks.append(bool(ok)); print(('PASS' if ok else 'FAIL'), name)


def unz(n):
    t = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
    t.write(gzip.open(D/f'{n}.json.gz', 'rt').read()); t.close()
    return t.name


def load(n):
    return json.load(gzip.open(D/f'{n}.json.gz'))


# funop: 4-bit function (bits 28-31) + 2-bit rounding (bits 32-33, function 0 only)
fu = [load('funop2'), load('funop3')]
faults = sorted({r['flip']['value'] for s in fu for r in s['results'] if r['fault'] and r['flip'] and 'value' in r['flip']})
want_faults = sorted(v | h << 4 for v in (2, 3, 5, 7, 11, 15) for h in range(4))
check('funop: exactly functions 2,3,5,7,11,15 (any rounding bits) hang the GPU', faults == want_faults)
res = {r['flip']['value']: r['table'][6] for s in fu for r in s['results']
       if r['layout'] == 'A' and r['flip'] and not r['fault'] and 'value' in r['flip']}
check('funop: functions 1,4,6,8,9,10,12,13,14 ignore bits 32-33 (bit-identical outputs)',
      all(res[fn | 1 << 4] == res[fn | 2 << 4] == res[fn | 3 << 4] for fn in (1, 4, 6, 8, 9, 10, 12, 13, 14)) and
      all(res[fn] == res[fn | 1 << 4] for fn in (1, 4, 6, 8, 9, 10, 12, 13, 14)))
p = [unz('funop2'), unz('funop3')]
rows = {r['value']: r for r in F.main(p)}
for v, name in ((0b010000, 'ceil'), (0b100000, 'trunc'), (0b110000, 'rint'), (0b000100, 'dfdx(lane^1)'), (0b000110, 'dfdy(lane^2)')):
    check(f'funop {v:06b} = {name} on all 32 lanes', rows[v]['best'] == name and rows[v]['exact_lanes'] == 32)
check('funop constant bits 34-41: still floor on all lanes',
      all(rows[m]['best'] == 'floor' and rows[m]['exact_lanes'] == 32 for m in rows if isinstance(m, str)))
for f in p: os.unlink(f)

# iunop: op2 selects spread/bitrev/popcount/fls; op1 and bits 28-37 ignored
iu = load('iunop')
b = {r['name']: r for r in iu['results']}
x = b['bitrev-base-A']['table'][7]
spread = lambda v: sum(((v >> i) & 1) << (2*i) for i in range(16))
fls = lambda v: v.bit_length()-1
bitrev = lambda v: int(f'{v:032b}'[::-1], 2)
ok = True
for r in iu['results']:
    if r['layout'] != 'A' or r['key'] != 'bitrev': continue
    n = int.from_bytes(bytes.fromhex(r['cand'])[-6:], 'little'); op2 = n >> 26 & 3
    fn = (spread, bitrev, lambda v: bin(v).count('1'), fls)[op2]
    ok &= all(fn(v) == o for v, o in zip(x, r['table'][6]))
check('iunop: op2 00 = Morton spread of low 16 bits, 01 bitrev, 10 popcount, 11 highest set bit; op1 and bits 28-37 ignored (26 encodings)', ok)

# simd_op: structural model over all 128 op x kind encodings, both input sets
pi, pf = unz('simdop-ints'), unz('simdop-flts')
r = S.check_model(pi, pf)
check(f'simd_op: structural model matches all {len(r)} (encoding, input-set) pairs', len(r) == 192 and all(x[-1] for x in r))
os.unlink(pi); os.unlink(pf)

# shuffles (uniform B = 3)
su = load('shuf-uni')
src = {}
for rr in su['results']:
    if rr['layout'] != 'A' or rr['key'] != 'quad_shuffle': continue
    n = int.from_bytes(bytes.fromhex(rr['cand'])[-6:], 'little')
    src[(n >> 47 & 1, n >> 38 & 3, n >> 26 & 3)] = [(v-0x5a000606)//16 if (v-0x5a000606) % 16 == 0 and 0 <= (v-0x5a000606)//16 < 32 else None
                                                    for v in rr['table'][6]]
B = 3
for w, g in ((0, 4), (1, 32)):
    base = lambda i: i//g*g
    check(f'{"quad" if g == 4 else "simd"} shuffle/xor/up/down (op1=0): Mesa semantics, out-of-range keeps own lane',
          src[(0, 0, w)] == [base(i)+B % g for i in range(32)] and src[(0, 1, w)] == [base(i)+((i ^ B) % g) for i in range(32)] and
          src[(0, 2, w)] == [i-B if i-B >= base(i) else i for i in range(32)] and
          src[(0, 3, w)] == [i+B if i+B < base(i)+g else i for i in range(32)])
    check(f'{"quad" if g == 4 else "simd"} op1=1 op2=2: rotate up', src[(1, 2, w)] == [base(i)+(i-B) % g for i in range(32)])
check('bit 27 set: instruction is 8 bytes (r16 marker swallowed) -> simd_matrix_fmadd16/32, not a shuffle',
      all(rr['table'][17][0] != 0x5a000038 for rr in su['results'] if rr['layout'] == 'A' and rr['key'] == 'quad_shuffle'
          and int.from_bytes(bytes.fromhex(rr['cand'])[-6:], 'little') >> 27 & 1))
sp = load('shuf-perm13')
q = {}
for rr in sp['results']:
    if rr['layout'] != 'A' or rr['key'] != 'quad_shuffle': continue
    n = int.from_bytes(bytes.fromhex(rr['cand'])[-6:], 'little')
    q[(n >> 47 & 1, n >> 38 & 3, n >> 26 & 3)] = (rr['table'][6], [v & 0xffff for v in rr['table'][8]])
o, Bv = q[(0, 0, 1)]
orq = lambda i: Bv[i] & ~3 | (Bv[i & ~3] | Bv[i & ~3 | 1] | Bv[i & ~3 | 2] | Bv[i & ~3 | 3]) & 3
check('simd_shuffle with quad-divergent index: low 2 bits are the OR over the quad (Mesa agx_lower_divergent_shuffle)',
      [(v-0x5a000606)//16 for v in o] == [orq(i) for i in range(32)])

print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
