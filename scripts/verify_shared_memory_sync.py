#!/usr/bin/env python3
"""Offline check of the retained threadgroup-memory, barrier and atomic throughput evidence (no GPU)."""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-shared-memory-sync'
fails = 0


def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)


def tab(f, key='stride'):
    return {(r.get(key), r['groups']): r['core_cycles_per_step'] for r in json.loads((R/f).read_text())['rows']}


near = lambda x, y, tol: abs(x-y) <= tol*y
for f, name in (('tg.json', 'threadgroup_load'), ('tgstore.json', 'threadgroup_store')):
    t = tab(f)
    deg = {0: 1, 1: 1, 2: 2, 4: 4, 8: 8, 16: 16, 32: 32}
    ok = all(near(t[(S, 32)]/32, max(1, d), 0.05) for S, d in deg.items() if (S, 32) in t and S >= 2)
    check(ok and t[(1, 32)]/32 < 1.0, f'{name}: 32 groups cost max(1, bank-conflict degree) core cycles per instruction (32 banks x 4 B): '
          + ', '.join(f'S={S}: {t[(S, 32)]/32:.2f}' for S in deg if (S, 32) in t))
    one = t[(1, 1)]
    check(25 < one < 35 if name.endswith('load') else 20 < one < 28, f'{name}: one SIMD group, back to back: {one:.1f} cycles per access')
b = {(r['barrier'], r['filler_iadds'], r['groups']): r['core_cycles_per_step'] for r in json.loads((R/'barrier.json').read_text())['rows']}
check(all(12 < b[('0x68', 0, G)] < 15 for G in (1, 2, 4, 8, 16, 32)),
      '0x68 back to back: 13-14 cycles per barrier for 1-32 SIMD groups: ' + ', '.join(f"{G}:{b[('0x68', 0, G)]:.1f}" for G in (1, 2, 4, 8, 16, 32)))
check(all(6.5 < b[('0x78', 0, G)] < 8 for G in (1, 2, 4)), '0x78 back to back: ~7 cycles')
check(b[('0x68', 4, 1)] > b[('0x68', 0, 1)] + 25, f"4 iadds before each barrier: {b[('0x68', 4, 1)]:.1f} vs {b[('0x68', 0, 1)]:.1f} (barrier waits for ALU results)")
a = tab('atomic-global.json')
check(near(a[(1, 32)]/32, 6.9, 0.05) and near(a[(8, 32)]/32, 54.4, 0.05) and near(a[(32, 32)]/32, 53.8, 0.05),
      f'device atomic add, distinct words: 32 consecutive words {a[(1, 32)]/32:.1f}, lanes 32 B apart {a[(8, 32)]/32:.1f}, '
      f'128 B apart {a[(32, 32)]/32:.1f} core cycles per instruction (~1.7 per 32-byte sector)')
c = tab('atomic.json')
check(c[(0, 1)] > 500 and near(c[(0, 32)]/32, c[(0, 1)], 0.05),
      f'one word for every lane of every core: {c[(0, 1)]:.0f} core cycles per instruction (32 x 38 ops: ~2 per cycle GPU-wide)')
bf = {(r['filler_iadds'], r['groups']): r['core_cycles_per_step'] for r in json.loads((R/'barrier-fill.json').read_text())['rows']}
check(bf[(16, 32)] > 1.6*bf[(8, 32)]*0.9 and bf[(8, 32)] > 1.5*bf[(4, 32)]*0.9 if (4, 32) in bf else bf[(16, 32)] > 250,
      'barrier cost at 32 groups grows with the registers written before it: ' + ', '.join(f'F={f}: {bf[(f, 32)]:.0f}' for f in (1, 2, 8, 16)))
ta = {(r['kind'], r['stride'], r['groups']): r['core_cycles_per_step'] for r in json.loads((R/'tgatomic.json').read_text())['rows'] if r.get('core_cycles_per_step')}
check(near(ta[('tgatomic', 1, 32)]/32, 1.0, 0.05) and near(ta[('tgatomic', 0, 32)]/32, 31.4, 0.05),
      f"threadgroup atomic add: distinct words {ta[('tgatomic', 1, 32)]/32:.2f}, one word {ta[('tgatomic', 0, 32)]/32:.1f} core cycles per instruction")
ar = {(r['stride'], r['groups']): r['core_cycles_per_step'] for r in json.loads((R/'atomic-ret.json').read_text())['rows']}
check(near(ar[(1, 32)]/32, 7.5, 0.05) and ar[(1, 1)] > 20, f"device atomic with return: {ar[(1, 32)]/32:.1f} per instruction at 32 groups, {ar[(1, 1)]:.1f} for one group")
print(f'{fails} failures'); sys.exit(1 if fails else 0)
