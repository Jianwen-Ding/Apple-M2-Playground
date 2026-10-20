#!/usr/bin/env python3
"""B16: does the 0x78 block barrier (7809) complete with partial blocks and in divergent control flow?
Every lane outputs 0x5e5e0000 | gid after the barrier (or 0xaaaa0000 | gid if it skipped it).
q1: 64 threads (2 groups, half a block); q2: 96 threads (3 groups); q3: 128 threads, groups 0-1 reach 7809 in the if,
groups 2-3 in the else (two instruction addresses); q4: 128 threads, only odd lanes of each group execute 7809.
Usage: b16.py sim|gpu CASE"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
B78 = bytes.fromhex('7809')
SUR = bytes.fromhex('6800')   # 2-byte 0x68 barrier: the simulator gate runs the identical program with it (it cannot decode 7809)
CASES = {'q1': 64, 'q2': 96, 'q3': 128, 'q4': 128}
def body(case):
    b = mov(28, 0x5e5e0000) + mov(29, 0xaaaa0000) + e('or r2, r1, r29')
    if case in ('q1', 'q2'):
        b += B78 + e('or r2, r1, r28')
    elif case == 'q3':
        b += mov(26, 6) + e('asr r24, r1, r26') + mov(26, 0)     # gid / 64: groups 0-1 vs 2-3
        b += e('if_icmp r0l, ueq, r24, r26, 1') + B78 + e('or r2, r1, r28') + e('else_fcmp r0l, eq, 0.0, 0.0, 1') + B78 + e('or r2, r1, r28') + e('pop_exec r0l, 1')
    else:
        b += mov(26, 1) + e('and r24, r1, r26') + e('if_icmp r0l, ueq, r24, r26, 1') + B78 + e('or r2, r1, r28') + e('pop_exec r0l, 1')
    return b
mode, case = sys.argv[1], sys.argv[2]; n = CASES[case]
bd = body(case); gate = bd.replace(B78, SUR); assert len(gate) == len(bd); cov.gate(gate)
sim_code = drm.build_main(gate); code = drm.build_main(bd)
if mode == 'sim':
    out, _ = cov.simulate(sim_code, n, n, 32, 0, [0] * 16); fw = None
else:
    import run_bench as B, gpu_safety; gpu_safety.require_budget(1)
    try:
        out, _, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b16/run')), code, n, n, [0] * 16, 32)
    except Exception as ex:
        gpu_safety.record(f'B16 {case}: {str(ex)[:100]}')
        print(json.dumps({'mode': mode, 'case': case, 'fault': str(ex)[-300:]})); sys.exit()
lanes = out[8:8 + n]
print(json.dumps({'mode': mode, 'case': case, 'threads': n, 'fw_ns': fw, 'passed': sum(lanes[i] == 0x5e5e0000 | i for i in range(n)),
                  'skipped': sum(lanes[i] == 0xaaaa0000 | i for i in range(n))}))
