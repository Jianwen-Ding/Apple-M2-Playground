#!/usr/bin/env python3
"""Offline checks of the imageblock occupancy measurement (results/2026-10-18-imageblock-occupancy). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-imageblock-occupancy'
rs = json.load(gzip.open(D/'ib_occ.json.gz'))['results']
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


g = collections.defaultdict(dict)
for r in rs:
    g[(r['name'], r['rep'])][r['kind']] = r
names = sorted({k[0] for k in g})
check('12 imageblock Shared words (layouts 32x32 / 32x16 / 16x16, sample strides, sample counts) x 3 repeats, each with the plain-layout word of the same bytes field; every per-core counter back to zero',
      len(names) == 12 and len(rs) == 72 and all(r['back_to_zero'] for r in rs))
check('every imageblock word gives exactly the peak occupancy of the plain word with the same bytes field (36 of 36 pairs)',
      all(v['imageblock']['peak_groups'] == v['plain']['peak_groups'] for v in g.values()) and len(g) == 36)


def model(bf):
    b = bf*256 if bf else 65536
    return min(96, 4*(65536//b))


check('the peak equals 4 x floor(65536 / bytes) groups (bytes = field x 256, field 0 = 64 KiB) for all 72 runs: 8 KiB -> 32, 16 KiB -> 16, 24 KiB -> 8, 32 KiB -> 8, 56 KiB -> 4, 64 KiB -> 4',
      all(r['peak_groups'] == model(r['bytes_field']) for r in rs) and {r['bytes_field']*256 for r in rs} == {0, 8192, 16384, 24576, 32768, 57344})
check('the imageblock width / height, sample stride and sample count fields change nothing: 32x32 vs 32x16 vs 16x16 at 8 KiB all give 32 groups',
      len({r['peak_groups'] for r in rs if r['name'] in ('32x32-s8', '32x16-s8', '16x16-s8')}) == 1)
sys.exit(0 if all(ok) else 1)
