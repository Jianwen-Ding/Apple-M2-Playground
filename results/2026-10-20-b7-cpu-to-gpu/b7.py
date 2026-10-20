#!/usr/bin/env python3
"""B7: CPU -> GPU visibility during a dispatch. drm_compute's AGX_CPU_CLOCK thread keeps writing an incrementing
counter to table word 0 while the kernel runs. Each lane loads it N times (plain device_load, or a returning atomic
add of 0) and outputs last - first (how far it saw the CPU counter move). Bounded loop.
Usage: b7.py sim|gpu plain|atomic N [flush]"""
import json, struct, subprocess, sys, os
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop, run_drm_atomic as DA
mov = RS.mov
e = lambda *a: agx_loop.encode(*a)
cov.install()
REGS = 64

def body(kind, n):
    plain = e('device_load 0, i32, x, r11, u8_u9, r5, unsigned')
    x = int.from_bytes(plain, 'little'); coh = ((x & ~(7 << 44)) | 7 << 44).to_bytes(8, 'little')   # Mesa u4 = 7: coherent
    rd = {'plain': plain, 'atomic': DA.atomic(0, 11, 5, 16, True), 'coherent': coh, 'plain_f59d': bytes.fromhex('f59d') + plain,
          'coherent_f59d': bytes.fromhex('f59d') + coh}[kind] + e('wait 0')
    b = mov(3, 0) + mov(4, n) + mov(5, 0) + mov(16, 0) + rd + e('iadd r12, r11, 0')
    loop = rd + e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
    b += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + loop
    b += e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}') + e('pop_exec r0l, 1')
    return b + e('isub r2, r11, r12')

def main():
    mode, kind, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    flush = len(sys.argv) > 4 and sys.argv[4] == 'flush'
    bd = body(kind, n); cov.gate(bd); code = drm.build_main(bd)
    table = [0] * 1024
    if mode == 'sim':
        out, tab = cov.simulate(code, 64, 32, REGS, 0, table)
        print(json.dumps({'mode': 'sim', 'kind': kind, 'delta': sorted(set(out[8:72]))[:4]})); return
    import gpu_safety; gpu_safety.require_budget(1)
    d = Path('/scratch/agxsim-runs/b7/run'); d.mkdir(parents=True, exist_ok=True)
    (d / 'code.bin').write_bytes(code + b'\x00' * 64)
    (d / 'table.bin').write_bytes(struct.pack('<1024I', *table))
    env = dict(os.environ, AGX_CPU_CLOCK='0', AGX_CPU_CLOCK_FLUSH='1' if flush else '0')
    r = subprocess.run(['/scratch/agxsim-runs/b1/drm_compute', '/dev/dri/renderD128', str(d / 'code.bin'), '64', str(d / 'out.bin'),
                        '1', str(REGS), str(d / 'table.bin')], capture_output=True, text=True, timeout=120, env=env)
    lines = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
    w = struct.unpack('<%dI' % (len(open(d / 'out.bin', 'rb').read()) // 4), open(d / 'out.bin', 'rb').read())
    deltas = list(w[8:72])
    rep = next((l for l in lines if 'rep' in l), {})
    clk = next((l for l in lines if 'cpu_clock' in l), {})
    print(json.dumps({'mode': 'gpu', 'kind': kind, 'n': n, 'flush': flush, 'rc': r.returncode, 'delta_min': min(deltas), 'delta_max': max(deltas),
                      'fw_ns': (rep.get('fw_ts') or [0, 0])[1] - (rep.get('fw_ts') or [0, 0])[0], 'cpu_clock': clk}))
main()
