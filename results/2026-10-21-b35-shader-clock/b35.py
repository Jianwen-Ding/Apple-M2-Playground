#!/usr/bin/env python3
"""B35: is any special register a clock? For each selector 0..255 one 32-lane dispatch reads it into r6, runs the
counted delay loop of TRIPS trips (8 fmuls each; checked in agx_run), reads it again into r7 and stores r6 at table[gid], r7 at
table[64 + gid]. Usage: b35.py sim|gpu [TRIPS]. Every selector's get_sr was recorded safe by safe-06 (0 faults)."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
sys.path.insert(0, '/save/workspace/apple-documentation-playground/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
import run_drm_sr_scan as scan   # get_sr encoder only
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a); st = agx_loop.store
N = 32

def delay(trips):
    # counted loop (B5's shape): r3 = trip, r4 = trips, 8 dependent fmuls per trip
    loop = b''.join(e('fmul32 r9, r9, r10') for _ in range(8)) + e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
    b = mov(3, 0) + mov(4, trips) + mov(9, 0x3f800000) + mov(10, 0x3f800000)
    b += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + loop
    b += e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}') + e('pop_exec r0l, 1')
    return b

def body(sel, trips):
    b = scan.get_sr(sel, 6) + delay(trips) + scan.get_sr(sel, 7)
    b += st(6, 8, 1) + mov(26, 64) + e('iadd r20, r1, r26') + st(7, 8, 20) + e('wait 0') + e('xor r2, r6, r7')
    return b

def main():
    mode = sys.argv[1]; trips = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    assert trips <= 20000
    os.environ.setdefault('AGX_SR_DEFAULT', '0')
    res = {'mode': mode, 'trips': trips, 'changed': {}, 'values': {}}
    if mode == 'gpu':
        import run_bench as B, gpu_safety
        gpu_safety.require_budget(1); R = B.Runner(Path('/scratch/agxsim-runs/b35/run'))
    sels = [int(x) for x in os.environ['B35_SELS'].split(',')] if 'B35_SELS' in os.environ else (range(256) if mode == 'gpu' else (0, 20, 80, 113))
    for sel in sels:
        bd = body(sel, trips); cov.gate(bd); code = drm.build_main(bd)
        if mode == 'sim':
            out, tab = cov.simulate(code, N, N, 32, 0, [0] * 128)
        else:
            out, tab, fw, _ = RS.run(R, code, N, N, [0] * 128, 32)
            res.setdefault('fw_ns', {})[sel] = fw
        a, b = tab[0:N], tab[64:64 + N]
        res['values'][sel] = sorted(set(a))[:4]
        if a != b:
            res['changed'][sel] = {'before': [f'{v:x}' for v in a[:4]], 'after': [f'{v:x}' for v in b[:4]]}
            print('CHANGED', sel, res['changed'][sel], flush=True)
    print(json.dumps({'mode': mode, 'changed': list(res['changed']), 'nonzero': {k: v for k, v in res['values'].items() if v != [0]}}))
    Path(f'{mode}.json').write_text(json.dumps(res) + '\n')

if __name__ == '__main__':
    main()
