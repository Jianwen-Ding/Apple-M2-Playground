#!/usr/bin/env python3
"""B28 extra: one 1,024-thread threadgroup declaring 64 KiB of threadgroup memory uses all of it. Thread i stores
0x7e000000|i at byte 64i and 0x7f000000|i at byte 64i+60 (up to byte 65,532); after the barrier it reads both words of
thread (i+1) % 1024 and outputs their sum = 0xfd000000 + 2j. Usage: tg64k.py sim|gpu"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
from run_drm_tg_layout import tg
mov = RS.mov
e = lambda *a: agx_loop.encode(*a)
cov.install()
N = 1024
b = mov(28, 0x7e000000) + e('or r6, r1, r28') + mov(28, 0x7f000000) + e('or r7, r1, r28')
b += mov(26, 64) + e('imadd r22, r1, r26, 0') + mov(26, 60) + e('iadd r23, r22, r26')
b += tg(False, 'i32', 6, base=22) + tg(False, 'i32', 7, base=23) + e('wait 0') + bytes.fromhex('6800')
b += mov(26, 1) + e('iadd r20, r1, r26') + mov(26, 1023) + e('and r20, r20, r26')
b += mov(26, 64) + e('imadd r22, r20, r26, 0') + mov(26, 60) + e('iadd r23, r22, r26')
b += tg(True, 'i32', 8, base=22) + tg(True, 'i32', 9, base=23) + e('wait 0') + e('iadd r2, r8, r9')
cov.gate(b); code = drm.build_main(b)
mode = sys.argv[1]
if mode == 'sim':
    out, _ = cov.simulate(code, N, N, 64, 65536, [0] * 16); fw = None
else:
    import run_bench as B, gpu_safety
    gpu_safety.require_budget(1)
    out, _, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b28tg/run')), code, N, N, [0] * 16, 64, 65536)
bad = sum(out[8 + i] != (0xfd000000 + 2 * ((i + 1) % N)) & 0xffffffff for i in range(N))
print(json.dumps({'mode': mode, 'bad': bad, 'first': hex(out[8]), 'last': hex(out[8 + N - 1]), 'fw_ns': fw}))
