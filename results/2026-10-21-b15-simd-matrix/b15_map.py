#!/usr/bin/env python3
"""B15 step 1: the operand layout of simd_matrix_fmadd32 / fmadd16 (0x6f, bit 27) on G14C.
One SIMD group (32 lanes). Lane i loads its A, B, C pairs from table words 2i, 2i+1 (A at 0, B at 64, C at 128; for
fmadd16 the pair is the two halves of one word, so words i), runs `simd_matrix_fmadd D, A, B, C` and stores D at table
1024 + 2i (+1). Experiments: one-hot A (A slot p = 1.0, B slot j = j + 1, C = 0) for p = 0..63, which shows the row of
D and the row of B each A slot stands for, and the column pairing of B and D; and A = B = 0, C slot j = j + 1.
Gate: probe_variants with the 8-byte `fmadd32 r30, r30, r31, r29` as surrogate (agx_run runs the whole program with it
and D stays 0). Usage: b15_map.py 32|16 [--dry]"""
import json, struct, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, agx_loop, probe_variants as PV
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a); st = agx_loop.store
W = int(sys.argv[1])
N = 32
SUR = e('fmadd32 r30, r30, r31, r29')
VAR = e('simd_matrix_fmadd32 r8_r9, r12_r13, r16_r17, r20_r21' if W == 32 else 'simd_matrix_fmadd16 r8l_r8h, r12l_r12h, r16l_r16h, r20l_r20h')
f32 = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
f16 = lambda x: struct.unpack('<H', struct.pack('<e', x))[0]

import os
DINIT = int(os.environ.get('B15_DINIT', '0'), 0)   # D's value before the instruction (a sentinel shows an unwritten D)
if W == 32:
    pre = mov(8, DINIT) + mov(9, DINIT) + mov(27, 2) + e('imadd r24, r1, r27, 0')                     # r24 = 2i
    for reg, base in ((12, 0), (16, 64), (20, 128)):
        pre += mov(26, base) + e('iadd r25, r24, r26') + e(f'device_load 0, i32, xy, r{reg}_r{reg + 1}, u8_u9, r25, unsigned')
    pre += e('wait 0')
    suf = mov(26, 1024) + e('iadd r25, r24, r26') + st(8, 8, 25) + mov(26, 1025) + e('iadd r25, r24, r26') + st(9, 8, 25)
    if os.environ.get('B15_ASTORE', '1') == '1':
        suf += mov(26, 1088) + e('iadd r25, r1, r26') + st(12, 8, 25) + mov(26, 1120) + e('iadd r25, r1, r26') + st(13, 8, 25)
else:
    pre = mov(8, DINIT)
    for reg, base in ((12, 0), (16, 64), (20, 128)):
        pre += mov(26, base) + e('iadd r25, r1, r26') + e(f'device_load 0, i32, x, r{reg}, u8_u9, r25, unsigned')
    pre += e('wait 0')
    suf = mov(26, 1024) + e('iadd r25, r1, r26') + st(8, 8, 25)
import os
GAP = int(os.environ.get('B15_GAP', '0'))      # independent movs between the instruction and the first read of D
suf = b''.join(mov(28 + (i % 2), i) for i in range(GAP)) + suf + e('wait 0') + e('iadd r2, r8, 0')

def table(a, b, c):
    t = [0] * 1024 + [0x5a5a5a5a] * 176      # readback region pre-filled: an unlanded store shows 0x5a5a5a5a
    if W == 32:
        for j in range(64): t[j], t[64 + j], t[128 + j] = f32(a[j]), f32(b[j]), f32(c[j])
    else:
        for i in range(32):
            t[i] = f16(a[2 * i]) | f16(a[2 * i + 1]) << 16
            t[64 + i] = f16(b[2 * i]) | f16(b[2 * i + 1]) << 16
            t[128 + i] = f16(c[2 * i]) | f16(c[2 * i + 1]) << 16
    return t

