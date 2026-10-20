#!/usr/bin/env python3
"""B33, threadgroup memory: 4 KiB (1,024 words). load2/load4: every lane fills words 32i..32i+31 with 0xc0000000 | w,
barrier, then an n-wide threadgroup_load at byte base 4 * idx_i (idx_i = 16 (i % 16) + i % 4 ... see idx), copying the
components to device table[3072 + 4i + c]. store2/store4: an n-wide threadgroup_store of 0xb0000000 | 4i + c at idx_i,
barrier, then lane i copies tg words 32i..32i+31 to device table[8192 + w]. Usage: b33tg.py sim|gpu CASE"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
from run_drm_tg_layout import tg
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a); st = agx_loop.store
N = 32
def idx(i): return 32 * i + i % 4 if 32 * i + i % 4 + 4 <= 1024 else 0
BAR = bytes.fromhex('6800')

def body(case):
    n = 4 if '4' in case else 2; m = (1 << n) - 1
    b = mov(26, 128) + e('imadd r22, r1, r26, 0') + mov(28, 4)          # r22 = byte 128 i (lane's 32 words)
    b += mov(26, 32) + e('imadd r23, r1, r26, 0')                         # r23 = word 32 i
    if case.startswith('load'):
        for k in range(32):                                               # fill: word 32i + k = 0xc0000000 | (32i + k)
            b += mov(26, 0xc0000000 + k) + e('iadd r9, r23, r26') + tg(False, 'i32', 9, base=22) + e('iadd r22, r22, r28')
        b += e('wait 0') + BAR
        b += mov(26, 4000) + e('iadd r6, r1, r26') + e('device_load 0, i32, x, r5, u8_u9, r6, unsigned') + e('wait 0')
        b += mov(26, 4) + e('imadd r24, r5, r26, 0')                      # byte address
        b += tg(True, 'i32', 12, base=24, mask=m) + e('wait 0')
        b += mov(27, 3072) + e('imadd r20, r1, r26, r27')
        for c in range(n):
            b += st(12 + c, 8, 20) + mov(27, 1) + e('iadd r20, r20, r27')
    else:
        b += mov(26, 4000) + e('iadd r6, r1, r26') + e('device_load 0, i32, x, r5, u8_u9, r6, unsigned') + e('wait 0')
        b += mov(26, 4) + e('imadd r24, r5, r26, 0')
        for c in range(n):
            b += mov(26, 0xb0000000 | c) + mov(27, 4) + e(f'imadd r{12 + c}, r1, r27, r26')
        b += tg(False, 'i32', 12, base=24, mask=m) + e('wait 0') + BAR
        b += mov(27, 8192) + e('iadd r20, r23, r27')
        for k in range(32):
            b += tg(True, 'i32', 9, base=22) + e('wait 0') + st(9, 8, 20) + e('iadd r22, r22, r28') + mov(27, 1) + e('iadd r20, r20, r27')
    return b + e('wait 0') + e('iadd r2, r1, 0')

def main():
    mode, case = sys.argv[1], sys.argv[2]
    n = 4 if '4' in case else 2
    t = [0] * 12000
    for i in range(N): t[4000 + i] = idx(i)
    bd = body(case); cov.gate(bd); code = drm.build_main(bd)
    if mode == 'sim':
        out, tab = cov.simulate(code, N, N, 64, 4096, t)
    else:
        import run_bench as B, gpu_safety; gpu_safety.require_budget(1)
        out, tab, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b33/run')), code, N, N, t, 64, 4096)
    if case.startswith('load'):
        got = [[tab[3072 + 4 * i + c] for c in range(n)] for i in range(N)]
        byte = sum(got[i] == [0xc0000000 | (idx(i) + c) for c in range(n)] for i in range(N))
        down = sum(got[i] == [0xc0000000 | ((idx(i) & ~(n - 1)) + c) for c in range(n)] for i in range(N))
    else:
        mem = tab[8192:8192 + 1024]
        byte = sum(all(mem[idx(i) + c] == 0xb0000000 | (4 * i + c) for c in range(n)) for i in range(N))
        down = sum(all(mem[(idx(i) & ~(n - 1)) + c] == 0xb0000000 | (4 * i + c) for c in range(n)) for i in range(N))
    print(json.dumps({'mode': mode, 'case': 'tg_' + case, 'byte_model': byte, 'rounded_model': down}))
main()
