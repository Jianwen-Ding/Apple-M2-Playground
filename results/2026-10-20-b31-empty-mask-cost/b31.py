#!/usr/bin/env python3
"""B31: cost of instructions issued with an empty execution mask. One SIMD group runs T trips of a counted loop
(agx_loop shape); each trip holds an if whose body is K copies of one instruction class:
  base   - no if at all;  empty - if never true, body issued with no active lane (no jump);
  skip   - same with Mesa's jmp_exec_none over the body;  active - if true for every lane.
Prints the firmware time (min of R runs) and, for stores, whether the masked-off stores wrote anything.
Usage: b31.py sim|gpu CLASS K MODE [T] [R]"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
from run_drm_tg_layout import tg
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a); jnone = lambda n: e(f'jmp_exec_none pc+{n}', f'jmp_exec_none pc+{n}')
CLS = {
    'iadd': lambda: e('iadd r10, r10, 1'),
    'fmadd32': lambda: e('fmadd32 r11, r11, r12, r13'),
    'load': lambda: e('device_load 0, i32, x, r14, u8_u9, r5, unsigned') + e('wait 0'),
    'store': lambda: agx_loop.store(15, 8, 6),
    'tgload': lambda: tg(True, 'i32', 16, base=22) + e('wait 0'),
    'shuffle': lambda: e('simd_shuffle r17, r17, r18l'),
}

def body(cls, k, mode, trips):
    b = mov(3, 0) + mov(4, trips) + mov(5, 0) + mov(22, 0) + mov(29, 0xffffffff) + mov(10, 0) + mov(11, 0) + mov(12, 0x3f800000)
    b += mov(13, 0x3f800000) + mov(17, 0) + mov(18, 1) + mov(26, 1000) + e('iadd r6, r1, r26') + mov(15, 0x77777777)
    inner = CLS[cls]() * k
    if mode == 'base': trip = b''
    elif mode == 'active': trip = mov(27, 1000) + e('if_icmp r0l, ult, r1, r27, 1') + inner + e('pop_exec r0l, 1')
    else:
        trip = e('if_icmp r0l, ueq, r1, r29, 1') + (jnone(6 + len(inner)) if mode == 'skip' else b'') + inner + e('pop_exec r0l, 1')
    loop = trip + e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
    b += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + loop
    b += e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}') + e('pop_exec r0l, 1')
    return b + e('iadd r2, r3, 0')

def main():
    mode_run, cls, k, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    trips = int(sys.argv[5]) if len(sys.argv) > 5 else 20000
    reps = int(sys.argv[6]) if len(sys.argv) > 6 else 5
    t = [0x01010101] * 2048
    bd = body(cls, k, mode, trips); cov.gate(bd); code = drm.build_main(bd)
    if mode_run == 'sim':
        out, tab = cov.simulate(code, 32, 32, 64, 1024, t); fws = [None]
    else:
        import run_bench as B, gpu_safety; gpu_safety.require_budget(1)
        fws = []
        for _ in range(reps):
            out, tab, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b31/run')), code, 32, 32, t, 64, 1024); fws.append(fw)
    stored = sum(tab[1000 + i] == 0x77777777 for i in range(32))
    print(json.dumps({'mode': mode_run, 'class': cls, 'k': k, 'variant': mode, 'trips': trips, 'out_ok': all(x == trips for x in out[8:40]),
                      'fw_ns_min': min(fws) if fws[0] is not None else None, 'stores_landed': stored}))
main()
