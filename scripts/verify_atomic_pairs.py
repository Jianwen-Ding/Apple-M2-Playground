#!/usr/bin/env python3
"""Offline checks of the device-atomic gap-bit pair evidence (results/2026-10-19-atomic-pairs). No GPU access."""
import gzip, json, sys
from pathlib import Path

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-atomic-pairs'
checks = []
PAIRS = ['26+28', '26+42', '26+43', '26+44', '28+42', '28+43', '28+44', '42+43', '42+44', '43+44']


def check(name, cond):
    checks.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


recs = {}
for pr in PAIRS:
    d = json.load(gzip.open(D/f'atomic-gap{pr}.json.gz'))
    recs[pr] = d
check('all 10 pairs recorded', set(recs) == set(PAIRS))
ok = True
for pr, d in recs.items():
    v, c = d['variant'], d['control_before']
    if not (v.get('ok') and c.get('ok') and d.get('recovery_control_passed') and not d.get('halted')):
        ok = False; print('  run problem:', pr)
    if v.get('table_after') != c.get('table_after') or v.get('out') != c.get('out'):
        ok = False; print('  differs from control:', pr)
    if d.get('kernel_log_delta'):
        ok = False; print('  kernel messages:', pr)
    if d['after']['budget_used'] != 0:
        ok = False; print('  budget used:', pr)
check('every pair: variant bit-identical to control, recovery exact, no kernel messages, budget 0', ok)
check('gate recorded (surrogate exact sim + decode, allowed mask = the two bits)',
      all(set(r['gate']) >= {'baseline_add_matches_independent_oracle', 'changed_bits'} for r in recs.values()))
sys.exit(0 if all(checks) else 1)
