#!/usr/bin/env python3
"""Observe stop after a uniform partial-mask return.

The return targets in-program decoded landing instructions. A no-return direct
jump surrogate constructs control depths (even=1, odd=2), validates every
landing/checkpoint and acts as the exact recovery control. Default is offline.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_empty_stop as E

CF, P = E.CF, E.P
ROOT = P.ROOT
DATA = E.DATA
LANDING = 1024


def oracle(kills=False):
    tab = E.TABLE.copy()
    tab[:32] = [E.PRE]*32
    state = [1 if i % 2 == 0 else 2 for i in range(32)]
    if kills:
        state = [0xffff if d == 1 else d for d in state]
    for k, marker in enumerate(E.MARKS):
        state = [max(d-1, 0) for d in state]
        tab[(2+k)*32:(3+k)*32] = [marker if d == 0 else E.SENT for d in state]
    tab[160:192] = [0 if d == 0 else E.SENT for d in state]
    out = ([E.SENT]*8+[0x12345678 if d == 0 else E.SENT for d in state]
           +[E.SENT]*8+[0xa5a50000+i for i in range(16)])
    return out, tab


def build(stops):
    if stops not in (0, 1, 2, 8, 32):
        raise ValueError(stops)
    P.cov.install()
    e, mov, st = P.RS.e, P.RS.mov, P.RS.agx_loop.store
    site = P.drm.control_main()[1]
    setup = e('iadd r20, r1, 0')+e('and r30, r1, 1')
    for slot, reg in enumerate(range(21, 27)):
        setup += mov(27, slot*32)+e(f'iadd r{reg}, r20, r27')
    setup += mov(28, E.PRE)+st(28, 8, 21)+e('wait 0')
    setup += mov(31, 0x2000+site+LANDING)
    partial = setup+e('if_icmp r0l, ueq, r30, 1, 1')
    ret_pc = site+len(partial)
    partial += e('ret r31')+e('wait 0')*2
    fallback = (e('pop_exec r0l, 2')+mov(28, 0xfa110001)
                +st(28, 8, 22)+e('wait 0')+e('stop'))
    body = partial+fallback
    assert len(body) <= LANDING and (LANDING-len(body)) % 2 == 0
    body += e('stop')*((LANDING-len(body))//2)
    # All possible return destinations are inside the final code. The return
    # lands at the first stop, or the first pop when stops==0, never padding.
    landing = e('stop')*stops
    for reg, marker in zip((23, 24, 25), E.MARKS):
        landing += e('pop_exec r0l, 1')+mov(28, marker)+st(28, 8, reg)+e('wait 0')
    landing += e('iadd r28, r0l, 0')+st(28, 8, 26)+e('wait 0')+mov(2, 0x12345678)
    code = P.drm.build_main(body+landing)
    # Known-op control constructs the return-arrival depths using only IFs,
    # jumps while no lane is active and uses waits in the stop test region.
    control_setup = setup+e('if_icmp r0l, ueq, r30, 0, 1')+e('if_icmp r0l, ueq, r30, 255, 1')
    jump_pc = site+len(control_setup)
    offset = site+LANDING-jump_pc
    control_body = control_setup+e(f'jmp_exec_none pc+{offset}', f'jmp_exec_none pc+{offset}')
    control_body += fallback
    assert len(control_body) <= LANDING and (LANDING-len(control_body)) % 2 == 0
    control_body += e('stop')*((LANDING-len(control_body))//2)
    control = P.drm.build_main(control_body+e('wait 0')*stops+landing[2*stops:])
    P.cov.gate(code, allow=('ret',))
    P.cov.gate(control)
    with E.measured_model():
        assert P.cov.simulate(control, 32, 32, 64, 0, E.TABLE) == oracle(), 'landing surrogate failed'
        assert P.cov.simulate(code, 32, 32, 64, 0, E.TABLE) == oracle(kills=bool(stops)), 'measured return/stop gate failed'
    try:
        P.cov.simulate(code, 32, 32, 64, 0, E.TABLE)
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc)
    else:
        raise AssertionError('ret must be opt-in')
    decoded, pc = [], 0
    while pc < len(code):
        op = P.cov.ASMB.info(code[pc:pc+16])
        assert op and op[1] > 0
        decoded.append([pc, op[0], op[1]])
        pc += op[1]
    assert pc == len(code)
    assert [ret_pc, 'ret', 2] in decoded
    assert any(row[0] == site+LANDING for row in decoded)
    return dict(code=code, control=control, table=E.TABLE, n=32, wg=32, regs=64,
                expected=oracle(), data_dir=DATA,
                gate=dict(stops=stops, ret_pc=ret_pc, target=0x2000+site+LANDING,
                          landing_pc=site+LANDING, decoded=decoded,
                          known_jump_surrogate_exact=True, actual_measured_model_exact=True,
                          default_ret_rejected=True, predicted_variant=oracle(kills=bool(stops)),
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stops', type=int, choices=(0,1,2,8,32), default=0)
    ap.add_argument('--repeat', type=int, default=0)
    ap.add_argument('--hardware', action='store_true')
    a = ap.parse_args()
    p = build(a.stops)
    print(json.dumps({'stops': a.stops, 'gate': True}), flush=True)
    if not a.hardware:
        return
    name = f'ret-empty-stop-{a.stops}-r{a.repeat}'
    r = CF.hardware(name, p)
    v = r.get('variant', {})
    if v.get('ok'):
        got = (v.get('out'), v.get('table_after'))
        r['stop_analysis'] = dict(matches_kill_model=got == oracle(kills=bool(a.stops)),
                                  matches_no_kill_model=got == oracle(),
                                  checkpoint_lanes=[[i for i in range(32) if v['table_after'][(2+k)*32+i] == marker]
                                                    for k, marker in enumerate(E.MARKS)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'), mode='wb', mtime=0) as f:
        f.write((json.dumps(r, sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('stop_analysis'), 'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'), 'budget':r['after']['budget_used']}), flush=True)
    if r.get('halted'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
