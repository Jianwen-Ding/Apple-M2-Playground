#!/usr/bin/env python3
"""B4: forward progress inside a SIMD group. Spinners run a loop of exactly N trips that loads the flag word
(table word 0) and records in r12 the first trip on which it was nonzero (0xffffffff = never). Writers, in the
other branch of the same if/else, store 1 to the flag. Every lane outputs r12. The loop never exits early, so the
program terminates whatever the scheduling is. Usage: b4.py sim|gpu VARIANT N"""
import json, sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
mov = RS.mov
e = lambda *a: agx_loop.encode(*a)
cov.install()

def body(variant, n):
    b = mov(12, 0xffffffff) + mov(28, 0xffffffff) + mov(3, 0) + mov(4, n) + mov(5, 0) + mov(15, 1) + mov(27, 0)
    cond = {'spin_if_lane0': 'ueq', 'spin_else_lane0': 'ugt', 'spin_if_lanes1_31': 'ugt'}[variant]
    spinner_first = variant in ('spin_if_lane0', 'spin_if_lanes1_31')
    spin = e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    loop = e('device_load 0, i32, x, r11, u8_u9, r5, unsigned') + e('wait 0')
    loop += e('icmpsel ueq, r13, r12, r28, r3, r12')          # r13 = (r12 == never) ? trip : r12
    loop += e('icmpsel ueq, r12, r11, r27, r12, r13')         # r12 = (flag == 0) ? r12 : r13
    loop += e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
    spin += loop + e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}') + e('pop_exec r0l, 1')
    write = agx_loop.store(15, 8, 5) + e('wait 0')
    first, second = (spin, write) if spinner_first else (write, spin)
    b += e(f'if_icmp r0l, {cond}, r1, r27, 1') + first + e('else_fcmp r0l, eq, 0.0, 0.0, 1') + second + e('pop_exec r0l, 1')
    return b + e('iadd r2, r12, 0')

def main():
    mode, variant, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    bd = body(variant, n); cov.gate(bd)
    code = drm.build_main(bd)
    table = [0] * 64
    if mode == 'sim':
        out, tab = cov.simulate(code, 32, 32, 32, 0, table)
    else:
        import run_bench as B, gpu_safety
        gpu_safety.require_budget(1)
        out, tab, fw, _ = RS.run(B.Runner(__import__('pathlib').Path('/scratch/agxsim-runs/b4/run')), code, 32, 32, table, 32)
    lanes = out[8:40]
    print(json.dumps({'mode': mode, 'variant': variant, 'n': n, 'lane0': lanes[0], 'lanes1_31': sorted(set(lanes[1:])),
                      'flag': tab[0], 'fw_ns': None if mode == 'sim' else fw}))
main()
