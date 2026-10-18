#!/usr/bin/env python3
"""Throughput / latency of Mesa's sin sequence against the PTX-compliant fma-split one (safe-02 item 5). Direct DRM, straight-line.

Each lane runs a dependent chain of K sin evaluations on its own value (the result feeds the next input), K in {1, 64, 128}, 131,072 lanes. The
cost per evaluation is the slope of firmware time against K. Sequences (from scripts/record_sincos_chain.py in the simulator repo):
  mesa : turns = x * c; fract = turns - floor(turns); q = fract * 4; y = sin_pt_1(q); r = sin_pt_2(y) * y       (7 instr)
  fma  : turns = fma(x, c_hi, x * c_lo) instead of x * c                                                         (8 instr)
Offline mode runs the program in the Rust simulator (the safety gate), hardware mode on the GPU.
  run_drm_sincos_cost.py offline|hardware
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
f2b = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
INV2PI = struct.unpack('<f', struct.pack('<f', 0.15915494309189535))[0]
LO = struct.unpack('<f', struct.pack('<f', 0.15915494309189535-INV2PI))[0]
e, mov = agx_loop.encode, chains.mov_imm


def build(kind, k, n):
    ins = [load(10, 1, True), e('wait 0'), mov(8, f2b(INV2PI)), mov(12, f2b(4.0)), mov(15, f2b(LO))]
    for _ in range(k):
        if kind == 'mesa':
            ins.append(e('fmul32 r7, r10, r8'))
        else:
            ins += [e('fmul32 r16, r10, r15'), e('fmadd32 r7, r10, r8, r16')]
        ins += [e('floor r17, r7'), e('fadd32 r17, r7, r17.neg'), e('fmul32 r17, r17, r12'), e('sin_pt_1 r18, r17'), e('sin_pt_2 r19, r18'),
                e('fmul32 r10, r19, r18')]
    ins += [mov(6, n), e('iadd r7, r1, r6'), agx_loop.store(10, 8, 7), e('wait 0'), mov(2, 0)]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins), len(ins)


def table(n):
    import random
    rng = random.Random(3)
    return [f2b(rng.uniform(-100, 100)) for _ in range(n)]+[0xcdcdcdcd]*n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--lanes', type=int, default=131072)
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/sincos-cost'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    n = a.lanes
    tb = table(n)
    regs = 2*24+8
    rec = {'lanes': n, 'runs': []}
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        for kind in ('mesa', 'fma'):
            prog, ni = build(kind, 64, n)
            o, t = cov.simulate(drm.build_main(prog), n, 32, regs, 0, tb)
            res = [struct.unpack('<f', struct.pack('<I', w))[0] for w in t[n:n+n]]
            print(kind, ni, 'instructions; results in [-1,1]:', all(-1.0001 <= v <= 1.0001 for v in res), 'first', res[:3])
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    for rep in range(a.repeats):
        for kind in ('mesa', 'fma'):
            for k in (1, 64, 128):
                prog, ni = build(kind, k, n)
                (out/'c.bin').write_bytes(drm.build_main(prog)+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(regs), str(out/'t.bin')],
                                   capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
                smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                    sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
                t = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
                x = {'rep': rep, 'kind': kind, 'k': k, 'instructions': ni, 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'out_sample': list(t[n:n+n:4099])}
                rec['runs'].append(x)
                print(rep, kind, k, x['fw_ns'], flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
