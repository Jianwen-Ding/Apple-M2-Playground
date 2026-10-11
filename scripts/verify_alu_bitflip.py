#!/usr/bin/env python3
"""Offline checks of the retained ALU bit-flip evidence (results/2026-10-11-alu-bitflip).

No GPU access. Each check recomputes a claim of
novel-results/2026-10-11-fmadd-lane-offset/README.md from the gzipped run records.
"""
import gzip
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_bitflip as A  # noqa: E402

D = Path(__file__).resolve().parents[1]/'results/2026-10-11-alu-bitflip'
f32 = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]
checks = []


def check(name, ok):
    checks.append((name, bool(ok)))
    print(('PASS' if ok else 'FAIL'), name)


def load(n):
    return json.load(gzip.open(D/f'{n}.json.gz'))


def raw(rec_set, key=None):
    """{label: A-layout table} for raw candidates."""
    return {r['flip']['raw']: r['table'] for r in rec_set['results']
            if r['layout'] == 'A' and r['flip'] and 'raw' in r['flip'] and (key is None or r['key'] == key)}


def lanes_from(values, base, step=16, mask=0xffffffff):
    out = []
    for v in values:
        v &= mask; d = v-base
        out.append(d//step if v and d % step == 0 and 0 <= d//step < 32 else (0 if v == 0 else None))
    return out


# 1. Gap-bit sweep: 213 flips over 53 instructions, no fault, only three with an effect.
full = load('full1')
check('full sweep complete, no fault', full['complete'] and not any(r['fault'] for r in full['results']))
import tempfile, os  # noqa: E401,E402
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as t:
    json.dump(full, t)
import io, contextlib  # noqa: E401,E402
with contextlib.redirect_stdout(io.StringIO()):
    rows = A.main(t.name)
os.unlink(t.name)
eff = sorted((r['key'], r['flip']['bit'], r['class']) for r in rows if r['class'] != 'same')
check('213 flips classified', len(rows) == 213)
check('only fmadd32 b52 (dest), fmadd32 b53 (length), fmadd16 b53 (length) have an effect',
      eff == [('fmadd16', 53, 'length'), ('fmadd32', 52, 'dest'), ('fmadd32', 53, 'length')])

# 2. 10-byte fmadd32: bits 75-79 = lane offset k on source A within 16-lane groups.
lane = raw(load('fma-lane'))
k1 = lanes_from(lane['x0801'][6], 0x5a000606)
check('k=1: lane i reads lane i-1 of A; lanes 0 and 16 read 0',
      k1 == [0, 0]+list(range(1, 15))+[0, 16]+list(range(17, 31)) or
      (k1[0] == 0 and k1[16] == 0 and all(k1[i] == i-1 for i in range(1, 32) if i != 16)))
for x, k in (('x1800', 3), ('x2800', 5), ('x3800', 7), ('x7800', 15)):
    v = lanes_from(lane[x][6], 0x5a000606)
    check(f'k={k}: lane i reads i-{k} within its 16-lane group, else 0',
          all((v[i] == i-k) if (i % 16) >= k else (v[i] == 0) for i in range(32)))
v = lanes_from(lane['x0810'][6], 0x5a000606)
check('bit 68 with k=1: lane 16 reads lane 15 (shift spans 32 lanes)', v[16] == 15 and v[0] == 0)
v = lanes_from(lane['x8000'][6], 0x5a000606)
check('k=16: every lane reads 0', all(x == 0 for x in v))
for x, size in (('x0900', 2), ('x0a00', 4)):
    v = lanes_from(lane[x][6], 0x5a000606)
    check(f'bit {72 if size == 2 else 73}: shift confined to groups of {size}',
          all(v[i] == i-1 for i in range(32) if i % size))
bcs = load('fma-lane-bc')
e1, e2 = raw(bcs, 'E1'), raw(bcs, 'E2')
check('C is not shifted (E1: A~0, result = own-lane C)', lanes_from(e1['x0801'][6], 0x5a000808) == list(range(32)))
v = lanes_from(e2['x0801'][6], 0x5a000707)
check('B is not shifted (E2: A=1.0 shifted, result = own-lane B except lanes 0/16)',
      v[0] == 0 and v[16] == 0 and all(v[i] == i for i in range(32) if i % 16))

# 3. Hazard: cross-half read of a just-written register.
hz = raw(load('fma-hazard'))
n, fl = lanes_from(hz['n0810'][6], 0x5a000707), lanes_from(hz['f0810'][6], 0x5a000707)
check('bit 68 right after the write: lane 16 gets 0; after 6 filler instructions: lane 16 gets B (A from lane 15 = 1.0)',
      n[16] == 0 and fl[16] == 16)

cr = load('fma-cross-rep')
seen = {}
for r in cr['results']:
    if r['flip']:
        lab = r['flip']['raw'].split('_')[0]
        seen.setdefault((lab, r['layout']), set()).add(r['table'][6][16])
L15 = 0x5a000606+15*16
check('cross-half read, 8 repeats each: layout A gives 0 without bit 68 and lane 15 with it; layout B (wait follows) always lane 15',
      seen[('x0800', 'A')] == {0} and seen[('x0802', 'A')] == {0} and seen[('x0810', 'A')] == {L15} and
      all(seen[(x, 'B')] == {L15} for x in ('x0800', 'x0801', 'x0802', 'x0810')))

# 4. Bit 52 (8-byte form) rule.
def rule(a, b, c):
    if b == 1.0 or a == 1.0:
        return a
    return c
for name, cases in (('fma-b52c', [(2, 3, 0), (2, 3, 1), (2, 3, 100), (1, 3, 0), (3, 1, 0), (0.5, 4, 0), (1e10, 1e10, 0), (1e10, 1e10, 5),
                                 (-2, 3, 0), (2, -3, 1), (1.5, 1.5, 0), (2, 2, 0), (4, 0.25, 0), (1e-20, 1e-20, 1)]),
                    ('fma-b52d', [(5, 1, 0), (1, 5, 0), (3, 3, 0), (1, 1, 0), (2, 1, 0), (1, 2, 0), (2, 0.5, 0), (7, 1, 0), (1, 7, 0),
                                 (-1, 3, 0), (3, -1, 0), (1, -3, 0), (0, 3, 1), (2, 3, -1), (1, 1, 5), (1.0000001, 1, 0), (1, 0.99999994, 0)])):
    r = raw(load(name))
    for i, (a, b, c) in enumerate(cases):
        got = r[f'c{i}x' if f'c{i}x' in r else f'c{i}b52'][6]
        want = struct.unpack('<f', struct.pack('<f', rule(a, b, c)))[0]
        check(f'bit 52 {(a, b, c)} -> {want} on all lanes', len(set(got)) == 1 and f32(got[0]) == want)
neg = raw(load('fma-b52d'))
check('bit 52 zero result takes the sign of A: (-1,3,0) -> -0.0, (3,-1,0) -> +0.0',
      neg['c9x'][6][0] == 0x80000000 and neg['c10x'][6][0] == 0)

# 5. fmadd16 10-byte form: same offset field; pair/quad groups read 0 outside the group.
h = raw(load('fma16-lane'))
lo = lambda t: [(x & 0xffff) for x in t[6]]
b0, b1 = lo(h['x0000']), lo(h['x0801'])
check('fmadd16 k=1: lane i gets A(i-1)+C(i) (lanes 1-29 except 16, where the f16 sum is exact); lane 0 gets C only',
      all(b1[i] == b0[i-1]-(i-1)+i for i in range(1, 30) if i != 16) and b1[0] == 0)
p = lo(h['x0900'])
check('fmadd16 bit 72 (pairs): even lanes get C only', all(p[i] == i for i in range(0, 32, 2)))

# 6. Constant-bit flips (const1): every effect is another known instruction, an intl-family alias, or a hang.
c1 = load('const1'); cb = {r['name']: r for r in c1['results']}
dec = json.load(open(D/'const1-decodes.json'))
hangs = sorted(r['name'][:-2] for r in c1['results'] if r['fault'])
check('constant flips: exactly extr b27, shlhi b26, asrh b15 (the unnamed bfi-family code b27,b26 set / b15 clear), bitop b15, wait b7 hang',
      hangs == sorted(['extr-rc27', 'shlhi-rc26', 'asrh-rc15', 'bitop-rc15', 'wait-rc7']))
FAM = {'bfi': (0, 0, 0), 'bfeil': (0, 0, 1), 'extr': (0, 1, 0), 'asr': (0, 1, 1), 'shlhi': (1, 0, 0), 'shrhi': (1, 0, 1), 'asrh': (1, 1, 1)}
ok = True
for k, code in FAM.items():
    for bit, pos in ((27, 0), (26, 1), (15, 2)):
        new = list(code); new[pos] ^= 1; new = tuple(new)
        name = next((n for n, c in FAM.items() if c == new), None)
        d = dec[f'{k}:b{bit}']
        ok &= (name is None and d is None and cb[f'{k}-rc{bit}-A']['fault']) or (d is not None and d[0] == name and not cb[f'{k}-rc{bit}-A']['fault'])
check('bfi family: bits (27, 26, 15) select bfi/bfeil/extr/asr/shlhi/shrhi/asrh; code (1,1,0) hangs', ok)
A6, B6 = cb['intl-base-A']['table'][7], cb['intl-base-A']['table'][8]
check('intl b26 = bitrev(A), b27 = popcount(A) (iunop ops with a B operand present)',
      cb['intl-rc26-A']['table'][6] == [int(f'{a:032b}'[::-1], 2) for a in A6] and cb['intl-rc27-A']['table'][6] == [bin(a).count('1') for a in A6])
check('intl b15 = convert with register mode r6l (0x0606 -> f_to_u16 rte) of B (~9e15) -> 0xffff', cb['intl-rc15-A']['table'][6] == [0xffff]*32)

ok = all(c for _, c in checks)
print(f'{sum(c for _, c in checks)}/{len(checks)} checks passed')
sys.exit(0 if ok else 1)
