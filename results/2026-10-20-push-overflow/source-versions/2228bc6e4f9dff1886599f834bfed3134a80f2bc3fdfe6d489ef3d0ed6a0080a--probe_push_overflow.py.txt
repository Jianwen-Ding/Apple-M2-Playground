#!/usr/bin/env python3
"""Bounded low-r0 increment boundaries, immediate execution, and pop0 sync.

Controls read initialized expected payloads under simple IF masks; they never
seed r0 or execute the tested push. Candidate drains are fully unrolled.
Default is simulator-only. No RET, jump, barrier or invalid operand is used.
"""
import argparse
import gzip
import hashlib
import json
import random
from pathlib import Path
import probe_masked_r0 as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-push-overflow'
BASE=128
PHASE_WORDS=2048
END=BASE+4*PHASE_WORDS
PRE=0xf6600001
DONE=0xf6600002


def table_for(maximum,n,rotate):
    ds=[0,1,2,3,14,15,16,30,31] if maximum==31 else [0,1,2,3,32766,32767,32768,32769,65531,65532,65533,65534,65535]
    rng=random.Random(6600+maximum)
    while len(ds)<32:ds.append(rng.randrange(maximum+1))
    if rotate:ds=ds[-1:]+ds[:-1]
    after=[(d+n)&65535 if d else 0 for d in ds]
    return ds+after+[max(d-1,0) for d in after]+[E.SENT]*(END+48-96)


def oracle(table,cached,control=False):
    orig=table[:32];after=table[32:64];states=[orig,after,after,table[64:96]]
    tab=table.copy();tab[96:128]=[PRE]*32
    for phase,ds in enumerate(states):
        active=[True]*32 if phase==0 and cached else [d==0 for d in ds]
        for bank in range(2):
            values=orig if bank else ds
            for source,value in enumerate(values):
                base=BASE+phase*PHASE_WORDS+bank*1024+source*32
                tab[base:base+32]=[value if m else E.SENT for m in active]
    tab[END:END+32]=[DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def construct(table,n,cached,control=False):
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    body=e('iadd r20, r1, 0')+B.load(10,20,True)
    for base,reg in ((32,11),(64,14)):
        body+=mov(12,base)+e('iadd r13, r20, r12')+B.load(reg,13,True)
    body+=e('wait 0')+mov(29,65535)+mov(12,96)+e('iadd r21, r20, r12')
    body+=mov(12,END)+e('iadd r22, r20, r12')+mov(28,PRE)+store(28,8,21)+e('wait 0')
    if not control:
        body+=e('mov r0l, r10l')
        if not cached:body+=e('pop_exec r0l, 0')
    sites=[]
    for phase,reg in enumerate((10,11,11,14)):
        if control:
            if phase:body+=e('pop_exec r0l, 1')
            if phase or not cached:body+=e(f'if_icmp r0l, ueq, r{reg}, 0, 1')
        elif phase==1:
            sites.append(P.drm.control_main()[1]+len(body))
            body+=e(f'if_fcmp r0l, eq, 0.0, 0.0, {n}',f'push_exec r0l, {n}' if n else 'update_exec r0l')
        elif phase==2:body+=e('pop_exec r0l, 0')
        elif phase==3:body+=e('pop_exec r0l, 1')
        for bank in range(2):
            source=10 if bank else reg if control else 0
            for j in range(32):
                body+=e(f'simd_shuffle r28, r{source}, {j}')+e('and r28, r28, r29')
                body+=mov(12,BASE+phase*PHASE_WORDS+bank*1024+j*32)+e('iadd r13, r20, r12')+store(28,8,13)+e('wait 0')
    drain=(max(table[:96])+2)//3+2
    body+=(e('pop_exec r0l, 1') if control else e('pop_exec r0l, 3')*drain)
    body+=mov(28,DONE)+store(28,8,22)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code);assert len(code)<1024*1024
    pc=0;bounds=[]
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        bounds.append(pc);pc+=info[1]
    assert pc==len(code) and all(at in bounds for at in sites)
    return code,sites,drain,bounds


def build(maximum,n,cached,rotate):
    assert maximum in (31,65535) and n in range(4) and rotate in (0,1)
    P.cov.install();table=table_for(maximum,n,rotate)
    code,sites,drain,bounds=construct(table,n,cached);control,_,_,_=construct(table,n,cached,True)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,cached,True),'independent payload control mismatch'
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table,cached),'actual increment/wrap/sync hypothesis mismatch'
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,expected=oracle(table,cached,True),data_dir=DATA,
        gate=dict(maximum=maximum,push_n=n,cached=cached,rotate=rotate,push_pc=sites[0],drain_pop3_count=drain,
                  boundaries=bounds,actual_measured_model_exact=True,payload_control_exact=True,
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--maximum',type=int,choices=(31,65535),default=31)
    ap.add_argument('--n',type=int,choices=range(4),default=1)
    ap.add_argument('--cached',action='store_true')
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.maximum,a.n,a.cached,a.rotate)
    print(json.dumps(dict(gates=True,maximum=a.maximum,push_n=a.n,cached=a.cached,rotate=a.rotate,bytes=len(p['code']))),flush=True)
    if not a.hardware:return
    name=f'push-overflow-m{a.maximum}-n{a.n}-'+('cached' if a.cached else 'synced')+f'-r{a.rotate}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        want=oracle(p['table'],a.cached)
        r['push_analysis']=dict(exact=(v['out'],v['table_after'])==want,
            different_words=[i for i,(x,y) in enumerate(zip(v['table_after'],want[1])) if x!=y],
            counter_values=[[[*sorted(set(v['table_after'][BASE+phase*PHASE_WORDS+j*32:BASE+phase*PHASE_WORDS+(j+1)*32])-{E.SENT})] for j in range(32)] for phase in range(4)],
            writers=[[i for i,x in enumerate(v['table_after'][BASE+phase*PHASE_WORDS:BASE+phase*PHASE_WORDS+32]) if x!=E.SENT] for phase in range(4)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(exact=r.get('push_analysis',{}).get('exact'),differences=r.get('push_analysis',{}).get('different_words',[])[:12],recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('push_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
