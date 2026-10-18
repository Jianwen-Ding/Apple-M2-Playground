#!/usr/bin/env python3
"""Cost of the 0x68 threadgroup barrier against the ALU work before it and the workgroup size (safe-02 item 3). Direct DRM, straight-line.

Every SIMD group runs N barriers in a row, with A dependent `iadd`s before each, uniform control flow (no deadlock possible). N in {1, 33, 65};
the cost per barrier is the slope of firmware time against N. Workgroups of 32 .. 1,024 lanes, 131,072 lanes per dispatch.
Gate: the same program with each barrier replaced by a same-length `wait` runs in the Rust simulator first.
  run_drm_barrier_cost.py offline|hardware
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
from run_drm_opcode_describe import WAIT

REPO = Path(__file__).resolve().parents[1]
e, mov = agx_loop.encode, agx_loop.chains.mov_imm
BAR = bytes.fromhex('6800')
GPRS = 48


def build(nbar, alu, barrier=BAR):
    ins = [mov(10, 1)]
    for _ in range(nbar):
        ins += [e('iadd r10, r10, 3') for _ in range(alu)]+([barrier] if barrier else [])
    ins += [mov(6, 131072), e('iadd r7, r1, r6'), agx_loop.store(10, 8, 7), e('wait 0'), mov(2, 0)]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/barrier-cost'))
    p.add_argument('--result', type=Path)
    p.add_argument('--control', action='store_true', help='same iadds, no barriers')
    a = p.parse_args()
    control = a.control
    n = 131072
    tb = [0]*n+[0xcdcdcdcd]*n
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        for alu in (0, 4, 32):
            o, t = cov.simulate(drm.build_main(build(5, alu, WAIT)), n, 32, GPRS, 0, tb)
            print('alu', alu, 'result lane0', t[n], 'expected', 1+3*alu*5, 'all equal', len(set(t[n:2*n])) == 1)
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'lanes': n, 'runs': []}
    for rep in range(a.repeats):
        for wg in ((128, 256) if control else (32, 128, 256, 1024)):
            for alu in ((4, 32) if control else (0, 4, 32)):
                for nb in (1, 33, 65):
                    (out/'c.bin').write_bytes(drm.build_main(build(nb, alu, None if control else BAR))+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
                    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(GPRS), str(out/'t.bin')],
                                       capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_LOCAL_X': str(wg), 'AGX_TABLE_OUT': str(out/'t.out')})
                    smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                    if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                        sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
                    t = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
                    x = {'rep': rep, 'wg': wg, 'alu': alu, 'nbar': nb, 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'result_ok': set(t[n:2*n]) == {1+3*alu*nb}, 'control': control}
                    rec['runs'].append(x)
                    print(json.dumps(x), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
