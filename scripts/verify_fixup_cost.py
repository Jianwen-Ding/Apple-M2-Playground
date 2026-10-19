#!/usr/bin/env python3
"""Offline checks of the retained fix-up cost evidence (results/2026-10-19-fixup-cost). No GPU access."""
import gzip
import json
import statistics as st
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-fixup-cost'
checks = []


def check(name, ok):
    checks.append(bool(ok))
    print('PASS' if ok else 'FAIL', name)


rec = json.load(gzip.open(D/'fixup_cost.json.gz'))
check('matrix complete: 4 programs x 15 samples', len(rec['results']) == 60 and rec['n'] == 64)
check('every dispatch oracle-correct with firmware timestamps and keeper stopped',
      all(r['out_ok'] and r['fw_ns'] for r in rec['results']) and rec.get('keeper_stopped') is True)
g = {}
for r in rec['results']:
    g.setdefault(r['variant'], []).append(r['fw_ns'])
check('all 4 cells have 15 samples', all(len(v) == 15 for v in g.values()))
med = {k: st.median(v) for k, v in g.items()}
expected = {None: 5250, 'eq': 18250, 'min': 18583, 'neu': 18125}
check('all 4 medians match the retained record', all(med[k] == v for k, v in expected.items()))
per = {v: (med[v]-med[None])/rec['n'] for v in ('eq', 'min', 'neu')}
check('per-fixup costs within 190-215 ns (fetch-bound, variants indistinguishable): %s' %
      {k: round(v) for k, v in per.items()}, all(190 < v < 215 for v in per.values()))
sys.exit(0 if all(checks) else 1)
