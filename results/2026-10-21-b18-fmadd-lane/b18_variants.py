#!/usr/bin/env python3
"""B18: the six lane-offset fmadd forms agx_run refuses to model (segments with k >= 2, and fmadd32 in the segment
modes, where a group's first lanes read outside it), run through probe_variants: the surrogate is the same instruction in the default mode with k = 1, which
agx_run models and the GPU has run; only the k and mode fields differ. Lane i loads A = i + 1 (f32 or f16), then
`fmadd_lane r14, r6, r7 = 1.0, r8 = 0` and r2 = r14: the result names the lane each lane read (0 = none).
Usage: b18_variants.py [--dry]"""
import json, struct, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, agx_loop, probe_variants as PV
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
N = 64
CASES = [  # (width, k bits, mode bits): the six forms coverage.py could not gate; surrogate: default mode, k = 1
    (32, '0b00001', '0b01000000000'), (32, '0b00010', '0b01000000000'), (32, '0b00011', '0b01000000000'),
    (16, '0b00010', '0b01000000000'), (16, '0b00011', '0b01000000000'), (32, '0b00001', '0b00100000000'),
]
def ins(w, k, mode):
    return f'fmadd32_lane r14, r6, r7, r8, {k}, {mode}, 0b0' if w == 32 else f'fmadd16_lane r14l, r6l, r7l, r8l, {k}, {mode}, 0b0'
def f16(x): return struct.unpack('<H', struct.pack('<e', x))[0]
def f32(x): return struct.unpack('<I', struct.pack('<f', x))[0]

probes = []
for w, k, mode in CASES:
    sk, smode = '0b00001', '0b00000000000'
    one, zero = (f32(1.0), 0) if w == 32 else (f16(1.0), 0)
    table = [f32(i + 1) if w == 32 else f16(i + 1) for i in range(N)]
    pre = e('device_load 0, i32, x, r6, u8_u9, r1, unsigned') + e('wait 0') + mov(7, one) + mov(8, zero) + mov(14, 0)
    suf = e('iadd r2, r14, 0')
    sur, var = e(ins(w, sk, smode)), e(ins(w, k, mode))
    allowed = int.from_bytes(sur, 'little') ^ int.from_bytes(var, 'little')
    name = f'fmadd{w}_lane_k{int(k, 2)}_mode{mode}'
    probes.append(PV.Probe(name, pre, sur, var, suf, allowed, N, N, 32, table,
                           lambda out, tab: all(out[8 + i] != 0xcdcdcdcd for i in range(N))))
recs = PV.run(probes, Path('/scratch/agxsim-runs/b18-variants'), dry='--dry' in sys.argv)
res = {}
for r in recs:
    w = 32 if 'fmadd32' in r['name'] else 16
    lanes = []
    for i in range(N):
        v = r['out'][8 + i]
        x = struct.unpack('<f', struct.pack('<I', v))[0] if w == 32 else struct.unpack('<e', struct.pack('<H', v & 0xffff))[0]
        lanes.append(int(x) - 1 if x == x and x >= 1 else None)
    res[r['name']] = {'deterministic': r['deterministic'], 'source_lane': lanes[:32]}
    print(r['name'], r['deterministic'], lanes[:32])
if recs: Path('variants.json').write_text(json.dumps(res, indent=0) + '\n')
