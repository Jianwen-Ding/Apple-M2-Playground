#!/usr/bin/env python3
"""Offline checks of the retained bfeil verdict-A evidence (AGX-Performance-Simulator results/2026-10-12-asahi-verify). No GPU access."""
import json
from pathlib import Path
import sys

SIM = Path(__file__).resolve().parents[1].parent/'AGX-Performance-Simulator'
checks = []


def check(name, cond):
    checks.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


D = SIM/'results/2026-10-12-asahi-verify'
check('simulator evidence dir present', D.is_dir())
rec = [json.loads(l) for l in (D/'bitfield-question.txt').read_text().splitlines() if l.strip().startswith('{"case"')]
byid = {r['case']: r for r in rec}
check('70 bitfield cases recorded', len(rec) == 70)
masked = [c for c in byid if '_mask_' in c]
check('20 masked cases recorded (4 bfeil + bfi/extr/shlhi/shrhi controls)', len(masked) == 20)
check('exactly the 4 masked bfeil cases fail modulo-32 (verdict A); the other masked forms pass both',
      sorted(c for c in masked if not byid[c]['masked_mod32']) == sorted(c for c in masked if c.startswith('bfeil_')) and
      len([c for c in masked if c.startswith('bfeil_')]) == 4)
check('all 70 cases pass the 7-bit reading', all(r['default_7bit'] for r in rec))
report = (D/'README.md').read_text()
check('asahi-verify report records verdict A', 'verdict A' in report and 'Q1, bfeil shift: verdict A' in report)
sys.exit(0 if all(checks) else 1)
