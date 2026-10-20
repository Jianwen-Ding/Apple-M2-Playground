#!/usr/bin/env python3
"""Test balanced execution-counter reservation around nested calls.

A two-count push preserves masked lanes across each call/ret/pop2 pair. Test
outer/inner reserves independently, with initialized valid saved links and an
explicit original-mask pop before final full-group diagnostics/termination.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_nested_partial_outer as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-call-mask-reserve'
DONE=0xe2200001


def table_for(first,winner,seed):
    base=B.table_for(first,winner,seed)
    return base[:512]+[E.SENT]*(3*32+16)


def oracle(table,winner,ol,il,outer_reserve,inner_reserve):
    total=outer_reserve+inner_reserve;tab=table.copy()
    target=0x2000+P.drm.control_main()[1]+B.N.CALLEES[winner]
    for lane,operand in enumerate(table[:32]):
        admitted=bool(table[480+lane]);inner=admitted and operand==target
        values={1:B.N.PRE,16:DONE,17:ol if admitted or total==0 else lane}
        if admitted:values.update({2:ol,3:B.N.OUT_MARK})
        if inner:values.update({4:il,5:B.N.INNER_MARK[winner]})
        if not inner and (admitted or total==0):values.update({6:0,7:0,18:0 if total==0 else 1+total})
        if admitted or total==0:values.update({8:0,9:il if admitted else lane,10:ol})
        if not admitted and total==2:values.update({13:0,14:0})
        if admitted or total!=4:values.update({11:B.N.CONT,12:ol if admitted or total==0 else lane})
        for plane,value in values.items():tab[plane*32+lane]=value
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def construct(outer,outer_reserve,inner_reserve):
    code,ol,il,op,ip,_=B.construct(outer,2);e,mov,write,mark,counter=B.N.helpers()
    outer_start=P.drm.control_main()[1]+B.N.OUTER
    inner_start=P.drm.control_main()[1]+min(B.N.CALLEES.values())
    stop=e('stop');push=lambda n:e(f'if_fcmp r0l, eq, 0.0, 0.0, {n}',f'push_exec r0l, {n}') if n else b''
    # Finish trace under the restored caller mask, then pop its original IF.
    old=mark(11,B.N.CONT)+write(12,1)+stop
    new=mark(11,B.N.CONT)+write(12,1)+e('pop_exec r0l, 1')+mark(16,DONE)+write(17,1)+e('pop_exec r0l, 1')*8+stop
    prefix=code[:outer_start];assert prefix.count(old)==1
    prefix=prefix.replace(old,new);grow=len(new)-len(old)
    assert prefix[-grow:]==stop*(grow//2)
    code=prefix[:-grow]+code[outer_start:]
    # Reserve the outer call, preserving the function's absolute address.
    outer_push=push(outer_reserve);new_op=op+len(outer_push);new_ol=ol+len(outer_push)
    prefix=code[:op];old_seed=mov(29,ol);assert prefix.count(old_seed)==1
    prefix=prefix.replace(old_seed,mov(29,new_ol))
    transfer=code[op:op+6]
    if outer=='direct':transfer=(0xc010|(((outer_start-new_op)&0xffffffff)<<16)).to_bytes(6,'little')
    assert code[outer_start-len(outer_push):outer_start]==stop*(len(outer_push)//2)
    code=prefix+outer_push+transfer+code[op+6:outer_start-len(outer_push)]+code[outer_start:]
    # Reserve the inner call and directly gather masked original lane 0's low
    # counter at return arrival, before any pop changes it.
    inner_push=push(inner_reserve);new_ip=ip+len(inner_push);new_il=0x2000+new_ip+2
    gather=mov(27,0xffff)+e('simd_shuffle r28, r0, 0')+e('and r28, r28, r27')+write(18)
    trim=len(inner_push)+len(gather)
    assert code[inner_start-trim:inner_start]==stop*(trim//2)
    code=code[:ip]+inner_push+code[ip:ip+6]+gather+code[ip+6:inner_start-trim]+code[inner_start:]
    P.cov.gate(code,allow=('call','ret'))
    boundaries=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code) and all(x-0x2000 in boundaries for x in (new_ol,new_il,*B.N.targets(17,'A')))
    return code,new_ol,new_il,new_op,new_ip,boundaries


def control(winner,ol,il,outer_reserve,inner_reserve):
    total=outer_reserve+inner_reserve;e,mov,write,mark,counter=B.N.helpers()
    target=0x2000+P.drm.control_main()[1]+B.N.CALLEES[winner]
    body=e('iadd r20, r1, 0')+B.N.load(30,20,True)+mov(12,480)+e('iadd r13, r20, r12')+B.N.load(10,13,True)+e('wait 0')
    body+=mark(1,B.N.PRE)+mov(29,ol)+mov(31,target)
    body+=e('if_icmp r0l, ueq, r10, 1, 1')+mov(1,ol)+write(2,1)+mark(3,B.N.OUT_MARK)+mov(1,il)+e('pop_exec r0l, 1')
    body+=e('icmpsel ueq, r11, r30, r31, 1, 0')+e('and r11, r11, r10')+e('xor r2, r10, r11')
    body+=e('if_icmp r0l, ueq, r11, 1, 1')+write(4,1)+mark(5,B.N.INNER_MARK[winner])+e('pop_exec r0l, 1')
    cond='if_icmp r0l, ueq, r11, 0, 1' if total==0 else 'if_icmp r0l, ueq, r2, 1, 1'
    body+=e(cond)+mark(6,0)+mark(7,0)+mark(18,0 if total==0 else 1+total)+e('pop_exec r0l, 1')
    if total:body+=e('if_icmp r0l, ueq, r10, 1, 1')
    body+=mark(8,0)+write(9,1)+write(10,29)+mov(1,ol)
    if total:body+=e('pop_exec r0l, 1')
    if total==2:body+=e('if_icmp r0l, ueq, r10, 0, 1')+mark(14,0)+mark(13,0)+e('pop_exec r0l, 1')
    if total==4:body+=e('if_icmp r0l, ueq, r10, 1, 1')
    body+=mark(11,B.N.CONT)+write(12,1)
    if total==4:body+=e('pop_exec r0l, 1')
    body+=mark(16,DONE)+write(17,1)+e('stop')
    result=P.drm.build_main(body);P.cov.gate(result)
    return result


def build(outer,first,winner,seed,outer_reserve,inner_reserve):
    assert first in (1,5,16,24) and outer_reserve in (0,2) and inner_reserve in (0,2)
    code,ol,il,op,ip,bounds=construct(outer,outer_reserve,inner_reserve);table=table_for(first,winner,seed)
    ctrl=control(winner,ol,il,outer_reserve,inner_reserve);want=oracle(table,winner,ol,il,outer_reserve,inner_reserve)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==want,'known scalar control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==want,'actual balanced-reserve hypothesis failed'
        for name in B.N.CALLEES:
            t=table_for(first,name,seed)
            assert P.cov.simulate(code,32,32,64,0,t)==oracle(t,name,ol,il,outer_reserve,inner_reserve),name
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=want,data_dir=DATA,
        gate=dict(outer_kind=outer,first=first,winner=winner,seed=seed,outer_reserve=outer_reserve,inner_reserve=inner_reserve,
                  outer_link=ol,inner_link=il,outer_pc=op,inner_pc=ip,boundaries=bounds,
                  all_saved_links_initialized=True,complete_actual_exact=True,no_call_control_exact=True,all_three_winners_exact=True,
                  base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outer',choices=('direct','indirect'),default='direct')
    ap.add_argument('--first',type=int,choices=(1,5,16,24),default=1)
    ap.add_argument('--winner',choices=tuple(B.N.CALLEES),default='A')
    ap.add_argument('--seed',type=int,default=17)
    ap.add_argument('--outer-reserve',type=int,choices=(0,2),default=2)
    ap.add_argument('--inner-reserve',type=int,choices=(0,2),default=2)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.outer,a.first,a.winner,a.seed,a.outer_reserve,a.inner_reserve)
    print(json.dumps(dict(outer=a.outer,first=a.first,winner=a.winner,seed=a.seed,reserves=[a.outer_reserve,a.inner_reserve],gates=True)),flush=True)
    if not a.hardware:return
    name=f'call-reserve-{a.outer}-k{a.first}-{a.winner}-s{a.seed}-r{a.outer_reserve}{a.inner_reserve}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):r['reserve_analysis']=dict(exact=(v['out'],v['table_after'])==p['expected'],
         caller_writers=[i for i,x in enumerate(v['table_after'][352:384]) if x!=E.SENT],
         masked_counter_values=sorted(set(v['table_after'][576:608])-{E.SENT}))
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('reserve_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('reserve_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
