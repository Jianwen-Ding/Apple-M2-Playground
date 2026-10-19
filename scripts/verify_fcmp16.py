#!/usr/bin/env python3
"""Offline checks of the retained fp16 compare evidence (results/2026-10-19-fcmp16). No GPU access."""
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_drm_fcmp16 import ieee, VALS16, M, CONDS

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-fcmp16'
checks = []


def check(name, ok):
    checks.append(bool(ok))
    print('PASS' if ok else 'FAIL', name)


rec = json.load(gzip.open(D/'fcmp16.json.gz'))
check('record covers all 7 conditions over 31 half edge values', rec['conds'] == CONDS and rec['vals'] == VALS16)
check('2 repeats x 7 conditions', len(rec['results']) == 14)
n = M*M
A = [VALS16[i//M] for i in range(n)]; B = [VALS16[i % M] for i in range(n)]
want = {c: [ieee(c, x, y) for x, y in zip(A, B)] for c in CONDS}
check('host oracle is exact IEEE (subnormal halves ordered, not flushed)',
      want['lt'][2] == 1 and want['eq'][1] == 1)  # +0 < 0x1; +0 == -0
ok = True
for r in rec['results']:
    if r['out'] != want[r['cond']] or not r['inputs_intact']:
        ok = False; break
check('all 961 pairs exact vs IEEE in every run, inputs intact', ok)
check('upper halves stay zero (r20 pre-zeroed, full-word check)',
      all(v in (0, 1) for r in rec['results'] for v in r['out']))
sys.exit(0 if all(checks) else 1)
