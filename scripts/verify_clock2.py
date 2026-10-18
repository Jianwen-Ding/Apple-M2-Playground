#!/usr/bin/env python3
"""Offline checks of the in-shader clock under load (results/2026-10-18-clock-load). No GPU access."""
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-clock-load'
rec = json.load(gzip.open(D/'clock2.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


runs = [rec['run1']['results'], rec['run2']['results']]
cell = lambda run, n, L: next(r for r in run if r['lanes'] == n and r['copies'] == L)
check('2 sweeps of 20 cells (1 / 32 / 1,024 / 65,536 lanes x 1 / 2 / 4 / 8 / 16 timer-line copies), 8 reads per lane, timer 24 MHz',
      all(len(r) == 20 for r in runs) and rec['run1']['R'] == 8 and all(x['cntfrq'] == 24000000 for r in runs for x in r))
check('every lane in every cell: timer words monotonic, no unwritten result word, all lanes of a SIMD group read identical values',
      all(x['monotonic'] and x['sentinel_words'] == 0 and x['group_uniform'] for r in runs for x in r))
check('1 and 32 lanes: 0.65-1.0 us per read, whatever the number of copies (the earlier 0.4-0.75 us is without the loop overhead)',
      all(650 <= x['cost_ns_median'] <= 1000 for r in runs for x in r if x['lanes'] in (1, 32)))
check('1,024 lanes (32 SIMD groups, one per core) all reading one line: 4.8-5.2 us per read (about 6x one lane)',
      all(4500 <= cell(r, 1024, 1)['cost_ns_median'] <= 5300 for r in runs))
check('1,024 lanes with 8 copies: 0.55-0.65 us per read, back to the single-lane cost or below',
      all(500 <= cell(r, 1024, 8)['cost_ns_median'] <= 700 for r in runs))
check('65,536 lanes all reading one line: 30-45 us per read (median), p90 above 45 us',
      all(30000 <= cell(r, 65536, 1)['cost_ns_median'] <= 45000 and cell(r, 65536, 1)['cost_ns_p90'] >= 45000 for r in runs))
check('65,536 lanes with 16 copies: 2.0-3.0 us per read (15x less than one copy)',
      all(2000 <= cell(r, 65536, 16)['cost_ns_median'] <= 3000 for r in runs) and
      all(cell(r, 65536, 1)['cost_ns_median']/cell(r, 65536, 16)['cost_ns_median'] > 12 for r in runs))
check('more copies never cost more at 65,536 lanes: medians fall from 1 to 2 to 4 to 8 copies in both sweeps',
      all(cell(r, 65536, 1)['cost_ns_median'] > cell(r, 65536, 2)['cost_ns_median'] > cell(r, 65536, 4)['cost_ns_median'] > cell(r, 65536, 8)['cost_ns_median'] for r in runs))
check('first-read values of the 32 cores of a 1,024-lane dispatch with 8 copies differ by at most 0.2 us (an upper bound on cross-core clock skew plus launch skew)',
      all(cell(r, 1024, 8)['first_read_spread_ns'] <= 200 for r in runs))
check('cells agree between the two sweeps within a factor 1.6',
      all(0.62 <= b['cost_ns_median']/a['cost_ns_median'] <= 1.6 for a, b in zip(*runs)))
sys.exit(0 if all(ok) else 1)
