#!/usr/bin/env python3
"""Offline check: else_fcmp / while_fcmp / if_fcmp straight-line results equal their icmp twins."""
import gzip, json, sys
from pathlib import Path
r = json.loads(gzip.open(Path(__file__).resolve().parents[1]/'results/2026-10-11-cf-float/cf-float.json.gz').read())['cases']
ok = len(r) == 42 and all(c['int'] == c['float'] for c in r)
w = [c for c in r if c['struct'] == 'while' and c['c1'] == 'gt' and c['t1'] == 13][0]['int']['r2']
ok2 = [v & 15 for v in w] == [0xb]*14+[0xc]*18      # while keeps lanes where the condition holds (x > 13)
print(('ok   ' if ok else 'FAIL ')+f'{len(r)} cases: float forms equal integer twins (final r2 and all r0l snapshots)')
print(('ok   ' if ok2 else 'FAIL ')+'while_*cmp keeps active the lanes whose condition is true')
sys.exit(0 if ok and ok2 else 1)
