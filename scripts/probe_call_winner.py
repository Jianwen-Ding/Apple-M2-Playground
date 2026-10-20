#!/usr/bin/env python3
"""Indirect call selection with divergent operands and a masked physical lane 0.

No ret, loops or barriers. Candidate targets are decoded in-program callees
that trace entry/link, pop the mask and end. Both filtered uniform-call paths
and forced jump paths are simulator-gated before hardware. Default offline.
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
DATA = ROOT/'results/2026-10-20-call-winner'
A, B = 1024,1536
PRE,FALL = 0xfeed0001,0xfa110001
MARKS = {'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002)}
N = 32


def table_for(first,winner):
    site = P.drm.control_main()[1]
    addresses = {'A':0x2000+site+A,'B':0x2000+site+B}
    other = 'B' if winner == 'A' else 'A'
    return ([addresses[winner if i == first else other] for i in range(N)]
            +[int(i >= first) for i in range(N)]+[E.SENT]*(6*N+16))


def oracle(table,landing,link,fall=False):
    tab = table.copy();tab[64:96] = [PRE]*N
    target = 0x2000+P.drm.control_main()[1]+{'A':A,'B':B}[landing]
    entered = [bool(table[32+i]) and table[i] == target for i in range(N)]
    if fall:
        tab[192:224] = [FALL]*N
    else:
        tab[96:128] = [MARKS[landing][0] if entered[i] else E.SENT for i in range(N)]
        tab[128:160] = [link if entered[i] else E.SENT for i in range(N)]
        tab[160:192] = [MARKS[landing][1]]*N
        tab[224:256] = [0]*N
    out = [E.SENT]*48+[0xa5a50000+i for i in range(16)]
    return out,tab


def build(first,winner):
    if not 0 <= first <= 31 or winner not in MARKS:
        raise ValueError((first,winner))
    P.cov.install()
    e,mov,st = P.RS.e,P.RS.mov,P.RS.agx_loop.store
    site = P.drm.control_main()[1]
    setup = e('iadd r20, r1, 0')
    for slot,reg in zip(range(2,8),range(21,27)):
        setup += mov(27,slot*N)+e(f'iadd r{reg}, r20, r27')
    setup += load(30,20,True)+mov(27,N)+e('iadd r27, r20, r27')+load(10,27,True)+e('wait 0')
    setup += mov(28,PRE)+st(28,8,21)+e('wait 0')
    initial_link_pc = site+len(setup)
    setup += mov(1,0xf1f10000)
    uniform_pc = site+len(setup)
    setup += mov(31,0x2000+site+A)
    setup += e('icmpsel ueq, r29, r30, r31, r10, 0')
    mask_pc = site+len(setup)
    setup += e('if_icmp r0l, ugt, r10, 0, 1')
    call_pc = site+len(setup);link = 0x2000+call_pc+2
    body = setup+e('call r30')+e('wait 0')*2
    body += e('pop_exec r0l, 1')+mov(28,FALL)+st(28,8,25)+e('wait 0')+e('stop')
    for offset,name in ((A,'A'),(B,'B')):
        assert len(body) <= offset and (offset-len(body))%2 == 0
        body += e('stop')*((offset-len(body))//2)
        body += mov(28,MARKS[name][0])+st(28,8,22)+st(1,8,23)+e('wait 0')
        body += e('pop_exec r0l, 1')+mov(28,MARKS[name][1])+st(28,8,24)+e('wait 0')
        body += e('iadd r28, r0l, 0')+st(28,8,26)+e('wait 0')+e('stop')
    code = P.drm.build_main(body);table = table_for(first,winner)
    gates = {};control = None
    for offset,name in ((A,'A'),(B,'B')):
        known = code[:uniform_pc]+mov(31,0x2000+site+offset)+code[uniform_pc+6:]
        old_if = e('if_icmp r0l, ugt, r10, 0, 1')
        new_if = e('if_icmp r0l, ugt, r29, 0, 1')
        assert len(old_if) == len(new_if)
        known = known[:mask_pc]+new_if+known[mask_pc+len(old_if):]
        uniform = known[:call_pc]+e('call r31')+known[call_pc+2:]
        eligible = any(table[32+i] and table[i] == 0x2000+site+offset for i in range(N))
        jump_op = 'jmp_exec_any' if eligible else 'jmp_exec_none'
        delta = site+offset-call_pc
        jump = known[:call_pc]+e(f'{jump_op} pc+{delta}',f'{jump_op} pc+{delta}')+known[call_pc+6:]
        jump = jump[:initial_link_pc]+mov(1,link)+jump[initial_link_pc+6:]
        with E.measured_model():
            assert P.cov.simulate(uniform,N,N,64,0,table) == oracle(table,name,link,fall=not eligible), 'filtered uniform-call gate failed'
            assert P.cov.simulate(jump,N,N,64,0,table) == oracle(table,name,link), 'forced landing gate failed'
        gates[name] = dict(uniform_exact=True,jump_exact=True,uniform_code=uniform.hex(),jump_code=jump.hex())
        if name == 'B':control = jump
    with E.measured_model():
        prediction = P.cov.simulate(code,N,N,64,0,table)
        assert prediction == oracle(table,winner,link), 'measured actual-call gate failed'
        actual_gate = (dict(variant_lane0_active_exact=True) if first == 0 else
                       dict(variant_lowest_active_case_exact=True))
    P.cov.gate(code,allow=('call',))
    decoded,pc = [],0
    while pc < len(code):
        op = P.cov.ASMB.info(code[pc:pc+16]);assert op and op[1]>0
        decoded.append([pc,op[0],op[1]]);pc += op[1]
    assert pc == len(code) and [call_pc,'call',2] in decoded
    assert all(any(row[0] == site+offset for row in decoded) for offset in (A,B))
    return dict(code=code,control=control,table=table,n=N,wg=N,regs=64,
                expected=oracle(table,'B',link),data_dir=DATA,
                gate=dict(first=first,winner=winner,call_pc=call_pc,link=link,decoded=decoded,
                          surrogates=gates,actual_gate=actual_gate,
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          limitation='measured two-target scope; actual program, landings and empty fallthrough gated'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=1)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--repeat',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    a = ap.parse_args();p = build(a.first,a.winner)
    print(json.dumps({'first':a.first,'winner':a.winner,'surrogate_gates':True,'actual':p['gate']['actual_gate']}),flush=True)
    if not a.hardware:return
    name = f'call-winner-k{a.first}-{a.winner}-r{a.repeat}'
    r = CF.hardware(name,p);v = r.get('variant',{})
    if v.get('ok'):
        got = (v.get('out'),v.get('table_after'))
        r['winner_analysis'] = {name:got==oracle(p['table'],name,p['gate']['link']) for name in MARKS}
        r['winner_analysis']['fall'] = got == oracle(p['table'],'A',p['gate']['link'],fall=True)
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('winner_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__ == '__main__':main()
