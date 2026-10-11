#!/usr/bin/env python3
"""Targeted microarchitecture probes behind the cost model (direct DRM, known-safe encodings only).

    python3 scripts/cost_probes.py lead|rotation|pairs|half [--output DIR]

All bodies pass run_bench.check_body and run in the counted-loop skeleton; cycles come from the
in-dispatch clock (reference units, see the instruction-bench finding; x1.049 for real cycles).
  lead     : a leader instruction + k independent iadds (k = 0, 1, 2, 4, 8), 8 repetitions per trip
  rotation : 72 independent instructions rotating over D destination registers (D = 4..16)
  pairs    : dependent chains alternating two instructions from different units
  half     : 16-bit / 32-bit partial-register cases
Results print per test and are saved as JSON (one value: cycles per repetition, or per instruction).
"""
import argparse, json
from pathlib import Path
import agx_loop, cost_hw as H, run_bench as B, gpu_safety

e = agx_loop.encode
EMPTY_TRIP = 35.25      # measured empty-loop trip (cost-model calibration)


def per_rep(R, lines, reps=8):
    parts = [e(x) for x in lines]*reps
    body = b''.join(parts)
    if body: B.check_body(body, [len(x) for x in parts])
    m = H.measure(R, H.counted(body, 100), H.counted(body, 500), 400, 'one')
    return (m['cycles']-EMPTY_TRIP)/reps, m['mhz']


def ind(k, regs=(7, 8, 9, 10, 11, 12, 13, 14)):
    return [f'iadd r{r}, r{r}, 1' for r in regs[:k]]


LEADS = {'rcp': 'rcp r6, r6', 'log2': 'log2 r6, r6', 'floor': 'floor r6, r6', 'sin_pt_1': 'sin_pt_1 r6, r6',
         'bfi': 'bfi r6, r6, r24, r26', 'convert': 'convert u32_to_f, r6, r6, rte', 'imadd': 'imadd r6, r6, r25, r24',
         'simd_shuffle': 'simd_shuffle r6, r6, r26l', 'fadd32': 'fadd32 r6, r6, r24', 'simd_iadd': 'simd_iadd r6, r6'}
PAIRS = {'iadd>iadd': ('iadd r6, r6, r24', 'iadd r6, r6, r24'), 'fadd32>iadd': ('fadd32 r6, r6, r24', 'iadd r6, r6, r24'),
         'iadd>bfi': ('iadd r6, r6, r24', 'bfi r6, r6, r24, r26'), 'fadd32>log2': ('fadd32 r6, r6, r24', 'log2 r6, r6'),
         'iadd>simd_shuffle': ('iadd r6, r6, r24', 'simd_shuffle r6, r6, r26l'), 'fadd32>convert': ('fadd32 r6, r6, r24', 'convert u32_to_f, r6, r6, rte'),
         'fadd16>fadd32': ('fadd16 r6l, r6l, r24l', 'fadd32 r6, r6, r24'), 'iadd>fmadd32': ('iadd r6, r6, r24', 'fmadd32 r6, r6, r25, r24'),
         'simd_iadd>iadd': ('simd_iadd r6, r6', 'iadd r6, r6, r24')}
