#!/usr/bin/env python3
"""Offline check of the retained whole-dispatch evidence (no GPU): launch cost, workgroup placement."""
import json, math, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-dispatch'
fails = 0


def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)


rows = json.loads((R/'dispatch.json').read_text())['rows']
empty = {(r['grid'], r['wg']): r['min_us'] for r in rows if r['case'] == 'empty'}
busiest = lambda n: math.ceil(math.ceil(n/4)/9)
for (n, wg), t in sorted(empty.items()):
    wgs = busiest(n//wg); groups = wgs*math.ceil(wg/32)
    model = max(0.100*wgs, 0.0136*groups)+5.6
    check(abs(model-t)/t < 0.25, f'empty dispatch {n} threads, {wg}-lane workgroups: {t:.0f} us; '
          f'max(100 ns x {wgs} workgroups, 13.6 ns x {groups} groups) + 5.6 us = {model:.0f} us')
pl = json.loads((R/'placement.json').read_text())
check(all(r['max_per_core'] == busiest(r['workgroups']) for r in pl if r['workgroups'] <= 228),
      'busiest core holds ceil(ceil(n/4)/9) workgroups for 38..228 workgroups (64- and 256-lane): '
      + ', '.join(f"{r['workgroups']}:{r['max_per_core']}" for r in pl if r['wg'] == 256))
check(all(r['cores_used'] == 34 for r in pl if r['workgroups'] == 38), '38 workgroups use only 34 cores (4 cores take 2)')
print(f'{fails} failures'); sys.exit(1 if fails else 0)
