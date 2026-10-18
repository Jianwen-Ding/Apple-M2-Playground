#!/usr/bin/env python3
"""Offline checks of the retained cross-dispatch visibility run (results/2026-10-18-dispatch-visibility). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-dispatch-visibility'
rec = json.load(gzip.open(D/'dv.json.gz'))
rs = rec['results']
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


g = collections.Counter((r['load'], r['store'], r['invalidate']) for r in rs)
check('24 runs: cached/coherent load x normal/coherent store x invalidate/none x 3 repeats', len(rs) == 24 and len(g) == 8 and all(v == 3 for v in g.values()))
check('every run: 65,536 lanes, 16 dispatches in order, all with firmware timestamps',
      rec['lanes'] == 65536 and all(r['dispatches'] == 16 and len(r['fw_ns']) == 16 and min(r['fw_ns']) > 0 for r in rs))
check('every lane counter ends at exactly 16 (each dispatch ran once, every store reached the next dispatch)', all(r['counters_ok'] for r in rs))
check('no cached or coherent load of the partner counter returned a value older than the previous dispatch (0 of 24 x 16 x 65,536)',
      all(r['stale_loads'] == 0 and r['lanes_with_stale'] == 0 for r in rs))
sys.exit(0 if all(ok) else 1)
