#!/usr/bin/env python3
"""B11: what the `.neg` / `.abs` source modifiers do to NaNs, denormals and zeros (PTX neg.f32 / abs.f32 must only
change the sign bit unless .ftz). Lane i loads x = table[i] into r6 and runs one recorded-safe form:
  fadd32 r14, r6.neg|abs, r7 (r7 = -0.0)   fmul32 r14, r6.neg|abs, r7 (r7 = 1.0)   fadd16 r14l, r6l.neg|abs, r7h (r7h = -0.0)
r2 = r14 is stored at out[8 + i]. Usage: b11.py sim|gpu. The result of each lane is classified against two models:
'bits' (sign flipped / cleared, nothing else) and 'arith' (flush denormals to signed zero, NaN -> canonical)."""
import json, struct, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
F32 = [0x00000000, 0x80000000, 0x3f800000, 0xbf800000, 0x00000001, 0x80000001, 0x00400000, 0x807fffff, 0x007fffff,
       0x00800000, 0x80800000, 0x7f7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0xffc00000, 0x7fc00001, 0x7fffffff,
       0xffc12345, 0x7f800001, 0xff800001, 0x7fa00000, 0x40490fdb, 0xc0490fdb]
F16 = [0x0000, 0x8000, 0x3c00, 0xbc00, 0x0001, 0x8001, 0x03ff, 0x83ff, 0x0200, 0x0400, 0x7bff, 0x7c00, 0xfc00, 0x7e00,
       0xfe00, 0x7e01, 0x7fff, 0xfe55, 0x7c01, 0xfc01, 0x7d00, 0x4248]
CASES = [('fadd32_neg', 'fadd32 r14, r6.neg, r7', 0x80000000, 32), ('fadd32_abs', 'fadd32 r14, r6.abs, r7', 0x80000000, 32),
         ('fmul32_neg', 'fmul32 r14, r6.neg, r7', 0x3f800000, 32), ('fmul32_abs', 'fmul32 r14, r6.abs, r7', 0x3f800000, 32),
         ('fadd16_neg', 'fadd16 r14l, r6l.neg, r7h', 0x80000000, 16), ('fadd16_abs', 'fadd16 r14l, r6l.abs, r7h', 0x80000000, 16)]

def models(case, x, w):
    s = 1 << (w - 1); m = s - 1
    bits = (x ^ s) if case.endswith('neg') else (x & m)
    e_mask = 0x7f800000 if w == 32 else 0x7c00
    frac = (1 << (23 if w == 32 else 10)) - 1
    isnan = (x & e_mask) == e_mask and (x & frac)
    if isnan:
        arith = 0x7fc00000 if w == 32 else 0x7e00
    elif w == 32 and (x & e_mask) == 0:
        arith = bits & s                                 # flushed: signed zero
    else:
        arith = bits
    return bits, arith

def main():
    mode = sys.argv[1]
    if mode == 'gpu':
        import run_bench as B, gpu_safety
        gpu_safety.require_budget(1); R = B.Runner(Path('/scratch/agxsim-runs/b11/run'))
    res = {'mode': mode}
    for name, ins, r7, w in CASES:
        xs = F32 if w == 32 else F16
        n = len(xs)
        bd = mov(7, r7) + e('device_load 0, i32, x, r6, u8_u9, r1, unsigned') + e('wait 0') + mov(14, 0) + e(ins) + e('iadd r2, r14, 0')
        cov.gate(bd); code = drm.build_main(bd)
        table = xs + [0] * (64 - n)
        if mode == 'sim':
            out, _ = cov.simulate(code, 32 * ((n + 31) // 32), 32, 32, 0, table)
        else:
            out, _, _, _ = RS.run(R, code, 32 * ((n + 31) // 32), 32, table, 32)
        rows = []
        for i, x in enumerate(xs):
            got = out[8 + i] & (0xffffffff if w == 32 else 0xffff)
            bits, arith = models(name, x, w)
            rows.append({'x': f'{x:0{w // 4}x}', 'got': f'{got:0{w // 4}x}', 'bits': got == bits, 'arith': got == arith})
        res[name] = {'bits_model': sum(r['bits'] for r in rows), 'arith_model': sum(r['arith'] for r in rows), 'n': n, 'rows': rows}
        print(name, res[name]['bits_model'], res[name]['arith_model'], n, ' '.join(f"{r['x']}->{r['got']}" for r in rows if not r['bits']), flush=True)
    Path(f'{mode}.json').write_text(json.dumps(res, indent=0) + '\n')

if __name__ == '__main__':
    main()
