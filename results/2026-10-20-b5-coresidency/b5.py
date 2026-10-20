#!/usr/bin/env python3
"""B5: co-residency across workgroups. W workgroups of 32 threads; lane 0 of each atomically adds 1 to a counter
(table word 0), then runs exactly N trips reading the counter with a returning atomic add of 0 and records the first
trip on which it reached W (0xffffffff = never). Lanes 1-31 do nothing. Bounded: the loop never exits early.
Usage: b5.py sim|gpu W N"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop, run_drm_atomic as DA
mov = RS.mov
e = lambda *a: agx_loop.encode(*a)
cov.install()
import os
WGT = int(os.environ.get('B5_WG', 32))   # threads per workgroup; W counts SIMD groups
REGS = int(os.environ.get('B5_REGS', 64))   # r0..r29 = 60 halves; an under-declared count lets SIMD groups on one core overwrite each other

def body(w, n):
    b = mov(12, 0xffffffff) + mov(28, 0xffffffff) + mov(3, 0) + mov(4, n) + mov(5, 0) + mov(15, 1) + mov(16, 0)
    b += mov(29, w) + mov(27, 31) + e('and r24, r1, r27') + mov(27, 0)
    b += e('if_icmp r0l, ueq, r24, r27, 1')
    b += DA.atomic(0, 14, 5, 15, True) + e('wait 0')
    loop = DA.atomic(0, 11, 5, 16, True) + e('wait 0')
    loop += e('icmpsel ueq, r13, r12, r28, r3, r12')          # r13 = (never) ? trip : r12
    loop += e('icmpsel ult, r12, r11, r29, r12, r13')         # r12 = (counter < W) ? r12 : r13
    loop += e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
    b += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + loop
    b += e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}') + e('pop_exec r0l, 1')
    b += e('pop_exec r0l, 1')
    return b + e('iadd r2, r12, 0')

def main():
    mode, w, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    bd = body(w, n); cov.gate(bd)
    code = drm.build_main(bd)
    table = [0] * 64
    if mode == 'sim':
        out, tab = cov.simulate(code, 32 * w, WGT, REGS, 0, table); fw = None
    else:
        import run_bench as B, gpu_safety
        gpu_safety.require_budget(1)
        out, tab, fw, _ = RS.run(B.Runner(Path("/scratch/agxsim-runs/b5/run")), code, 32 * w, WGT, table, REGS)
    l0 = [out[8 + 32 * k] for k in range(w)]
    seen = [x for x in l0 if x != 0xffffffff]
    if '-v' in sys.argv: print('tab0..8', [hex(x) for x in tab[:8]], 'lane0 sample', [hex(x) for x in l0[:6]], [hex(x) for x in l0[-4:]], 'out[:10]', [hex(x) for x in out[:10]])
    print(json.dumps({'wg': WGT, 'regs': REGS, 'mode': mode, 'W': w, 'n': n, 'counter': tab[0], 'saw_W': len(seen), 'never': w - len(seen),
                      'max_trip': max(seen) if seen else None, 'fw_ns': fw}))
main()
