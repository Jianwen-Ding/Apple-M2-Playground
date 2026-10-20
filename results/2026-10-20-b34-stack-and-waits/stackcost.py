#!/usr/bin/env python3
"""B34 timing: one SIMD group, Mesa's `stack_adjust #80`, then a counted loop of T trips whose body is 16 of:
  stack_dep    stack_load r10 at byte offset r10 (r10 = 0 = the stored value) + wait 0   (dependent chain)
  stack_indep  stack_load r10..r25 at offsets 0..60, one wait 0
  stack_store  stack_store r9 at offsets 0..60, then wait 0
  dev_dep      device_load r10 = table[r10] (L1 hit, word 0 = 0) + wait 0
  dev_indep    device_load r10..r25 = table[0..15], one wait 0
  none         (empty body)
Runs through drm_compute with Mesa's helper and 80 scratch dwords; prints min firmware ns over REPS.
Usage: stackcost.py sim|gpu KIND [T] [REPS]"""
import json, os, struct, subprocess, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
ADJ = bytes.fromhex('b500010525800000')
def body(kind, trips):
    b = mov(3, 0) + mov(4, trips) + mov(5, 0) + mov(9, 0) + mov(10, 0)
    b += e('stack_store i32, 1, 0, x, 4, r9, 0, 0') + e('wait 0')
    k = {'stack_dep': (e('stack_load r10, i32, 1, 0, x, 4, r10, 0') + e('wait 0')) * 16,
         'stack_indep': b''.join(e(f'stack_load r{10 + j}, i32, 1, 0, x, 4, {4 * j}, 0') for j in range(16)) + e('wait 0'),
         'stack_store': b''.join(e(f'stack_store i32, 1, 0, x, 4, r9, {4 * j}, 0') for j in range(16)) + e('wait 0'),
         'dev_dep': (e('device_load 0, i32, x, r10, u8_u9, r10, unsigned') + e('wait 0')) * 16,
         'dev_indep': b''.join(mov(26, j) + e(f'device_load 0, i32, x, r{10 + j}, u8_u9, r26, unsigned') for j in range(16)) + e('wait 0'),
         'none': b''}[kind]
    loop = k + e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
    b += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + loop
    b += e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}') + e('pop_exec r0l, 1')
    return b + e('iadd r2, r3, 0')

kind = sys.argv[2]; trips = int(sys.argv[3]) if len(sys.argv) > 3 else 20000; reps = int(sys.argv[4]) if len(sys.argv) > 4 else 7
bd = body(kind, trips); cov.gate(bd)
code = ADJ + drm.build_main(bd)
if sys.argv[1] == 'sim':
    small = ADJ + drm.build_main(body(kind, 50))
    r = subprocess.run(['/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_run', '/dev/stdin', '--grid', '32', '--wg', '32',
                        '--regs', '64', '--alloc', '0x100000=512', '--alloc', '0x200000=256', '--uniform', '4=0', '--uniform', '5=32',
                        '--uniform', '6=0x100000', '--uniform', '7=0', '--uniform', '8=0x200000', '--uniform', '9=0',
                        '--dump', '0x100000=512:/scratch/agxsim-runs/b34/sim_out.bin'], input=small, capture_output=True)
    w = struct.unpack('<128I', open('/scratch/agxsim-runs/b34/sim_out.bin', 'rb').read())
    print(json.dumps({'mode': 'sim', 'kind': kind, 'rc': r.returncode, 'ok': bool(w) and all(x == 50 for x in w[8:40]), 'err': r.stderr[-200:].decode()}))
    sys.exit()
import gpu_safety; gpu_safety.require_budget(1)
d = Path('/scratch/agxsim-runs/b34/run'); d.mkdir(parents=True, exist_ok=True)
(d / 'code.bin').write_bytes(code + b'\0' * 64); (d / 'table.bin').write_bytes(b'\0' * 256)
r = subprocess.run(['/scratch/agxsim-runs/b1/drm_compute', '/dev/dri/renderD128', str(d / 'code.bin'), '32', str(d / 'out.bin'), str(reps), '64',
                    str(d / 'table.bin')], capture_output=True, text=True, timeout=120,
                   env=dict(os.environ, AGX_HELPER_CODE='/scratch/agxsim-runs/b1/an/helper-mesa.bin', AGX_SCRATCH_DWORDS='80'))
fw = [json.loads(l)['fw_ts'] for l in r.stdout.splitlines() if l.startswith('{"rep"')]
w = struct.unpack('<%dI' % (os.path.getsize(d / 'out.bin') // 4), open(d / 'out.bin', 'rb').read())
print(json.dumps({'mode': 'gpu', 'kind': kind, 'trips': trips, 'rc': r.returncode, 'ok': all(x == trips for x in w[8:40]),
                  'fw_ns_min': min(t[1] - t[0] for t in fw) if fw else None}))
