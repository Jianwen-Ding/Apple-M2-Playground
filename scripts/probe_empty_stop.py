#!/usr/bin/env python3
"""Checkpoint empty-mask stop versus wait at controlled execution-mask depths.

Default is offline. --hardware submits one simulator-gated case with exact
before/after wait controls, bounded watchdog, kernel and memory diagnostics.
No call, ret, jump, loop, barrier or uninitialized source is involved.
"""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path

import probe_control_followup as CF

P = CF.P
ROOT = P.ROOT
DATA = ROOT/'results/2026-10-20-empty-stop'
CASES = ('all1', 'all2', 'all3', 'mix12', 'mix13', 'mix23', 'mix01')
N = 32
SENT = 0xcdcdcdcd
PRE = 0xa1100000
CHECKPOINT = 0xa1100001
MARKS = (0xa1100011, 0xa1100012, 0xa1100013)
TABLE = [SENT]*(6*N+16)


@contextmanager
def measured_model():
    old = os.environ.get('AGX_EXPERIMENTAL_RET')
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        yield
    finally:
        if old is None:
            del os.environ['AGX_EXPERIMENTAL_RET']
        else:
            os.environ['AGX_EXPERIMENTAL_RET'] = old


def first_mask(case):
    # For mixed cases odd lanes remain active, even lanes reach depth 1.
    return [case.startswith('mix') and bool(i & 1) for i in range(N)]


def depths(case):
    if case.startswith('all'):
        return [int(case[-1])]*N
    a, b = map(int, case[-2:])
    return [b if i % 2 == 0 else a for i in range(N)]


def oracle(case, stop=False):
    tab = TABLE.copy()
    tab[:N] = [PRE]*N
    tab[N:2*N] = [CHECKPOINT if live else SENT for live in first_mask(case)]
    state = depths(case)
    live = [not (stop and d == 0) for d in state]
    for k, marker in enumerate(MARKS):
        state = [max(d-1, 0) for d in state]
        tab[(2+k)*N:(3+k)*N] = [marker if alive and d == 0 else SENT for d,alive in zip(state,live)]
    tab[5*N:6*N] = [0 if alive and d == 0 else SENT for d,alive in zip(state,live)]
    payload = [0x12345678 if alive and d == 0 else SENT for d,alive in zip(state,live)]
    out = [SENT]*8+payload+[SENT]*8+[0xa5a50000+i for i in range(16)]
    return out, tab


def build(case):
    if case not in CASES:
        raise ValueError(case)
    P.cov.install()
    e, mov, st = P.RS.e, P.RS.mov, P.RS.agx_loop.store
    code = e('iadd r20, r1, 0')+e('and r30, r1, 1')
    for slot, reg in enumerate(range(21, 27)):
        code += mov(27, slot*N)+e(f'iadd r{reg}, r20, r27')
    code += mov(28, PRE)+st(28, 8, 21)+e('wait 0')
    if case.startswith('all'):
        code += e('if_icmp r0l, ueq, r30, 255, 1')
    else:
        code += e('if_icmp r0l, ueq, r30, 1, 1')
    code += mov(28, CHECKPOINT)+st(28, 8, 22)+e('wait 0')
    push = e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    false = e('if_icmp r0l, ueq, r30, 255, 1')
    if case.startswith('all'):
        code += push*(int(case[-1])-1)
    elif case == 'mix12':
        code += false
    elif case == 'mix13':
        code += push+false
    elif case == 'mix23':
        code += false+push
    stop_pc = P.drm.control_main()[1]+len(code)
    code += e('stop')
    for reg, marker in zip((23, 24, 25), MARKS):
        code += e('pop_exec r0l, 1')+mov(28, marker)+st(28, 8, reg)+e('wait 0')
    code += e('iadd r28, r0l, 0')+st(28, 8, 26)+e('wait 0')+mov(2, 0x12345678)
    code = P.drm.build_main(code)
    assert code[stop_pc:stop_pc+2] == bytes.fromhex('8800')
    control = code[:stop_pc]+e('wait 0')+code[stop_pc+2:]
    assert len(code) == len(control) and code[-2:] == e('stop')
    P.cov.gate(code)
    with measured_model():
        expected = oracle(case)
        expected_var = oracle(case, stop=True)
        assert P.cov.simulate(control, N, N, 64, 0, TABLE) == expected, 'wait surrogate oracle failed'
        actual = P.cov.simulate(code, N, N, 64, 0, TABLE)
        assert actual == expected_var, 'actual simulator stop hypothesis differs from scalar model'
    # Enumerate exact instruction boundaries; no unknown transfers enter a
    # padding region or run outside the program.
    pc, decoded = 0, []
    while pc < len(code):
        op = P.cov.ASMB.info(code[pc:pc+16])
        assert op and op[1] > 0
        decoded.append([pc, op[0], op[1]])
        pc += op[1]
    assert pc == len(code) and any(row == [stop_pc, 'stop', 2] for row in decoded)
    return dict(code=code, control=control, table=TABLE, n=N, wg=N, regs=64,
                expected=expected, data_dir=DATA,
                gate=dict(case=case, stop_pc=stop_pc, stop_hex='8800', control_hex='3800',
                          variant_matches_simulator_hypothesis=True,
                          wait_surrogate_matches_scalar_oracle=True,
                          expected_depths=depths(case), decoded=decoded,
                          expected_variant=expected_var,
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          limitation='measured stop ends issuing lanes and preserves masked survivors'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case', choices=CASES)
    ap.add_argument('--hardware', action='store_true')
    ap.add_argument('--repeat', type=int, default=0)
    a = ap.parse_args()
    p = build(a.case)
    print(json.dumps({'case': a.case, 'simulator_gate': True, 'stop_pc': p['gate']['stop_pc']}), flush=True)
    if not a.hardware:
        return
    # Shared unsafe harness saves exact bytes before dispatch and preserves
    # kernel/memory/process diagnostics on failure, then validates recovery.
    r = CF.hardware(f'empty-stop-{a.case}-r{a.repeat}', p)
    v = r.get('variant', {})
    r['stop_analysis'] = dict(variant_completed=v.get('ok', False))
    if v.get('ok'):
        got = (v.get('out'), v.get('table_after'))
        r['stop_analysis'].update(matches_measured_model=got == oracle(a.case, stop=True),
                                  checkpoint_lanes=[[i for i in range(N) if v['table_after'][(2+k)*N+i] == marker]
                                                    for k, marker in enumerate(MARKS)])
    path = DATA/f'empty-stop-{a.case}-r{a.repeat}.json.gz'
    with gzip.GzipFile(filename=str(path), mode='wb', mtime=0) as f:
        f.write((json.dumps(r, sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis': r['stop_analysis'], 'recovery': r.get('recovery_control_passed'),
                      'halted': r.get('halted'), 'budget': r['after']['budget_used']}), flush=True)
    if r.get('halted'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
