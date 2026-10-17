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
print('PASS historical records; out-of-program return behavior remains unexplained')

# Follow-up: exact reconstruction, controls, recovered faults and the measured
# all-active model. Out-of-program quiet cases remain explicitly unsupported.
import os
import probe_control_followup as F
for path in sorted((DATA / 'followup').glob('*.json.gz')):
    r = json.load(gzip.open(path, 'rt'))
    p = F.case(r['name'])
    assert p['code'].hex() == r['code'] and p['control'].hex() == r['control_code'], r['name']
    assert p['gate'] == r['gate'], r['name']
    assert F.matches(r['control_before'], p['expected']) and F.matches(r['control_after'], p['expected'])
    assert r['recovery_control_passed'] and 'halted' not in r
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        observed = P.cov.simulate(p['code'], p['n'], p['wg'], p['regs'], 0, p['table'])
    except RuntimeError as exc:
        expected_errors = {'ret-pop1': 'outside the program', 'ret-r1-pop1': 'outside the program',
                           'ret-byte-nopop': 'fell off end'}
        assert r['name'] in expected_errors and expected_errors[r['name']] in str(exc), str(exc)
        if r['name'] == 'ret-byte-nopop':
            assert not r['variant']['ok'] and '0x1000008100' in r['kernel_log_delta']
            assert r['after']['budget_used'] == r['before']['budget_used'] + 1
        else:
            assert r['variant']['ok']  # Quiet out-of-program completions remain unmodelled.
    else:
        assert r['variant']['ok'] and observed == (r['variant']['out'], r['variant']['table_after']), r['name']
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']
    print('PASS follow-up', r['name'])

# Uniform partial masks are now modelled (measured 2026-10-17): uniform
# full-mask binaries replayed with fewer lanes must be accepted, not rejected.
# (Exact per-lane values under n < 32 depend on the harness lane mapping, a
# separate untested dimension; acceptance is the contract change here.)
os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
try:
    for name in ('call-ret-pop2', 'callreg-ret-pop2'):
        r = json.load(gzip.open(DATA / 'followup' / f'{name}.json.gz', 'rt'))
        out16, tab16 = P.cov.simulate(bytes.fromhex(r['code']), 16, 32, r['regs'], 0, r['table_in'])
        assert len(out16) > 0 and len(tab16) == len(r['table_in']), name
        print(f'PASS uniform partial coverage accepted: {name}')
finally:
    del os.environ['AGX_EXPERIMENTAL_RET']

# Divergent targets with lane 0 masked out remain unmodelled and must be
# rejected for both register calls and returns.
import run_drm_compute as _drm
import record_suite as _RS
_e, _mov, _st = _RS.e, _RS.mov, _RS.agx_loop.store
_stop, _wait = _e('stop'), _e('wait 0')


def _neg_case(kind):
    _P_site = _drm.control_main()[1]
    b = _e('iadd r29, r1, 0')
    b += _mov(27, 0) + _e('iadd r20, r29, r27')
    # r30: odd lanes -> A, even lanes -> B (divergent); lane 0 (-> B) masked out.
    b += _mov(30, 0x2000 + _P_site + 512)
    b += _mov(27, 1) + _e('and r24, r29, r27') + _mov(26, 1)
    b += _RS.if_else('if_icmp r0l, seq, r24, r26, 1', None,
                      _mov(30, 0x2000 + _P_site + 1024), b'')
    # mask lane 0 out: active iff gid != 0
    b += _mov(27, 0) + _e('if_icmp r0l, ugt, r29, r27, 1')
    if kind == 'call':
        b += _e('call r30') + _wait + _wait + _stop
    else:
        b += _e('ret r30') + _wait + _wait + _stop
    # landing B (valid in-program target for the non-divergent lanes)
    b += _stop * ((512 - len(b)) // 2)
    assert len(b) == 512
    b += _e('pop_exec r0l, 2') + _mov(23, 0xBBBB0001) + _st(23, 8, 20) + _wait + _stop
    # landing A (valid in-program target)
    b += _stop * ((1024 - len(b)) // 2)
    assert len(b) == 1024
    b += _e('pop_exec r0l, 2') + _mov(23, 0xBBBB0002) + _st(23, 8, 20) + _wait + _stop
    return _drm.build_main(b)


os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
try:
    for kind in ('call', 'ret'):
        try:
            P.cov.simulate(_neg_case(kind), 32, 32, 64, 0, [0] * 128)
        except RuntimeError as exc:
            assert 'lane 0 inactive' in str(exc), f"{kind}: {exc}"
            print(f'PASS divergent {kind} with lane 0 masked stays rejected')
        else:
            raise AssertionError(f'divergent {kind} with lane 0 masked unexpectedly accepted')
finally:
    del os.environ['AGX_EXPERIMENTAL_RET']
