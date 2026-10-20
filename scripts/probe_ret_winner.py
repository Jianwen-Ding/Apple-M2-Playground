#!/usr/bin/env python3
"""Divergent active return operands with lane 0 excluded.

Every target is an in-program decoded landing. Both uniform-return operand
substitutions and direct-jump substitutions validate complete traces. The
original unsupported diagnostics remain archived; current actual programs must
match the measured model. Default offline.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_empty_stop as E
from run_drm_cpu_clock import load

P, CF = E.P, E.CF
ROOT = E.ROOT
DATA = ROOT/'results/2026-10-20-ret-winner'
A, B = 1024, 1536
PRE, FALL = 0xfeed0001, 0xfa110001
MARKS = {'A':(0xa1100001,0xa1100002), 'B':(0xb2200001,0xb2200002)}
N = 32


def table_for(first, winner):
    site = P.drm.control_main()[1]
    addresses = {'A':0x2000+site+A, 'B':0x2000+site+B}
    other = 'B' if winner == 'A' else 'A'
    targets = [addresses[winner if i == first else other] for i in range(N)]
    return targets+[int(i >= first) for i in range(N)]+[E.SENT]*(5*N+16)


def oracle(table, first, landing, uniform_ret=True):
    tab = table.copy()
    tab[2*N:3*N] = [PRE]*N
    tab[3*N:4*N] = [MARKS[landing][0] if not uniform_ret or i < first else E.SENT for i in range(N)]
    tab[4*N:5*N] = [MARKS[landing][1]]*N
    tab[6*N:7*N] = [0]*N
    out = [E.SENT]*48+[0xa5a50000+i for i in range(16)]
    return out, tab


def build(first, winner):
    if not 1 <= first <= 31 or winner not in MARKS:
        raise ValueError((first,winner))
    P.cov.install()
    e, mov, st = P.RS.e, P.RS.mov, P.RS.agx_loop.store
    site = P.drm.control_main()[1]
    setup = e('iadd r20, r1, 0')
    for slot, reg in zip(range(2,7),range(21,26)):
        setup += mov(27, slot*N)+e(f'iadd r{reg}, r20, r27')
    setup += load(30,20,True)+mov(27,N)+e('iadd r27, r20, r27')+load(26,27,True)+e('wait 0')
    setup += mov(28,PRE)+st(28,8,21)+e('wait 0')
    uniform_pc = site+len(setup)
    setup += mov(31,0x2000+site+A)
    setup += e('if_icmp r0l, ugt, r26, 0, 1')
    ret_pc = site+len(setup)
    body = setup+e('ret r30')+e('wait 0')*2
    body += e('pop_exec r0l, 2')+mov(28,FALL)+st(28,8,24)+e('wait 0')+e('stop')
    for offset, name in ((A,'A'),(B,'B')):
        assert len(body) <= offset and (offset-len(body))%2 == 0
        body += e('stop')*((offset-len(body))//2)
        body += e('pop_exec r0l, 1')+mov(28,MARKS[name][0])+st(28,8,22)+e('wait 0')
        body += e('pop_exec r0l, 1')+mov(28,MARKS[name][1])+st(28,8,23)+e('wait 0')
        body += e('iadd r28, r0l, 0')+st(28,8,25)+e('wait 0')+e('stop')
    code = P.drm.build_main(body)
    table = table_for(first,winner)
    gates = {}
    control = None
    for offset, name in ((A,'A'),(B,'B')):
        uniform = code[:uniform_pc]+mov(31,0x2000+site+offset)+code[uniform_pc+6:]
        uniform = uniform[:ret_pc]+e('ret r31')+uniform[ret_pc+2:]
        jump_offset = site+offset-ret_pc
        jump = code[:ret_pc]+e(f'jmp_exec_any pc+{jump_offset}',f'jmp_exec_any pc+{jump_offset}')+code[ret_pc+6:]
        with E.measured_model():
            assert P.cov.simulate(uniform,N,N,64,0,table) == oracle(table,first,name), 'uniform-return surrogate failed'
            assert P.cov.simulate(jump,N,N,64,0,table) == oracle(table,first,name,uniform_ret=False), 'jump landing surrogate failed'
        gates[name] = {'uniform_return_exact':True,'jump_landing_exact':True,
                       'uniform_code':uniform.hex(),'jump_code':jump.hex()}
        if name == 'A':
            control = jump
    with E.measured_model():
        predicted = P.cov.simulate(code,N,N,64,0,table)
        assert predicted == oracle(table,first,winner), 'measured actual-return gate failed'
        actual_gate = ({'variant_uniform_active_case_exact':True} if first == 31 else
                       {'variant_lowest_active_case_exact':True})
    P.cov.gate(code, allow=('ret',))
    decoded, pc = [], 0
    while pc < len(code):
        op = P.cov.ASMB.info(code[pc:pc+16])
        assert op and op[1] > 0
        decoded.append([pc,op[0],op[1]])
        pc += op[1]
    assert pc == len(code) and [ret_pc,'ret',2] in decoded
    for offset in (A,B):
        assert any(row[0] == site+offset for row in decoded)
    return dict(code=code,control=control,table=table,n=N,wg=N,regs=64,
                expected=oracle(table,first,'A',uniform_ret=False),data_dir=DATA,
                gate=dict(first=first,winner=winner,ret_pc=ret_pc,uniform_pc=uniform_pc,
                          targets={'A':0x2000+site+A,'B':0x2000+site+B}, decoded=decoded,
                          surrogates=gates,actual_gate=actual_gate,
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          limitation='measured two-target scope; actual program and both landing paths gated'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=1)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--repeat',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    a = ap.parse_args()
    p = build(a.first,a.winner)
    print(json.dumps({'first':a.first,'winner':a.winner,'surrogate_gates':True,'actual':p['gate']['actual_gate']}),flush=True)
    if not a.hardware:
        return
    name = f'ret-winner-k{a.first}-{a.winner}-r{a.repeat}'
    r = CF.hardware(name,p)
    v = r.get('variant',{})
    if v.get('ok'):
        got = (v.get('out'),v.get('table_after'))
        r['winner_analysis'] = {name:got==oracle(p['table'],a.first,name) for name in MARKS}
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('winner_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
