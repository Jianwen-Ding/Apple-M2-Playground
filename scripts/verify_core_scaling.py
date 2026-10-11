#!/usr/bin/env python3
"""Offline check of the retained core-scaling evidence (no GPU).

Rows: core cycles (reference units) for one step of every one of G SIMD groups of one workgroup on one
core, measured by scripts/scale_probes.py (32/128-step bodies, barrier-bracketed phases)."""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-core-scaling'
fails = 0


def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)


def table(name):
    t = {}
    for r in json.loads((R/name).read_text())['rows']:
        if r.get('core_cycles_per_step') and r['stable_cores'] >= 10 and r['split_workgroups'] == 0:
            t[(r['op'], r['chains'], r['groups'], tuple(r.get('idle', ())))] = r['core_cycles_per_step']
    return t


g = table('grid.json')
T = lambda op, ch, G, idle=(): g[(op, ch, G, idle)]
near = lambda x, y, tol: abs(x-y) <= tol*y
check(len(g) >= 590, f'grid: {len(g)} stable rows (23 forms x 2 chain counts x 13 group counts)')

simple = ['iadd_imm', 'mov_imm', 'fadd32_imm', 'fmadd32_imm']
check(all(near(32/T(o, 8, 32), 4.0, 0.03) for o in simple),
      'core issue saturates at 4 instructions/cycle (32 groups, immediate forms): ' + ', '.join(f'{32/T(o, 8, 32):.2f}' for o in simple))
check(all(T(o, 8, G) < 1.15 for o in simple for G in (1, 2, 3, 4)) and all(near(T(o, 8, G), 2.0, 0.3) for o in simple for G in (5, 6, 8)),
      'up to 4 groups issue in parallel (<= 1.15 cycles/step); 5, 6 and 8 groups take ~2 (one issue per cycle per scheduler, g % 4)')

half = {'imadd': 1.96, 'bfi': 1.96, 'convert_f2i': 1.96, 'floor': 1.96, 'log2': 1.96, 'rcp': 2.94, 'rsqrt': 3.92, 'iadd64': 3.92}
for o, c in half.items():
    ok = (T(o, 8, 3) > 1.8*T(o, 8, 2) and near(T(o, 8, 3), T(o, 8, 4), 0.1) and near(T(o, 8, 5), T(o, 8, 6), 0.1)
          and near(T(o, 8, 32)/16, c, 0.03))
    check(ok, f'{o}: two shared units (3 groups cost as 4, 5 as 6; 2 groups as 1): '
              f'G=1..6 {[round(T(o, 8, G), 2) for G in (1, 2, 3, 4, 5, 6)]}, per-unit occupancy {T(o, 8, 32)/16:.2f} (model {c})')

check(near(T('fadd32', 8, 3), 2.0, 0.05) and near(T('fadd32', 8, 32), 16.0, 0.05),
      f'fadd32 (2 register reads): 3 groups {T("fadd32", 8, 3):.2f}, 32 groups {T("fadd32", 8, 32):.2f} = 2 reads/cycle per half')
check(near(T('fmadd32', 8, 3), 3.0, 0.05) and near(T('fmadd32', 8, 32), 24.0, 0.05),
      f'fmadd32 (3 register reads): 3 groups {T("fmadd32", 8, 3):.2f}, 32 groups {T("fmadd32", 8, 32):.2f}')
check(T('simd_shuffle', 8, 5) > 2*T('simd_shuffle', 8, 4)*0.95 and near(T('simd_shuffle', 8, 32), 16, 0.05),
      f'simd_shuffle (issue interval 2) blocks its scheduler: 4 groups {T("simd_shuffle", 8, 4):.2f}, 5 groups {T("simd_shuffle", 8, 5):.2f}, 32 groups {T("simd_shuffle", 8, 32):.2f}')
red = {o: 32/T(o, 8, 32) for o in ('simd_iadd', 'simd_prefix_iadd', 'quad_iadd')}
check(0.2 < red['simd_iadd'] < 0.3 and red['quad_iadd'] > 0.6,
      'reduction core rates at 32 groups (instr/cycle): ' + ', '.join(f'{k} {v:.3f}' for k, v in red.items()))

i = table('idle.json')
I = lambda G, idle=(): i[('iadd_imm', 8, G, tuple(idle))]
check(near(I(5), 2.0, 0.05) and all(I(5, (s,)) < 1.15 for s in (1, 3, 4)) and near(I(5, (2,)), 2.0, 0.05),
      f'idle-slot anomaly: 5 working groups {I(5):.2f}; idling slot 1/3/4 -> {I(5, (1,)):.2f}/{I(5, (3,)):.2f}/{I(5, (4,)):.2f}, slot 2 -> {I(5, (2,)):.2f} (no static slot->scheduler map fits)')

c = table('chains.json')
check(len(c) >= 130, f'chains: {len(c)} stable rows (5 forms x chains 2,3,4,6 x 7 group counts)')
lat16 = T('iadd_imm', 1, 16)
check(lat16 > 1.25*T('iadd_imm', 8, 16), f'open: one dependent iadd chain per group at 16 groups costs {lat16:.2f} vs {T("iadd_imm", 8, 16):.2f} with 8 chains')

print(f'{fails} failures'); sys.exit(1 if fails else 0)
