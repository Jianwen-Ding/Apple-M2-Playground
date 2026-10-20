#!/usr/bin/env python3
"""Return from an outer function before inner participants reconverge.

All saved outer links are initialized by a full-group outer call. Remove one
or both inner pops without moving any function/link address; add a direct
outer-landing pre-pop checkpoint. All targets remain decoded in-program.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_nested_divergent as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-nested-early-return'


def oracle(table,winner,ol,il,pops):
    tab=table.copy();target=0x2000+P.drm.control_main()[1]+B.CALLEES[winner]
    for lane,t in enumerate(table[:32]):
        match=t==target
        values={1:B.PRE,2:ol,3:B.OUT_MARK,11:B.CONT,12:il if match else ol}
        if match:
            values.update({4:il,5:B.INNER_MARK[winner]})
            if pops==1:values.update({13:0,14:0})
        else:values.update({6:0,7:0,8:0,9:il,10:ol})
        for plane,value in values.items():tab[plane*32+lane]=value
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def construct(outer,pops):
    code,ol,il,op,ip,_=B.construct(outer);e,mov,write,mark,counter=B.helpers()
    sequence=counter(6)+e('pop_exec r0l, 1')+counter(7)+e('pop_exec r0l, 1')+counter(8)
    replacement=counter(6)
    pop=e('pop_exec r0l, 1');waits=e('wait 0')*(len(pop)//2)
    assert len(waits)==len(pop)
    replacement+=(pop if pops else waits)+counter(7)+waits+counter(8)
    assert len(sequence)==len(replacement) and code.count(sequence)==1
    code=code.replace(sequence,replacement)
    # Insert within the main caller, removing only STOP padding so the outer
    # function and every indirect target/link retains its original address.
    at=op+6;end=P.drm.control_main()[1]+B.OUTER;extra=counter(14)
    assert code[end-len(extra):end]==e('stop')*(len(extra)//2)
    code=code[:at]+extra+code[at:end-len(extra)]+code[end:]
    P.cov.gate(code,allow=('call','ret'))
    boundaries=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code) and all(v-0x2000 in boundaries for v in (ol,il,*B.targets(17,'A')))
    return code,ol,il,op,ip,boundaries


def control(winner,ol,il,pops):
    e,mov,write,mark,counter=B.helpers();target=0x2000+P.drm.control_main()[1]+B.CALLEES[winner]
    body=e('iadd r20, r1, 0')+B.load(30,20,True)+e('wait 0')+mark(1,B.PRE)
    body+=mov(1,ol)+write(2,1)+mark(3,B.OUT_MARK)+e('mov r29, r1')+mov(1,il)+mov(31,target)
    body+=e('if_icmp r0l, ueq, r30, r31, 1')+write(4,1)+mark(5,B.INNER_MARK[winner])+e('pop_exec r0l, 1')
    body+=e('if_icmp r0l, nueq, r30, r31, 1')+mark(6,0)+mark(7,0)+mark(8,0)+write(9,1)+write(10,29)+e('pop_exec r0l, 1')
    if pops:
        body+=e('if_icmp r0l, ueq, r30, r31, 1')+mark(14,0)+mark(13,0)+e('pop_exec r0l, 1')
    body+=mov(2,il)+mov(3,ol)+e('icmpsel ueq, r1, r30, r31, r2, r3')+mark(11,B.CONT)+write(12,1)+e('stop')
    result=P.drm.build_main(body);P.cov.gate(result)
    return result


def build(outer,winner,seed,pops):
    assert pops in (0,1)
    code,ol,il,op,ip,bounds=construct(outer,pops)
    table=B.targets(seed,winner)+[E.SENT]*(14*32+16)
    ctrl=control(winner,ol,il,pops);want=oracle(table,winner,ol,il,pops)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==want,'no-call scalar control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==want,'complete early-return hypothesis failed'
        for name in B.CALLEES:
            t=table.copy();t[:32]=B.targets(seed,name)
            assert P.cov.simulate(code,32,32,64,0,t)==oracle(t,name,ol,il,pops),name
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=want,data_dir=DATA,
        gate=dict(outer_kind=outer,winner=winner,seed=seed,inner_pops=pops,outer_link=ol,inner_link=il,
                  outer_pc=op,inner_pc=ip,boundaries=bounds,all_targets_in_program=True,
                  complete_actual_exact=True,no_call_control_exact=True,all_three_winners_exact=True,
                  base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outer',choices=('direct','indirect'),default='direct')
    ap.add_argument('--winner',choices=tuple(B.CALLEES),default='A')
    ap.add_argument('--seed',type=int,default=17)
    ap.add_argument('--pops',type=int,choices=(0,1),default=1)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.outer,a.winner,a.seed,a.pops)
    print(json.dumps(dict(outer=a.outer,winner=a.winner,seed=a.seed,pops=a.pops,gates=True)),flush=True)
    if not a.hardware:return
    name=f'nested-early-{a.outer}-{a.winner}-s{a.seed}-p{a.pops}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):r['early_analysis']=dict(exact=(v['out'],v['table_after'])==p['expected'])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('early_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('early_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
