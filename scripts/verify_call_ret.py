#!/usr/bin/env python3
"""Offline checks of retained call/ret evidence and simulator rejection. No GPU access."""
import gzip
import json
from pathlib import Path
import probe_ret_landing as P

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'results/2026-10-17-call-ret'
P.cov.install()
old = json.load(gzip.open(DATA / 'records.json.gz', 'rt'))['records']
for r in old:
    code = bytes.fromhex(r['code'])
    if r['name'].startswith('C1'):
        assert P.cov.simulate(code, r['n'], r['wg'], r['regs'], 0, r['table_in']) == (r['out'], r['table_after']), r['name']
    else:
        try:
            P.cov.simulate(code, r['n'], r['wg'], r['regs'], 0, r['table_in'])
        except RuntimeError as exc:
            assert 'ret semantics unresolved' in str(exc), str(exc)
        else:
            raise AssertionError(f"unvalidated return accepted: {r['name']}")
print('PASS three retained direct calls replay exactly; all three old returns rejected')

records = json.load(gzip.open(DATA / 'landing-records.json.gz', 'rt'))['records']
assert len(records) == 2
for r in records:
    P.VALUE = r['target_value']
    P.LANDINGS = tuple(r['landing_offsets'])
    code, surrogate = P.build()
    assert code.hex() == r['code'] and surrogate.hex() == r['surrogate_code']
    assert P.gate(code, surrogate) == r['gate']
    control = r['control_before']
    assert (control['out'], control['table_after']) == P.expected(1)
    if r['target_value'] == 1024:
        assert 'failure' not in r and not r['kernel_log_delta']
        v = r['variant']
        assert (v['out'], v['table_after']) == P.expected(0)
        c = r['control_after']
        assert (c['out'], c['table_after']) == P.expected(1)
        assert r['after']['budget_used'] == r['before']['budget_used']
    else:
        assert r['target_value'] == 4608
        assert 'failure' in r and 'variant' not in r and 'control_after' not in r
        assert r['after']['budget_used'] == r['before']['budget_used'] + 1
        assert '0x1000008100' in r['kernel_log_delta'] and 'Unmapped' in r['kernel_log_delta']
        assert (DATA / 'R1-halfword-kernel-log.txt').read_text() == r['kernel_log_delta']
        raw = json.load(gzip.open(DATA / 'fault-harness-files.json.gz', 'rt'))
        assert bytes.fromhex(raw['c.bin']) == code + bytes(16)
    print(f"PASS {r['name']}: exact bytes, simulator surrounding paths, retained outcome")
print('PASS: return behavior remains unexplained; no return-model validation claimed')
