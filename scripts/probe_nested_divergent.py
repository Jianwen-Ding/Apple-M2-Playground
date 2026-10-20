#!/usr/bin/env python3
"""Two-level calls with a three-way divergent inner register call.

All physical lanes enter the outer function. Outer links are saved before the
inner call and restored only after two explicit pops. A no-call conditional
control independently writes the complete expected trace. Default is offline.
"""
import argparse
import gzip
import hashlib
import json
import random
from pathlib import Path
import probe_empty_stop as E
from run_drm_cpu_clock import load

P,CF=E.P,E.CF
DATA=E.ROOT/'results/2026-10-20-nested-divergent'
OUTER=1024
CALLEES={'A':2048,'B':2560,'C':3072}
PRE=0xe1100001
OUT_MARK=0xe1100002
CONT=0xe1100003
BAD=0xbad10001
INNER_MARK={'A':0xa1100011,'B':0xb2200011,'C':0xc3300011}


def targets(seed,winner):
    rng=random.Random(seed);names=list(CALLEES)
    choices=[rng.choice(names) for _ in range(32)]
    at=names.index(winner);choices[:3]=names[at:]+names[:at]
    site=P.drm.control_main()[1]
    return [0x2000+site+CALLEES[k] for k in choices]


def oracle(table,winner,outer_link,inner_link):
    tab=table.copy();site=P.drm.control_main()[1];target=0x2000+site+CALLEES[winner]
    same=[x==target for x in table[:32]]
    tab[32:64]=[PRE]*32
    tab[64:96]=[outer_link]*32
    tab[96:128]=[OUT_MARK]*32
    tab[128:160]=[inner_link if x else E.SENT for x in same]
    tab[160:192]=[INNER_MARK[winner] if x else E.SENT for x in same]
    for phase in (6,7):tab[phase*32:(phase+1)*32]=[E.SENT if x else 0 for x in same]
    tab[256:288]=[0]*32
    tab[288:320]=[inner_link]*32
    tab[320:352]=[outer_link]*32
    tab[352:384]=[CONT]*32
    tab[384:416]=[outer_link]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def helpers():
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    def write(plane,reg=28):
        return mov(12,plane*32)+e('iadd r13, r20, r12')+store(reg,8,13)+e('wait 0')
    def mark(plane,value):return mov(28,value)+write(plane)
    def counter(plane):return e('mov r28, r0l')+write(plane)
    return e,mov,write,mark,counter


def construct(outer_kind):
    P.cov.install();e,mov,write,mark,counter=helpers();site=P.drm.control_main()[1]
    setup=e('iadd r20, r1, 0')+load(30,20,True)+e('wait 0')+mark(1,PRE)+mov(31,0x2000+site+OUTER)
    outer_pc=site+len(setup)
    if outer_kind=='direct':
        delta=site+OUTER-outer_pc
        transfer=(0xc010|((delta&0xffffffff)<<16)).to_bytes(6,'little');outer_link=0x2000+outer_pc+6
    else:
        transfer=e('call r31')+e('wait 0')*2;outer_link=0x2000+outer_pc+2
    main=setup+transfer+e('pop_exec r0l, 1')+counter(13)+e('pop_exec r0l, 1')+mark(11,CONT)+write(12,1)+e('stop')
    assert len(main)<=OUTER and (OUTER-len(main))%2==0
    body=main+e('stop')*((OUTER-len(main))//2)
    outer=write(2,1)+mark(3,OUT_MARK)+e('mov r29, r1')
    inner_pc=site+OUTER+len(outer);inner_link=0x2000+inner_pc+2
    outer+=e('call r30')+e('wait 0')*2
    outer+=counter(6)+e('pop_exec r0l, 1')+counter(7)+e('pop_exec r0l, 1')+counter(8)
    outer+=write(9,1)+write(10,29)+e('mov r1, r29')+e('ret r1')+e('wait 0')*2
    outer+=e('pop_exec r0l, 1')*3+mark(13,BAD)+e('stop')
    body+=outer
    for name,offset in CALLEES.items():
        assert len(body)<=offset and (offset-len(body))%2==0
        body+=e('stop')*((offset-len(body))//2)
        body+=write(4,1)+mark(5,INNER_MARK[name])+e('ret r1')+e('wait 0')*2
        body+=e('pop_exec r0l, 1')*3+mark(13,BAD)+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code,allow=('call','ret'))
    boundaries=[];at=0
    while at<len(code):
        info=P.cov.ASMB.info(code[at:at+16]);assert info and info[1]>0
        boundaries.append(at);at+=info[1]
    assert at==len(code)
    assert all(x-0x2000 in boundaries for x in [outer_link,inner_link]+[0x2000+site+v for v in (OUTER,*CALLEES.values())])
    return code,outer_link,inner_link,outer_pc,inner_pc,boundaries


def control(winner,outer_link,inner_link):
    e,mov,write,mark,counter=helpers();target=0x2000+P.drm.control_main()[1]+CALLEES[winner]
    body=e('iadd r20, r1, 0')+load(30,20,True)+e('wait 0')+mark(1,PRE)
    body+=mov(1,outer_link)+write(2,1)+mark(3,OUT_MARK)+e('mov r29, r1')+mov(1,inner_link)+mov(31,target)
    body+=e('if_icmp r0l, ueq, r30, r31, 1')+write(4,1)+mark(5,INNER_MARK[winner])+e('pop_exec r0l, 1')
    body+=e('if_icmp r0l, nueq, r30, r31, 1')+mark(6,0)+mark(7,0)+e('pop_exec r0l, 1')
    body+=mark(8,0)+write(9,1)+write(10,29)+mov(1,outer_link)+mark(11,CONT)+write(12,1)+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code)
    return code


def build(outer_kind,winner,seed):
    assert outer_kind in ('direct','indirect') and winner in CALLEES
    code,ol,il,op,ip,bounds=construct(outer_kind)
    table=targets(seed,winner)+[E.SENT]*(13*32+16)
    ctrl=control(winner,ol,il);want=oracle(table,winner,ol,il)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==want,'independent no-call control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==want,'complete nested program failed'
        # Each potential winning callee is valid and has an exact complete trace.
        for name in CALLEES:
            t=table.copy();t[:32]=targets(seed,name)
            assert P.cov.simulate(code,32,32,64,0,t)==oracle(t,name,ol,il),name
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=want,data_dir=DATA,
        gate=dict(outer_kind=outer_kind,winner=winner,seed=seed,outer_link=ol,inner_link=il,
                  outer_pc=op,inner_pc=ip,boundaries=bounds,all_targets_in_program=True,
                  complete_actual_exact=True,no_call_control_exact=True,all_three_winners_exact=True,
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outer',choices=('direct','indirect'),default='direct')
    ap.add_argument('--winner',choices=tuple(CALLEES),default='A')
    ap.add_argument('--seed',type=int,default=17)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.outer,a.winner,a.seed)
    print(json.dumps(dict(outer=a.outer,winner=a.winner,seed=a.seed,gates=True)),flush=True)
    if not a.hardware:return
    name=f'nested-divergent-{a.outer}-{a.winner}-s{a.seed}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):r['nested_analysis']=dict(exact=(v['out'],v['table_after'])==p['expected'])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('nested_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('nested_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
