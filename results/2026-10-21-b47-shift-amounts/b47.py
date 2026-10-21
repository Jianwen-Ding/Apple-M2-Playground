#!/usr/bin/env python3
"""B47: register shift amounts 0..255 in bfi / bfeil / extr / asr. Lane i (one 256-thread workgroup) computes
`op r2, ..., r1` with r1 = i as the amount; the control suffix stores r2 at out[8 + i]. Usage: b47.py sim|gpu.
Each result is compared with the formulas of ptx-re-blockers.md B47 with the amount taken modulo 128, 64 and 32."""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
N, M = 256, 0xffffffff
HI = 0x9abcdef0
XS = (0x80000001, 0xffffffff, 0x12345678)

def cases():
    for x in XS:
        yield f'bfi_0_{x:08x}', 0, x, 'bfi r2, r6, r7, r1'
        yield f'bfi_a_{x:08x}', 0x0f0f0f0f, x, 'bfi r2, r6, r7, r1'
        yield f'bfeil_0_{x:08x}', 0, x, 'bfeil r2, r6, r7, r1'
        yield f'bfeil_a_{x:08x}', 0x0f0f0f0f, x, 'bfeil r2, r6, r7, r1'
        yield f'extr_{x:08x}', x, HI, 'extr r2, r6, r7, r1'
        yield f'asr_{x:08x}', 0, x, 'asr r2, r7, r1'

def model(name, a, b, s):
    op = name.split('_')[0]
    sh = lambda v, k: (v << k) if k < 128 else 0
    if op == 'bfi':   return ((a & ~sh(M, s)) | sh(b, s)) & M
    if op == 'bfeil': return (b >> s) & M | (a & ~M & M)
    if op == 'extr':  return (((b << 32) | a) >> s) & M
    sx = b - (1 << 32) if b >> 31 else b
    return (sx >> s) & M

def main():
    mode = sys.argv[1]
    res = {'mode': mode, 'cases': {}}
    if mode == 'gpu':
        import run_bench as B, gpu_safety
    for name, a, b, ins in cases():
        bd = mov(6, a) + mov(7, b) + e(ins); cov.gate(bd); code = drm.build_main(bd)
        if mode == 'sim':
            out, _ = cov.simulate(code, N, N, 32, 0, [0] * 16)
        else:
            gpu_safety.require_budget(1)
            out, _, _, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b47/run')), code, N, N, [0] * 16, 32)
        got = out[8:8 + N]
        fit = {f'mod{m}': sum(got[s] == model(name, a, b, s % m) for s in range(N)) for m in (128, 64, 32)}
        res['cases'][name] = {'fit': fit, 'got': [f'{v:08x}' for v in got]}
        print(name, fit, flush=True)
    Path(f'{mode}.json').write_text(json.dumps(res, indent=0) + '\n')

if __name__ == '__main__':
    main()
