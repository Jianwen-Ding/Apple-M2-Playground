#!/usr/bin/env python3
"""The NaN bit patterns of AGX's fp32 special-function results (rcp, rsqrt, exp2, log2): each instruction on inputs
that give NaN (NaNs of several payloads and both signs; negatives, -inf and -0 where the function is undefined) and
on a few ordinary ones, recording every output. A front end that must return one canonical NaN (PTX: 0x7fffffff)
can test a result against the hardware's NaN with one comparison only if the hardware's NaN is a single pattern.
  run_drm_special_nan.py offline|hardware [--result FILE]
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
OPS = {'rcp': 'rcp r13, r8', 'rsqrt': 'rsqrt r13, r8', 'exp2': 'exp2 r13, r8', 'log2': 'log2 r13, r8'}
INPUTS = [0x7fc00000, 0x7fffffff, 0x7f800001, 0x7fa00000, 0xffc00000, 0xffffffff, 0xff800001, 0x7fc12345,
          0xbf800000, 0xc2c80000, 0xff800000, 0x7f800000, 0x80000000, 0x00000000, 0x80000001, 0x00000001,
          0x3f800000, 0x40490fdb, 0x00800000, 0x7f7fffff]


def build(op, n):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [load(8, 1, True), e('wait 0'), e(OPS[op])]
    ins += [mov(6, n), e('iadd r7, r1, r6'), agx_loop.store(13, 8, 7), e('wait 0'), mov(2, 0)]
    return b''.join(ins)


def is_nan(b):
    return (b & 0x7fffffff) > 0x7f800000


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/special-nan'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    xs = INPUTS * 2  # two SIMD lanes' worth of each, 40 lanes
    n = len(xs)
    rec = {}
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
    else:
        out = a.output; out.mkdir(parents=True, exist_ok=True)
        exe = out/'drm_compute'
        subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    for op in OPS:
        if a.mode == 'offline':
            _, t = cov.simulate(drm.build_main(build(op, n)), n, 32, 40, 0, xs+[0xcdcdcdcd]*n)
            outs = list(t[n:2*n])
        else:
            (out/'c.bin').write_bytes(drm.build_main(build(op, n))+bytes(16))
            (out/'t.bin').write_bytes(struct.pack(f'<{2*n}I', *xs, *([0xcdcdcdcd]*n)))
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '40', str(out/'t.bin')],
                               capture_output=True, timeout=120, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
            outs = list(struct.unpack(f'<{2*n}I', (out/'t.out').read_bytes())[n:])
        pairs = {f'{x:#010x}': f'{y:#010x}' for x, y in zip(xs, outs)}
        nans = sorted({f'{y:#010x}' for y in outs if is_nan(y)})
        rec[op] = {'outputs': pairs, 'nan_patterns': nans}
        print(f"{a.mode} {op}: NaN results {nans}")
    if a.result:
        a.result.write_text(json.dumps(rec, indent=1)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
