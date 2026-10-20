#!/usr/bin/env python3
"""B28: does the threadgroup barrier (0x68) stop waiting for SIMD groups / lanes that have ended?
Lanes that get past the barrier(s) output 0x5e5e0000 | gid; lanes that ended early output nothing (0xcdcdcdcd) or
the skip value 0xaaaa0000 | gid. Usage: b28.py sim|gpu CASE   (CASE = p1 p2 p3 p4)"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
mov = RS.mov
e = lambda *a: agx_loop.encode(*a)
jnone = lambda n: e(f'jmp_exec_none pc+{n}', f'jmp_exec_none pc+{n}')
BAR = bytes.fromhex('6800'); STOP = bytes.fromhex('8800')
cov.install()
CASES = {'p1': (64, 64), 'p2': (64, 64), 'p3': (1024, 1024), 'p4': (32, 32)}

def body(case):
    b = mov(28, 0xaaaa0000) + e('or r2, r1, r28') + mov(28, 0x5e5e0000) + mov(27, 31)
    if case in ('p1', 'p2', 'p3'):
        # group index (gid / 32); "late" groups run the barrier section, the others skip it (p2: after one barrier)
        b += mov(26, 5) + e('asr r24, r1, r26')
        if case == 'p3':
            b += mov(26, 1) + e('and r24, r24, r26') + mov(26, 0)      # even groups run it, odd groups skip
            cond = 'ueq'
        else:
            b += mov(26, 0); cond = 'ueq'                                # group 0 runs it, group 1 skips
        if case == 'p2':
            b += BAR                                                     # every group: one common barrier first
        inner = BAR + (BAR if case == 'p2' else b'') + e('or r2, r1, r28')
        b += e(f'if_icmp r0l, {cond}, r24, r26, 1') + jnone(6 + len(inner)) + inner + e('pop_exec r0l, 1')
    else:
        # p4: lanes 16-31 stop under a partial mask; lanes 0-15 then run the barrier and set the sentinel
        b += mov(26, 15) + e('if_icmp r0l, ugt, r1, r26, 1') + STOP + e('pop_exec r0l, 1')
        b += BAR + e('or r2, r1, r28')
    return b

def main():
    mode, case = sys.argv[1], sys.argv[2]
    n, wg = CASES[case]
    bd = body(case); cov.gate(bd); code = drm.build_main(bd)
    table = [0] * 16
    if mode == 'sim':
        out, tab = cov.simulate(code, n, wg, 64, 0, table); fw = None
    else:
        import run_bench as B, gpu_safety
        gpu_safety.require_budget(1)
        try:
            out, tab, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b28/run')), code, n, wg, table, 64)
        except Exception as ex:
            gpu_safety.record(f'B28 {case}: {str(ex)[:120]}')
            print(json.dumps({'mode': mode, 'case': case, 'fault': str(ex)[:300]})); return
    lanes = out[8:8 + n]
    kinds = {}
    for i, v in enumerate(lanes):
        k = 'passed' if v == 0x5e5e0000 | i else 'skip' if v == 0xaaaa0000 | i else 'none' if v == 0xcdcdcdcd else 'other'
        kinds.setdefault(k, []).append(i)
    print(json.dumps({'mode': mode, 'case': case, 'fw_ns': fw, **{k: [len(v), v[0], v[-1]] for k, v in kinds.items()}}))
main()
