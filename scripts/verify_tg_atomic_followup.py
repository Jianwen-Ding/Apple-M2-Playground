#!/usr/bin/env python3
"""Reconstruct and simulator-check all retained threadgroup follow-ups; no GPU."""
import gzip
import json
import probe_tg_atomic_followup as T

names = T.OPS + T.MASKS + T.BITS + T.EXTRA + T.SKIPS
files = sorted(T.DATA.glob('*.json.gz'))
assert {p.name.removesuffix('.json.gz') for p in files} == set(names)
for path in files:
    r = json.load(gzip.open(path, 'rt'))
    p = T.case(r['name'])  # Full surrogate in agx_run versus independent integer oracle.
    assert r['code'] == p['code'].hex() and r['control_code'] == p['control'].hex()
    assert r['table_in'] == p['table'] and r['shared'] == 2048
    assert r['gate'] == json.loads(json.dumps(p['gate']))
    assert T.F.matches(r['control_before'], p['expected'])
    assert T.F.matches(r['control_after'], p['expected'])
    assert r['recovery_control_passed'] and 'halted' not in r
    assert not r['kernel_log_delta'] and r['after']['budget_used'] == r['before']['budget_used']
    for snapshot in (r['before'], r['after']):
        assert snapshot['memory_cgroup'] and 'MemAvailable:' in snapshot['meminfo']
    v = r['variant']
    assert v['ok'] and v['fw_ns'] > 0
    if r['name'] in T.OPS + T.MASKS:
        expected_table = p['table'].copy()
        expected_table[192:224] = [0xfeed0001] * 32
        expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000+i for i in range(16)]
        assert T.F.matches(v, (expected_out, expected_table))
        try:
            T.P.cov.simulate(p['code'], 32, 32, 64, 2048, p['table'])
        except RuntimeError as ex:
            assert 'termination observed, memory side effects not modeled' in str(ex), str(ex)
        else:
            raise AssertionError('unmodeled opcode silently accepted')
    else:
        assert T.F.matches(v, p['expected'])
        assert T.P.cov.simulate(p['code'], 32, 32, 64, 2048, p['table']) == p['expected']
    print('PASS', r['name'])
print(f'PASS {len(files)} exact records and simulator-checked controls; 12 variant replays, 15 explicit rejections')

r = json.load(gzip.open(T.DATA / 'validation/known-good-after-watchdog-v1.json.gz', 'rt'))
p = T.case('tg-sub-bit36')
assert r['code'] == r['control_code'] == p['control'].hex()
assert r['table_in'] == p['table'] and r['phase'] == 'finished'
assert r['recovery_control_passed'] and 'halted' not in r and not r['kernel_log_delta']
assert r['before']['budget_used'] == r['after']['budget_used']
assert len(r['harness_sha256']) == 64
for stage in ('control_before', 'variant', 'control_after'):
    assert T.F.matches(r[stage], p['expected'])
    assert not r[stage].get('host_timeout')
print('PASS updated watchdog: three exact known-good hardware dispatches')
