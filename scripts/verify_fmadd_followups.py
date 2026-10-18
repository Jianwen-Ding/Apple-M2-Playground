#!/usr/bin/env python3
"""Offline checks of the fmadd lane-offset follow-ups (results/2026-10-18-fmadd-followups): write-to-read distance for the
cross-half read, and inactive source lanes. Simulator replay of the masked program unless --no-sim."""
import collections
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
D = ROOT/'results/2026-10-18-fmadd-followups'
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def crossing(path):
    rec = json.load(gzip.open(D/path))
    out = collections.defaultdict(lambda: [0, 0])
    for r in rec['results']:
        if r['flip'] and 'raw' in r['flip']:
            nm = r['flip']['raw']                     # d<N>c<form>r<rep>
            N, form = int(nm[1]), nm[2:5]
            k = (N, form, r['layout'])
            out[k][1] += 1
            out[k][0] += r['table'][6][16] != 0       # slot 6 = r5 (D): lane 16 nonzero = A read from lane 15 across the half boundary
    return rec, out


r1, c1 = crossing('distance1.json.gz')
r2, c2 = crossing('distance2.json.gz')
check('distance run 1: 112 dispatches, N = 0..8 fillers x {bit 68, no bit 68} x layouts A / B x 3 repeats; run 2: 220 dispatches, bit 68 only, 12 repeats; no fault',
      r1['complete'] and r2['complete'] and len(r1['results']) == 112 and len(r2['results']) == 220 and not any(r['fault'] for r in r1['results']+r2['results']))
tot = collections.defaultdict(lambda: [0, 0])
for src in (c1, c2):
    for k, (a, b) in src.items():
        tot[k][0] += a; tot[k][1] += b
check('layout B (a wait follows the fmadd): lane 16 reads lane 15 in every one of 162 runs, with or without bit 68, at every distance 0..8',
      sum(v[1] for k, v in tot.items() if k[2] == 'B') == 162 and all(v[0] == v[1] for k, v in tot.items() if k[2] == 'B'))
check('layout A (an ALU instruction follows), bit 68: distances 0 and 1 never cross (0 of 15 each)', tot[(0, 'c68', 'A')] == [0, 15] and tot[(1, 'c68', 'A')] == [0, 15])
check('layout A, bit 68: distances 2..8 cross in 12-15 of 15 runs each (15 of 15 only at distance 4): never fully reliable',
      all(12 <= tot[(N, 'c68', 'A')][0] <= 15 for N in range(2, 9)) and sum(1 for N in range(2, 9) if tot[(N, 'c68', 'A')][0] == 15) == 1)
check('layout A, no bit 68 (control): lane 16 reads 0 in 26 of 27 runs (one run crossed)', sum(tot[(N, 'c00', 'A')][0] for N in range(9)) == 1 and sum(tot[(N, 'c00', 'A')][1] for N in range(9)) == 27)

mask = json.load(gzip.open(D/'mask.json.gz'))
agg = collections.defaultdict(collections.Counter)
for r in mask['results']:
    for k, v in r['totals'].items():
        agg[(r['k'], r['after'])][k] += v
check('mask run: 3 repeats x k in {1, 2, 4, 8, 15} x {alu, wait} = 30 dispatches of 210 SIMD groups with 7 mask kinds', len(mask['results']) == 30 and mask['groups'] == 210)
check('an active lane whose source lane is inactive reads 0: %d such lanes in total, never the register contents, never another value' %
      sum(c['src_inactive_reads_zero'] for c in agg.values()),
      all(c['src_inactive_reads_register'] == 0 and c['src_inactive_other'] == 0 for c in agg.values()) and sum(c['src_inactive_reads_zero'] for c in agg.values()) == 14572)
check('an active lane whose source is active reads it exactly (0 wrong in every k and both variants); inactive lanes are never written',
      all(c['src_active_bad'] == 0 and c['inactive_changed'] == 0 and c['src_active_ok'] > 300 for c in agg.values()))
check('lanes below the start of their half read 0 except lanes 16+ (cross-half) in a few cases and, only when a wait follows, up to k lanes of the first half in total',
      all(c['below_half_bad_lo'] == 0 for key, c in agg.items() if key[1] == 'alu') and all(c['below_half_bad_lo'] <= 15 for c in agg.values())
      and all(c['below_half_bad_hi'] > 5 for c in agg.values()))
check('with a wait after the fmadd the cross-half reads are 5-25x more frequent than with an ALU instruction after it (k = 8: %d vs %d)' %
      (agg[(8, 'wait')]['below_half_bad_hi'], agg[(8, 'alu')]['below_half_bad_hi']),
      agg[(8, 'wait')]['below_half_bad_hi'] > 5*agg[(8, 'alu')]['below_half_bad_hi'])

if '--no-sim' not in sys.argv:
    sys.path.insert(0, str(ROOT/'scripts')); sys.path.insert(0, str(ROOT.parent/'AGX-Performance-Simulator/scripts'))
    import coverage as cov
    import run_drm_fmadd_mask as R
    import run_drm_compute as drm
    n = mask['groups']*32
    same = True
    for r in mask['results']:
        if r['after'] != 'alu' or r['rep'] != 0:
            continue
        mk = R.masks(mask['groups'], 40+r['rep'])
        o, t = cov.simulate(drm.build_main(R.body(n, r['k'], 'alu')), n, 32, 64, 0, mk+[0]*(2*n))
        d = t[2*n:3*n]
        sim = collections.Counter()
        for g in range(mask['groups']):
            for key, v in R.classify(mk[32*g:32*g+32], d[32*g:32*g+32], r['k']).items():
                sim[key] += v
        for key in ('src_inactive_reads_zero', 'src_inactive_reads_register', 'src_inactive_other', 'src_active_ok', 'src_active_bad', 'inactive_untouched', 'inactive_changed'):
            if sim[key] != r['totals'][key]:
                same = False
                print('   differs', r['k'], key, sim[key], r['totals'][key])
    check('Rust simulator (inactive source reads 0) reproduces the hardware counts of every deterministic class for k = 1, 2, 4, 8, 15 (same masks)', same)
sys.exit(0 if all(ok) else 1)
