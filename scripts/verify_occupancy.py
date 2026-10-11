#!/usr/bin/env python3
"""Offline check of the retained occupancy evidence (no GPU).

Model: resident SIMD groups per core = min(96, 2 * floor(3328 / (2 * declared_halves)))
for workgroups of >= 128 lanes; smaller workgroups cap lower."""
import gzip, json, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-occupancy'
model = lambda g: min(96, 2*(3328//(2*g)))
fails = 0
def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)
sw = json.loads(gzip.open(R/'lx128-sweep.json.gz').read())
pts = sw['points']
check(sw['local_x'] == 128 and len(pts) == 60, '128-lane sweep: 30 register counts x 2 repeats')
check(all(p['peak_simd_groups'] == model(p['gprs']) for p in pts), 'every point equals min(96, 2*floor(3328/(2g)))')
check(all(p['counters_back_to_zero'] for p in pts), 'every per-core counter returned to zero')
lo = json.loads(gzip.open(R/'lx32-low.json.gz').read())['points']
check(max(p['peak_simd_groups'] for p in lo) < 64 and all(p['peak_simd_groups'] < model(p['gprs']) for p in lo if p['gprs'] <= 48),
      '32-lane workgroups cap below the register model at low counts (max %d)' % max(p['peak_simd_groups'] for p in lo))
for lx in (64, 256):
    p = json.loads(gzip.open(R/f'lx{lx}-points.json.gz').read())['points']
    g16 = [x['peak_simd_groups'] for x in p if x['gprs'] == 16][0]
    check(all(x['peak_simd_groups'] == model(x['gprs']) for x in p if x['gprs'] >= 48), f'{lx}-lane workgroups follow the model at 48+ halves (16 halves: {g16:.0f})')
for lx in (128, 256):
    tp = json.loads((R/f'tg-sweep-lx{lx}.json').read_text())['points']
    gpw = lx//32
    want = lambda sh: min(96, gpw*(65536//sh))
    check(all(abs(x['peak_simd_groups']-want(x['shared_bytes'])) < 1e-9 and x['counters_back_to_zero'] for x in tp),
          f'threadgroup memory, {lx}-lane workgroups: resident groups = min(96, groups/wg * floor(65536 / declared bytes)): '
          + ', '.join(f"{x['shared_bytes']}:{x['peak_simd_groups']:.0f}" for x in tp))
print(f'{fails} failures'); sys.exit(1 if fails else 0)
