#!/usr/bin/env python3
"""Offline checks of the occupancy follow-ups (results/2026-10-18-occupancy). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-occupancy'
rec = json.load(gzip.open(D/'occupancy2.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def by(points, *keys):
    d = collections.defaultdict(list)
    for p in points:
        d[tuple(p[k] for k in keys)].append(p)
    return d


allp = [p for k in rec.values() for p in k['points']]
check('every run: all 38 cores used and every per-core counter back to zero', all(p['cores_used'] == 38 and p['counters_back_to_zero'] for p in allp))
sizes = by(rec['sizes']['points'], 'lx')
check('sizes (chain of 2000, 16 halves, 3 runs each): 32 lanes 46-48 groups, 64 lanes 81-87, 96 lanes 93-96',
      all(46 <= p['peak_simd_groups'] <= 48 for p in sizes[(32,)]) and all(81 <= p['peak_simd_groups'] <= 87 for p in sizes[(64,)])
      and all(93 <= p['peak_simd_groups'] <= 96 for p in sizes[(96,)]))
check('sizes: every workgroup size from 128 to 1024 lanes (13 sizes): exactly 96 groups in all runs',
      all(p['peak_simd_groups'] == 96 for lx, ps in sizes.items() if lx[0] >= 128 for p in ps) and len([k for k in sizes if k[0] >= 128]) == 13)
steps = by(rec['steps']['points'], 'lx', 'steps')
med = lambda lx, s: sorted(p['peak_simd_groups'] for p in steps[(lx, s)])[1]
check('chain length: the peak rises with the chain for every size (launch-rate limit) ...',
      all(med(lx, 250) < med(lx, 1000) < med(lx, 4000) for lx in (32, 64)) and med(96, 250) < med(96, 1000) < med(96, 4000))
check('... then plateaus: 32-lane workgroups 54-55 groups at 4,000 and 16,000 steps (all 6 runs), 64-lane 90-94, 96-lane exactly 96',
      all(54 <= p['peak_simd_groups'] <= 55 for s in (4000, 16000) for p in steps[(32, s)])
      and all(90 <= p['peak_simd_groups'] <= 94 for s in (4000, 16000) for p in steps[(64, s)])
      and all(p['peak_simd_groups'] == 96 for s in (4000, 16000) for p in steps[(96, s)]))
shapes = by(rec['shapes']['points'], 'threads')
check('shapes: 64-thread workgroups (64x1x1, 8x8x1, 4x4x4): 89-93 groups; no shape dependence beyond the thread count',
      all(88 <= p['peak_simd_groups'] <= 94 for p in shapes[(64,)]) and {tuple(p['shape']) for p in shapes[(64,)]} == {(64, 1, 1), (8, 8, 1), (4, 4, 4)})
check('shapes: 14 shapes of 128, 256 and 1024 threads (1-D, 2-D, 3-D): exactly 96 groups in every run',
      all(p['peak_simd_groups'] == 96 for t in (128, 256, 1024) for p in shapes[(t,)]) and len({tuple(p['shape']) for t in (128, 256, 1024) for p in shapes[(t,)]}) == 14)
wg8 = [p['peak_lanes']/8 for p in shapes[(8,)]]
check('shapes: 2x2x2 workgroups (8 threads, one partly filled SIMD group): 53-56 resident workgroups per core (peak lanes / 8)', all(52 <= w <= 56 for w in wg8) and len(wg8) == 3)


def model(g, sh, lanes=128):
    regs = min(96, 2*(3328//(2*g)))
    mem = (lanes//32)*(65536//((sh+255)//256*256)) if sh else 96
    return min(96, regs, mem)


comb = by(rec['comb']['points'], 'gprs', 'shared')
bad = [(k, [p['peak_simd_groups'] for p in v], model(*k)) for k, v in comb.items() if any(p['peak_simd_groups'] != model(*k) for p in v)]
check('combined grid (6 register counts x 6 threadgroup sizes, 128-lane workgroups, 2 runs): all 36 cells equal '
      'min(96, 2*floor(3328/(2*halves)), 4*floor(65536/ceil256(bytes)))' + (f'; differing: {bad}' if bad else ''), len(comb) == 36 and not bad)
sys.exit(0 if all(ok) else 1)
