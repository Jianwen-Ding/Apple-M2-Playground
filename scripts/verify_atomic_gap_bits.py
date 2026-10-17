#!/usr/bin/env python3
"""Offline exact checks of single-bit atomic probes, controls and recovered fault evidence."""
import gzip
import json
from pathlib import Path
import probe_control_followup as F

DATA = Path(__file__).resolve().parents[1] / 'results/2026-10-17-atomic-gap-bits'
expected_names = {f'atomic-gap{b}' for b in (26, 28, 29, 31, 42, 43, 44)} | {'atomic-gap29-op2', 'atomic-gap29-op3'}
files = sorted(DATA.glob('*.json.gz'))
assert {p.name.removesuffix('.json.gz') for p in files} == expected_names
for path in files:
    r = json.load(gzip.open(path, 'rt'))
    p = F.case(r['name'])  # Simulates complete baseline and compares independent integer oracle.
    assert r['code'] == p['code'].hex() and r['control_code'] == p['control'].hex()
    assert r['table_in'] == p['table'] and r['gate'] == json.loads(json.dumps(p['gate']))
    assert F.matches(r['control_before'], p['expected']) and F.matches(r['control_after'], p['expected'])
    assert r['recovery_control_passed'] and 'halted' not in r
    v, bit = r['variant'], p['gate']['changed_bit']
    if bit == 31:
        assert not v['ok'] and '0x1000382040' in r['kernel_log_delta'] and 'Unmapped' in r['kernel_log_delta']
        assert r['after']['budget_used'] == r['before']['budget_used'] + 1
    elif bit == 29:
        assert v['ok'] and v['table_after'] == p['table'] and v['out'][8:40] == [0]*32
        assert v['out'][:8] == p['expected'][0][:8] and v['out'][40:] == p['expected'][0][40:]
        assert r['after']['budget_used'] == r['before']['budget_used'] and not r['kernel_log_delta']
    else:
        assert F.matches(v, p['expected']) and not r['kernel_log_delta']
        assert r['after']['budget_used'] == r['before']['budget_used']
    print('PASS', r['name'])
print(f'PASS {len(files)} atomic variants, exact controls and recovery records')
