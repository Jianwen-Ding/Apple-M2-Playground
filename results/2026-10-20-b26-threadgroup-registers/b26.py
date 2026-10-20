#!/usr/bin/env python3
"""B26: one threadgroup of WG threads with HALVES register halves declared; every thread writes gid ^ 0x3c3c0000 into
its highest register r<HALVES/2 - 1> and copies it to the output. Usage: b26.py sim|gpu WG HALVES"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
mov = RS.mov
e = lambda *a: agx_loop.encode(*a)
cov.install()
mode, wg, halves = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
top = halves // 2 - 1
BAR = len(sys.argv) > 4 and sys.argv[4] == 'barrier'
b = mov(28, 0x3c3c0000) + e(f'xor r{top}, r1, r28') + e('wait 0') + (bytes.fromhex('6800') if BAR else b'') + e(f'iadd r2, r{top}, 0')
cov.gate(b); code = drm.build_main(b)
if mode == 'sim':
    out, _ = cov.simulate(code, wg, wg, halves, 0, [0] * 16); fw = None
else:
    import run_bench as B, gpu_safety
    gpu_safety.require_budget(1)
    try:
        out, _, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b26/run')), code, wg, wg, [0] * 16, halves)
    except Exception as ex:
        gpu_safety.record(f'B26 wg={wg} halves={halves}: {str(ex)[:100]}')
        print(json.dumps({'mode': mode, 'wg': wg, 'halves': halves, 'fault': str(ex)[:300]})); sys.exit()
bad = sum(out[8 + i] != i ^ 0x3c3c0000 for i in range(wg))
none = sum(out[8 + i] == 0xcdcdcdcd for i in range(wg))
print(json.dumps({'barrier': BAR, 'mode': mode, 'wg': wg, 'halves': halves, 'top_reg': top, 'bad': bad, 'not_written': none, 'fw_ns': fw}))
