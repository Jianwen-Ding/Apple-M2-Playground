#!/usr/bin/env python3
"""Nested divergent calls under a partial original outer mask.

Seed valid saved outer links in every physical lane before divergence. This
makes later reactivation bounded and observable without consuming an
uninitialized transfer operand. All functions/inner links stay fixed.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_nested_divergent as N

P,E,CF=N.P,N.E,N.CF
DATA=E.ROOT/'results/2026-10-20-nested-partial-outer'
MASK_PLANE=15


def table_for(first,winner,seed):
    target=N.targets(seed,winner);site=P.drm.control_main()[1]
    names=list(N.CALLEES);at=names.index(winner)
    for lane,name in zip(range(first,first+3),names[at:]+names[:at]):target[lane]=0x2000+site+N.CALLEES[name]
    return target+[E.SENT]*(14*32)+[int(i>=first) for i in range(32)]+[E.SENT]*16


def oracle(table,winner,ol,il,pops):
    result=table.copy();target=0x2000+P.drm.control_main()[1]+N.CALLEES[winner]
    for lane,operand in enumerate(table[:32]):
        outer=bool(table[480+lane]);inner=outer and operand==target
        values={1:N.PRE,11:N.CONT,12:ol if pops==2 or not inner else il}
        if outer:values.update({2:ol,3:N.OUT_MARK})
        if inner:values.update({4:il,5:N.INNER_MARK[winner]})
        if not inner:values.update({6:0,7:0})
        if pops==2 or not inner:values.update({8:0,9:il if outer else lane,10:ol})
        if pops==1 and inner:values.update({13:0,14:0})
        for plane,value in values.items():result[32*plane+lane]=value
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],result


def construct(outer,pops):
    code,old_ol,il,old_op,ip,_=N.construct(outer);e,mov,write,mark,counter=N.helpers()
    pop=e('pop_exec r0l, 1');wait=e('wait 0')*(len(pop)//2)
    sequence=counter(6)+pop+counter(7)+pop+counter(8)
    replacement=counter(6)+(pop if pops else wait)+counter(7)+(pop if pops==2 else wait)+counter(8)
    assert len(sequence)==len(replacement) and code.count(sequence)==1
    code=code.replace(sequence,replacement)
    def extra(saved_link):
        return mov(29,saved_link)+mov(12,MASK_PLANE*32)+e('iadd r13, r20, r12')+N.load(10,13,True)+e('wait 0')+e('if_icmp r0l, ueq, r10, 1, 1')
    added=extra(old_ol);op=old_op+len(added);ol=old_ol+len(added)
    added=extra(ol);assert op==old_op+len(added)
    end=P.drm.control_main()[1]+N.OUTER;checkpoint=counter(14)
    trim=len(added)+len(checkpoint);assert code[end-trim:end]==e('stop')*(trim//2)
    transfer=code[old_op:old_op+6]
    if outer=='direct':transfer=(0xc010|(((end-op)&0xffffffff)<<16)).to_bytes(6,'little')
    code=code[:old_op]+added+transfer+checkpoint+code[old_op+6:end-trim]+code[end:]
    P.cov.gate(code,allow=('call','ret'))
    boundaries=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code) and all(x-0x2000 in boundaries for x in (ol,il,*N.targets(17,'A')))
    return code,ol,il,op,ip,boundaries


def control(winner,ol,il,pops):
    e,mov,write,mark,counter=N.helpers();target=0x2000+P.drm.control_main()[1]+N.CALLEES[winner]
    body=e('iadd r20, r1, 0')+N.load(30,20,True)+mov(12,MASK_PLANE*32)+e('iadd r13, r20, r12')+N.load(10,13,True)+e('wait 0')
    body+=mark(1,N.PRE)+mov(29,ol)+mov(31,target)
    body+=e('if_icmp r0l, ueq, r10, 1, 1')+mov(1,ol)+write(2,1)+mark(3,N.OUT_MARK)+mov(1,il)+e('pop_exec r0l, 1')
    body+=e('icmpsel ueq, r11, r30, r31, 1, 0')+e('and r11, r11, r10')
    body+=e('if_icmp r0l, ueq, r11, 1, 1')+write(4,1)+mark(5,N.INNER_MARK[winner])+e('pop_exec r0l, 1')
    body+=e('if_icmp r0l, ueq, r11, 0, 1')+mark(6,0)+mark(7,0)
    if pops!=2:body+=mark(8,0)+write(9,1)+write(10,29)+mov(1,ol)
    body+=e('pop_exec r0l, 1')
    if pops==2:body+=mark(8,0)+write(9,1)+write(10,29)+mov(1,ol)
    if pops==1:body+=e('if_icmp r0l, ueq, r11, 1, 1')+mark(14,0)+mark(13,0)+e('pop_exec r0l, 1')
    body+=mark(11,N.CONT)+write(12,1)+e('stop')
    result=P.drm.build_main(body);P.cov.gate(result)
    return result


def build(outer,first,winner,seed,pops):
    assert first in (1,5,16,24) and pops in (0,1,2)
    code,ol,il,op,ip,bounds=construct(outer,pops);table=table_for(first,winner,seed)
    ctrl=control(winner,ol,il,pops);want=oracle(table,winner,ol,il,pops)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==want,'no-call scalar control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==want,'complete partial-outer hypothesis failed'
        for name in N.CALLEES:
            t=table_for(first,name,seed)
            assert P.cov.simulate(code,32,32,64,0,t)==oracle(t,name,ol,il,pops),name
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=want,data_dir=DATA,
        gate=dict(outer_kind=outer,first=first,winner=winner,seed=seed,inner_pops=pops,outer_link=ol,inner_link=il,
                  outer_pc=op,inner_pc=ip,boundaries=bounds,all_targets_in_program=True,all_saved_links_initialized=True,
                  complete_actual_exact=True,no_call_control_exact=True,all_three_winners_exact=True,
                  base_builder_sha256=hashlib.sha256(Path(N.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outer',choices=('direct','indirect'),default='direct')
    ap.add_argument('--first',type=int,choices=(1,5,16,24),default=1)
    ap.add_argument('--winner',choices=tuple(N.CALLEES),default='A')
    ap.add_argument('--seed',type=int,default=17)
    ap.add_argument('--pops',type=int,choices=(0,1,2),default=2)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.outer,a.first,a.winner,a.seed,a.pops)
    print(json.dumps(dict(outer=a.outer,first=a.first,winner=a.winner,seed=a.seed,pops=a.pops,gates=True)),flush=True)
    if not a.hardware:return
    name=f'nested-partial-{a.outer}-k{a.first}-{a.winner}-s{a.seed}-p{a.pops}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):r['partial_analysis']=dict(exact=(v['out'],v['table_after'])==p['expected'])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('partial_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('partial_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
