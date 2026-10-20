#!/usr/bin/env python3
"""Balanced call-mask reserves through 3/4/8 calls, with divergent leaf targets.

All saved-link registers are initialized to a valid main continuation before
masking, then overwritten only by callers that actually enter each function.
Every entry/continuation has exact counter/link/participation checkpoints.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_call_mask_reserve as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-deep-call-reserve'
KINDS=('direct','indirect','alternating','reverse')
PRE=0xe3300001
CALLER=0xe3300002
DONE=0xe3300003
BAD=0xbad30001


def planes(depth):return 3+8*depth,4+8*depth,5+8*depth

def mark_entry(j):return 0xe3301000+j

def mark_pop1(j):return 0xe3302000+j

def mark_pop2(j):return 0xe3303000+j


def target_offsets(depth):return {'A':depth*1024,'B':depth*1024+512,'C':depth*1024+1024}


def table_for(depth,first,winner,seed):
    old=B.B.table_for(first,winner,seed)
    base=P.drm.control_main()[1]+0x2000
    old_offsets={base+v:k for k,v in B.B.N.CALLEES.items()}
    targets=[base+target_offsets(depth)[old_offsets[x]] for x in old[:32]]
    _,_,final=planes(depth)
    return targets+old[480:512]+[E.SENT]*((final-1)*32+16)


def oracle(table,depth,winner,links):
    tab=table.copy();target=0x2000+P.drm.control_main()[1]+target_offsets(depth)[winner]
    caller,full,final=planes(depth);tab[64:96]=[PRE]*32
    for lane,operand in enumerate(table[:32]):
        admitted=bool(table[32+lane]);leaf=admitted and operand==target
        if admitted:
            tab[caller*32+lane]=CALLER
            for j in range(depth):
                base=3+8*j
                if j<depth-1 or leaf:
                    tab[base*32+lane]=links[j]
                    tab[(base+1)*32+lane]=1+2*(j+1)
                    tab[(base+2)*32+lane]=mark_entry(j) if j<depth-1 else B.B.N.INNER_MARK[winner]
                if j==depth-1 and not leaf:
                    tab[(base+3)*32+lane]=1+2*depth
                    tab[(base+4)*32+lane]=mark_pop1(j)
                tab[(base+5)*32+lane]=mark_pop2(j)
                tab[(base+6)*32+lane]=links[j]
                tab[(base+7)*32+lane]=1+2*j
        tab[full*32+lane]=DONE
        tab[final*32+lane]=links[0] if admitted else lane
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def construct(depth,pattern,saved_seed):
    P.cov.install();e,mov,write,mark,_=B.B.N.helpers();site=P.drm.control_main()[1]
    push=e('if_fcmp r0l, eq, 0.0, 0.0, 2','push_exec r0l, 2');stop=e('stop')
    links=[None]*depth;call_pcs=[None]*depth;call_kinds=[None]*depth
    caller,full,final=planes(depth)
    def counter(plane):return e('simd_shuffle r28, r0, 0')+e('and r28, r28, r27')+write(plane)
    def entry(j,leaf=None):
        base=3+8*j
        return write(base,1)+counter(base+1)+mark(base+2,mark_entry(j) if leaf is None else B.B.N.INNER_MARK[leaf])
    def post(j):
        base=3+8*j
        return counter(base+3)+e('pop_exec r0l, 1')+mark(base+4,mark_pop1(j))+e('pop_exec r0l, 1')+mark(base+5,mark_pop2(j))+write(base+6,1)+counter(base+7)
    def kind(j):
        if j==depth-1:return 'leaf-indirect'
        if pattern in ('direct','indirect'):return pattern
        direct=(j%2==0)==(pattern=='alternating')
        return 'direct' if direct else 'indirect'
    def call(j,pc):
        k=kind(j);call_kinds[j]=k
        if k=='direct':
            at=pc+len(push);delta=site+(j+1)*1024-at
            body=push+(0xc010|((delta&0xffffffff)<<16)).to_bytes(6,'little');size=6
        elif k=='indirect':
            setup=mov(31,0x2000+site+(j+1)*1024)+push;at=pc+len(setup)
            body=setup+e('call r31')+e('wait 0')*2;size=2
        else:
            at=pc+len(push);body=push+e('call r30')+e('wait 0')*2;size=2
        links[j]=0x2000+at+size;call_pcs[j]=at
        return body
    def fallback():return e('pop_exec r0l, 1')*(2*depth+4)+mark(full,BAD)+stop
    main=e('iadd r20, r1, 0')+B.B.N.load(30,20,True)+mov(12,32)+e('iadd r13, r20, r12')+B.B.N.load(10,13,True)+e('wait 0')
    main+=mov(27,0xffff)+mov(31,0x2000+site+1024)+mark(2,PRE)
    for j in range(depth-1):main+=mov(2+j,saved_seed)
    main+=e('if_icmp r0l, ueq, r10, 1, 1')
    main+=call(0,site+len(main))+post(0)+mark(caller,CALLER)+e('pop_exec r0l, 1')+mark(full,DONE)+write(final,1)
    main+=e('pop_exec r0l, 1')*(2*depth+4)+stop
    body=main
    for j in range(depth-1):
        offset=(j+1)*1024
        assert len(body)<=offset and (offset-len(body))%2==0
        body+=stop*((offset-len(body))//2)
        function=e(f'mov r{2+j}, r1')+entry(j)
        function+=call(j+1,site+offset+len(function))+post(j+1)+e(f'mov r1, r{2+j}')+e('ret r1')+e('wait 0')*2+fallback()
        body+=function
    for name,offset in target_offsets(depth).items():
        assert len(body)<=offset and (offset-len(body))%2==0
        body+=stop*((offset-len(body))//2)+entry(depth-1,name)+e('ret r1')+e('wait 0')*2+fallback()
    code=P.drm.build_main(body);P.cov.gate(code,allow=('call','ret'))
    boundaries=[];at=0
    while at<len(code):
        info=P.cov.ASMB.info(code[at:at+16]);assert info and info[1]>0
        boundaries.append(at);at+=info[1]
    assert at==len(code)
    destinations=links+[0x2000+site+j*1024 for j in range(1,depth)]+[0x2000+site+v for v in target_offsets(depth).values()]
    assert all(x-0x2000 in boundaries for x in destinations)
    return code,links,call_pcs,call_kinds,boundaries


def control(table,depth,winner,links):
    e,mov,write,mark,_=B.B.N.helpers();caller,full,final=planes(depth)
    target=0x2000+P.drm.control_main()[1]+target_offsets(depth)[winner]
    body=e('iadd r20, r1, 0')+B.B.N.load(30,20,True)+mov(12,32)+e('iadd r13, r20, r12')+B.B.N.load(10,13,True)+e('wait 0')+mark(2,PRE)+mov(31,target)
    body+=e('icmpsel ueq, r11, r30, r31, 1, 0')+e('and r11, r11, r10')+e('xor r2, r10, r11')
    for j in range(depth):
        base=3+8*j
        condition='if_icmp r0l, ueq, r10, 1, 1' if j<depth-1 else 'if_icmp r0l, ueq, r11, 1, 1'
        body+=e(condition)+mark(base,links[j])+mark(base+1,1+2*(j+1))+mark(base+2,mark_entry(j) if j<depth-1 else B.B.N.INNER_MARK[winner])+e('pop_exec r0l, 1')
        if j==depth-1:body+=e('if_icmp r0l, ueq, r2, 1, 1')+mark(base+3,1+2*depth)+mark(base+4,mark_pop1(j))+e('pop_exec r0l, 1')
        body+=e('if_icmp r0l, ueq, r10, 1, 1')+mark(base+5,mark_pop2(j))+mark(base+6,links[j])+mark(base+7,1+2*j)+e('pop_exec r0l, 1')
    body+=e('if_icmp r0l, ueq, r10, 1, 1')+mark(caller,CALLER)+mov(1,links[0])+e('pop_exec r0l, 1')+mark(full,DONE)+write(final,1)+e('stop')
    result=P.drm.build_main(body);P.cov.gate(result)
    return result


def build(depth,pattern,first,winner,seed):
    assert depth in (3,4,8) and pattern in KINDS and first in (1,5,16,24)
    _,links,_,_,_=construct(depth,pattern,0)
    code,actual_links,pcs,kinds,bounds=construct(depth,pattern,links[0]);assert links==actual_links
    table=table_for(depth,first,winner,seed);want=oracle(table,depth,winner,links);ctrl=control(table,depth,winner,links)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==want,'known no-call control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==want,'complete deep reserve hypothesis failed'
        for name in target_offsets(depth):
            t=table_for(depth,first,name,seed)
            assert P.cov.simulate(code,32,32,64,0,t)==oracle(t,depth,name,links),name
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=want,data_dir=DATA,
        gate=dict(depth=depth,pattern=pattern,first=first,winner=winner,seed=seed,links=links,call_pcs=pcs,call_kinds=kinds,
                  boundaries=bounds,all_saved_links_initialized=True,complete_actual_exact=True,no_call_control_exact=True,all_three_winners_exact=True,
                  base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--depth',type=int,choices=(3,4,8),default=3)
    ap.add_argument('--pattern',choices=KINDS,default='direct')
    ap.add_argument('--first',type=int,choices=(1,5,16,24),default=1)
    ap.add_argument('--winner',choices=('A','B','C'),default='A')
    ap.add_argument('--seed',type=int,default=17)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.depth,a.pattern,a.first,a.winner,a.seed)
    print(json.dumps(dict(depth=a.depth,pattern=a.pattern,first=a.first,winner=a.winner,seed=a.seed,gates=True)),flush=True)
    if not a.hardware:return
    name=f'deep-reserve-d{a.depth}-{a.pattern}-k{a.first}-{a.winner}-s{a.seed}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):r['deep_analysis']=dict(exact=(v['out'],v['table_after'])==p['expected'],
        entry_counter_values=[sorted(set(v['table_after'][(4+8*j)*32:(5+8*j)*32])-{E.SENT}) for j in range(a.depth)],
        restored_counter_values=[sorted(set(v['table_after'][(10+8*j)*32:(11+8*j)*32])-{E.SENT}) for j in range(a.depth)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('deep_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('deep_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
