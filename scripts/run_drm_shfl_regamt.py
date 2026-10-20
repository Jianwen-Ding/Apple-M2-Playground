#!/usr/bin/env python3
"""Native simd_shuffle_up / _down / _xor / simd_shuffle with a *register* amount (r9l) against PTX shfl.sync with the default
clamp. Does a warp-uniform runtime offset get the 1-instruction lowering? Same data as run_drm_shfl.py (240 groups, six kinds:
0 uniform small, 1 per-lane small, 2 per-lane full width, 3 lane permutation, 4 uniform edge amounts 0..3/31/32/33/63, 5 ramp).
Straight-line, direct DRM; offline mode runs the simulator (the safety gate).
  run_drm_shfl_regamt.py offline|hardware [--result FILE]
"""
import argparse, json, sys
from pathlib import Path
import run_drm_compute as drm
from run_drm_shfl import MODES, build, data, default_c, ptx_shfl, run_hw, REPO
import subprocess

OP = {'up': 'simd_shuffle_up', 'down': 'simd_shuffle_down', 'bfly': 'simd_shuffle_xor', 'idx': 'simd_shuffle'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--groups', type=int, default=240)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/shfl-regamt'))
    a = p.parse_args()
    n = a.groups*32
    A, B = data(a.groups, 11)
    tb = A+B+[0xcdcdcdcd]*(2*n)
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    if a.mode == 'hardware':
        subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    else:
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
    rec = {'groups': a.groups, 'results': []}
    for mode in MODES:
        for variant, pre in (('raw', []), ('masked', ['and r9, r9, 31'])):
            lines = pre + [f'{OP[mode]} r28, r8, r9l']
            code = drm.build_main(build(n, lines, 28, None))
            t = cov.simulate(code, n, 32, 80, 0, tb)[1] if a.mode == 'offline' else run_hw(exe, out, code, n, tb)
            bad = {}
            for g in range(a.groups):
                sl = slice(32*g, 32*g+32)
                d, _ = ptx_shfl(mode, A[sl], B[sl], default_c(mode))
                if t[2*n+32*g:2*n+32*g+32] != d:
                    bad[g % 6] = bad.get(g % 6, 0)+1
            r = {'mode': mode, 'variant': variant, 'bad_by_kind': bad, 'out': t[2*n:3*n]}
            rec['results'].append(r)
            print(a.mode, mode, variant, 'wrong groups by kind', bad, flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