def dvals(tab):
    if W == 32:
        return [struct.unpack('<f', struct.pack('<I', tab[1024 + q]))[0] for q in range(64)]
    return [struct.unpack('<e', struct.pack('<H', tab[1024 + q // 2] >> (16 * (q % 2)) & 0xffff))[0] for q in range(64)]

zero_d = lambda out, tab: all(tab[1024 + q] in (DINIT,) for q in range(64 if W == 32 else 32))
exps = {}
for p in range(64):
    a = [0.0] * 64; a[p] = 1.0
    exps[f'a{p}'] = table(a, [j + 1.0 for j in range(64)], [float(os.environ.get('B15_C', '0'))] * 64)
exps['c'] = table([0.0] * 64, [0.0] * 64, [j + 1.0 for j in range(64)])
probes = [PV.Probe(f'mma{W}_{k}', pre, SUR, VAR, suf, int.from_bytes(SUR, 'little') ^ int.from_bytes(VAR, 'little'),
                   N, N, 48, t, zero_d) for k, t in exps.items()]
if os.environ.get('B15_ARITH'):            # B15_ARITH=SETS: random A, B, C (seeded), save the operands and D
    import random, gpu_safety, run_bench as B, run_drm_compute as drm
    p = probes[0]; PV.check(p); gpu_safety.require_budget(1)
    R = B.Runner(Path('/scratch/agxsim-runs/b15/arith')); code = drm.build_main(p.body(p.variant))
    rng = random.Random(15); sets = []
    def val(kind):
        q = (lambda x: x) if W == 32 else (lambda x: struct.unpack('<e', struct.pack('<e', x))[0])   # exact in the operand type
        if kind == 0: return q(rng.uniform(-1, 1))
        if kind == 1: return q(rng.choice([-1, 1]) * rng.uniform(1, 2) * 2.0 ** (rng.randint(-20, 20) if W == 32 else rng.randint(-6, 6)))
        if W == 32:
            return rng.choice([1.0, -1.0, 2.0 ** -24, 1.0 + 2.0 ** -23, 3.0, 2.0 ** 24, -(2.0 ** 24), 0.5]) * (1 + rng.randint(0, 3) * 2.0 ** -22)
        return q(rng.choice([1.0, -1.0, 2.0 ** -11, 1.0 + 2.0 ** -10, 3.0, 2.0 ** 10, -(2.0 ** 10), 0.5]) * (1 + rng.randint(0, 3) * 2.0 ** -9))
    for k in range(int(os.environ['B15_ARITH'])):
        kind = k % 3
        a, b, c = ([val(kind) for _ in range(64)] for _ in range(3))
        t = table(a, b, c)
        tab = RS.run(R, code, p.n, p.wg, t, p.regs)[1]
        rnd = lambda xs: [struct.unpack('<f', struct.pack('<I', w))[0] for w in xs] if W == 32 else None
        sets.append({'a': [t[j] for j in range(64)] if W == 32 else t[0:32], 'b': t[64:128] if W == 32 else t[64:96],
                     'c': t[128:192] if W == 32 else t[128:160], 'd': tab[1024:1088] if W == 32 else tab[1024:1056]})
    Path(f'arith{W}.json').write_text(json.dumps(sets) + '\n'); print(json.dumps({'sets': len(sets)})); sys.exit(0)
if os.environ.get('B15_HAZARD'):           # B15_HAZARD=REPS: run probe a5 REPS times, count all-zero D readbacks
    import gpu_safety, run_bench as B, run_drm_compute as drm
    p = next(x for x in probes if x.name.endswith('_a5')); PV.check(p); gpu_safety.require_budget(1)
    R = B.Runner(Path('/scratch/agxsim-runs/b15/hazard'))
    code = drm.build_main(p.body(p.surrogate if os.environ.get('B15_SURROGATE') else p.variant))
    ds = [dvals(RS.run(R, code, p.n, p.wg, p.table, p.regs)[1]) for _ in range(int(os.environ['B15_HAZARD']))]
    good = ds[0] if ds[0].count(0.0) < 64 else next((d for d in ds if d.count(0.0) < 64), None)
    raw = [RS.run(R, code, p.n, p.wg, p.table, p.regs)[1][1024:1152] for _ in range(int(os.environ.get('B15_RAW', '0')))]
    from collections import Counter
    for t, c in Counter(tuple(t) for t in raw).most_common():
        print(c, 'runs: D', [f'{w:x}' for w in t[:8]], '... D[16:20]', [f'{w:x}' for w in t[16:20]], '| A lanes 0-3 slot0', [f'{w:x}' for w in t[64:68]], 'slot1', [f'{w:x}' for w in t[96:100]])
    print(json.dumps({'stores_missing_runs': sum(all(w == 0x5a5a5a5a for w in t[:64]) for t in raw), 'unwritten_raw_runs': sum(all(w == DINIT for w in t[:64]) for t in raw), 'zero_raw_runs': sum(all(w == 0 for w in t[:64]) for t in raw), 'other_raw': sorted({tuple(t) for t in raw}.__len__() for _ in [0]), 'raw_runs': len(raw)}))
    print(json.dumps({'gap': GAP, 'runs': len(ds), 'all_zero': sum(d.count(0.0) == 64 for d in ds),
                      'other_wrong': sum(d != good and d.count(0.0) < 64 for d in ds)})); sys.exit(0)
recs = PV.run(probes, Path(f'/scratch/agxsim-runs/b15/map{W}'), dry='--dry' in sys.argv)
res = {r['name']: {'deterministic': r['deterministic'], 'd': dvals(r['table_after'])} for r in recs}
if recs:
    Path(f'map{W}.json').write_text(json.dumps(res) + '\n')
    for k in list(res)[:3] + [f'mma{W}_c']:
        print(k, res[k]['deterministic'], res[k]['d'])
