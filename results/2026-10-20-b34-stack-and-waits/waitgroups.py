#!/usr/bin/env python3
"""B34 wait groups: r20 = sentinel; a cold device_load (lane-distinct word 1M + 4096 i, never touched) into r20 in
group S; a warm load (word 0, loaded earlier) into r11 in group F; `wait F`; r2 = r20 (read before any wait for S);
then `wait S` and r21 = r20 -> table[2048 + i]. Output r2 == sentinel means `wait F` did not wait for group S.
Usage: waitgroups.py sim|gpu SLOW_GROUP"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
slow = int(sys.argv[2]); fast = 1 - slow
N = 32; FAR = 1 << 20
b = mov(5, 0) + e('device_load 0, i32, x, r11, u8_u9, r5, unsigned') + e('wait 0')            # warm word 0
b += mov(26, 4096) + mov(27, FAR) + e('imadd r6, r1, r26, r27') + mov(20, 0xdead0000)
b += e(f'device_load {slow}, i32, x, r20, u8_u9, r6, unsigned') + e(f'device_load {fast}, i32, x, r11, u8_u9, r5, unsigned')
b += e(f'wait {fast}') + e('iadd r2, r20, 0') + e(f'wait {slow}')
b += mov(26, 2048) + e('iadd r7, r1, r26') + agx_loop.store(20, 8, 7) + e('wait 0')
cov.gate(b); code = drm.build_main(b)
t = [0] * (FAR + 4096 * N + 16)
t[0] = 0x0000beef
for i in range(N): t[FAR + 4096 * i] = 0xc0de0000 | i
if sys.argv[1] == 'sim':
    out, tab = cov.simulate(code, N, N, 64, 0, t)
else:
    import run_bench as B, gpu_safety; gpu_safety.require_budget(1)
    out, tab, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b34/run')), code, N, N, t, 64)
early = out[8:8 + N]; late = tab[2048:2048 + N]
print(json.dumps({'mode': sys.argv[1], 'slow_group': slow, 'wait': fast,
                  'read_after_wait_other_group': {'sentinel': sum(x == 0xdead0000 for x in early), 'loaded': sum(early[i] == 0xc0de0000 | i for i in range(N))},
                  'after_own_wait_loaded': sum(late[i] == 0xc0de0000 | i for i in range(N))}))
