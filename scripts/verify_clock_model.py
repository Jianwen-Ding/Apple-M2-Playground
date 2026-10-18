#!/usr/bin/env python3
"""The clock-read table in the simulator's cost model (cost.rs CLOCK_READ_NS) equals the mean of the two retained sweeps of the
clock-load finding (results/2026-10-18-clock-load), cell by cell. Offline."""
import gzip
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT.parent/'AGX-Performance-Simulator/rust/src/cost.rs').read_text()
m = re.search(r'const CLOCK_READ_NS: \[\[f64; 5\]; 4\] = \[(.*?)\n\];', src, re.S)
table = [[float(x) for x in re.findall(r'[\d.]+', row)] for row in re.findall(r'\[([^\]]*)\]', m.group(1))]
rec = json.load(gzip.open(ROOT/'results/2026-10-18-clock-load/clock2.json.gz'))
a, b = rec['run1']['results'], rec['run2']['results']
want = []
for n in (1, 32, 1024, 65536):
    want.append([round((next(r for r in a if r['lanes'] == n and r['copies'] == L)['cost_ns_median'] +
                        next(r for r in b if r['lanes'] == n and r['copies'] == L)['cost_ns_median'])/2) for L in (1, 2, 4, 8, 16)])
ok = table == want
print('PASS' if ok else 'FAIL', 'cost.rs CLOCK_READ_NS equals the mean of the two retained sweeps in all 20 cells')
print('PASS' if re.search(r'CLOCK_READ_LANES: \[usize; 4\] = \[1, 32, 1024, 65536\]', src) and re.search(r'CLOCK_READ_COPIES: \[usize; 5\] = \[1, 2, 4, 8, 16\]', src) else 'FAIL', 'the axes match the sweep (1 / 32 / 1,024 / 65,536 lanes, 1 / 2 / 4 / 8 / 16 copies)')
sys.exit(0 if ok else 1)