HALF = {'f32 write r6 then independent f16 write r6l': ['fadd32 r6, r8, r24', 'fadd16 r6l, r7l, r24l'],
        'f16 write r6l then f32 read of r6 (merge)': ['fadd16 r6l, r6l, r24l', 'fadd32 r9, r6, r24'],
        'f16 write r6l then f16 read of r6l': ['fadd16 r6l, r6l, r24l', 'fadd16 r9l, r6l, r24l'],
        'f16 write r6l then f32 read of r7 (control)': ['fadd16 r6l, r6l, r24l', 'fadd32 r9, r7, r24'],
        'simd_iadd then dependent iadd': ['simd_iadd r6, r6', 'iadd r6, r6, r24'],
        'simd_iadd then independent iadd': ['simd_iadd r6, r6', 'iadd r7, r7, r24'],
        'simd_iadd then dependent fadd32': ['simd_iadd r6, r6', 'fadd32 r6, r6, r24'],
'f32 then f16 read of low half': ['fadd32 r6, r6, r24', 'fadd16 r6l, r6l, r24l'],
        'f16 chain': ['fadd16 r6l, r6l, r24l', 'fadd16 r6l, r6l, r24l'],
        'f16 low/high independent': ['fadd16 r6l, r6l, r24l', 'fadd16 r6h, r6h, r24l'],
        'f16 write r6l then independent f32 write r6': ['fadd16 r6l, r7l, r24l', 'fadd32 r6, r8, r24']}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('what', choices=['lead', 'rotation', 'pairs', 'half', 'values', 'groups'])
    ap.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/cost/probes'))
    a = ap.parse_args()
    gpu_safety.require_budget(1)
    R = B.Runner(a.output/a.what)
    res = {}
    if a.what == 'lead':
        for lead, li in LEADS.items():
            for k in (0, 1, 2, 4, 8):
                res[f'{lead}+{k}'] = per_rep(R, [li]+ind(k))[0]
            print(lead, ' '.join(f"+{k}: {res[f'{lead}+{k}']:.2f}" for k in (0, 1, 2, 4, 8)), flush=True)
    elif a.what == 'rotation':
        for instr in ('iadd r{r}, r{r}, 1', 'fadd32 r{r}, r{r}, 0.125', 'fadd16 r{r}l, r{r}l, r24l'):
            for D in (4, 6, 7, 8, 9, 10, 12, 16):
                lines = [instr.format(r=5+k % D) for k in range(72)]
                c, mhz = per_rep(R, lines, reps=1)
                res[f'{instr}|{D}'] = c/72
                print(f'{instr.split()[0]:6s} D={D:2d} cycles/instr {c/72:.2f}', flush=True)
    elif a.what == 'pairs':
        for name, (x, y) in PAIRS.items():
            res[name] = per_rep(R, [x, y])[0]; print(f'{name:20s} cycles/pair {res[name]:.2f}', flush=True)
    elif a.what == 'groups':
        # latency-bound single chains: per-trip cycles with 1 SIMD group vs ~4 per core (per-core span)
        G = {'iadd chain': ['iadd r6, r6, r24'], 'fadd32 chain': ['fadd32 r6, r6, r24'], 'imadd chain': ['imadd r6, r6, r25, r24'],
             'rcp chain': ['rcp r6, r6'], 'shuffle chain': ['simd_shuffle r6, r6, r26l'], 'fmadd32 chain': ['fmadd32 r6, r6, r25, r24'],
             'iadd 2 chains': ['iadd r6, r6, r24', 'iadd r7, r7, r24'], 'mixed chain': ['iadd r6, r6, r24', 'fadd32 r6, r6, r24', 'imadd r6, r6, r25, r24', 'bfi r6, r6, r24, r26']}
        for name, lines in G.items():
            parts = [e(x) for x in lines]*8; body = b''.join(parts)
            B.check_body(body, [len(x) for x in parts])
            one = H.measure(R, H.counted(body, 100), H.counted(body, 500), 400, 'one')
            four = H.measure(R, H.counted(body, 100), H.counted(body, 500), 400, 'gpu')
            res[name] = {'one': one['cycles'], 'four_per_core': four['cycles'], 'ratio': four['cycles']/one['cycles'], 'groups_per_core': four['groups_per_core']}
            print(f"{name:16s} 1 group {one['cycles']:7.1f}  4/core {four['cycles']:7.1f}  ratio {res[name]['ratio']:.3f}", flush=True)
    elif a.what == 'values':
        # same instruction sequences with different data: benchmark chains (NaN/inf/trivial) vs finite values.
        # r24 = 1 (int) / 0.0f, r25 = 1.0f; the loop preloads r5..r12 with 1.5f (cost_hw.counted).
        V = {'log2 chain (1.5 -> NaN after 3 steps)': ['log2 r6, r6'],
             'exp2 chain (1.5 -> +inf after 4 steps)': ['exp2 r6, r6'],
             'log2/exp2 alternating (stays ~1.5)': ['log2 r6, r6', 'exp2 r6, r6'],
             'fmul32 x*1.0 (trivial)': ['fmul32 r6, r6, r25'],
             'fmul32 x*1.0001 (r26 = 1.0001f)': ['mov_imm r26, 1065354055, 0b0', 'fmul32 r6, r6, r26'],
             'fmadd32 x*1+0 (trivial)': ['fmadd32 r6, r6, r25, r24'],
             'fmadd32 x*1.0001+0.5': ['mov_imm r26, 1065354055, 0b0', 'mov_imm r27, 1056964608, 0b0', 'fmadd32 r6, r6, r26, r27'],
             'rcp chain (1.5 <-> 0.667)': ['rcp r6, r6'],
             'rcp of 0 -> inf -> 0': ['mov_imm r6, 0, 0b0', 'rcp r6, r6', 'rcp r6, r6']}
        for name, lines in V.items():
            res[name] = per_rep(R, lines)[0]; print(f'{name:42s} cycles/rep {res[name]:.2f}', flush=True)
    else:
        for name, lines in HALF.items():
            res[name] = per_rep(R, lines)[0]; print(f'{name:45s} cycles/pair {res[name]:.2f}', flush=True)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/f'{a.what}.json').write_text(json.dumps(res, indent=1)+'\n')


if __name__ == '__main__':
    main()
