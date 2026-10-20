#!/usr/bin/env python3
"""Distinguish RET target selection from stale execution and stored counters.

All three per-lane destinations and the fallthrough have bounded drains.
Ordinary writes change only original issuers; independent IF/jump controls
never write r0 or execute RET. Default is simulator-only.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_masked_r0 as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-ret-stale-targets'
LANDINGS=(1024,1536,2048)
KINDS=('deep-first','zero-first','one-first','uniform-deep','uniform-zero','uniform-one')
MASKS=((0,'suffix'),(0,'scatter'),(5,'suffix'),(5,'scatter'),(31,'suffix'))
MARKS=(0xa5500001,0xb5500002,0xc5500003,0xfa550004)
SENT=0xcdcdcdcd


def table_for(first,shape,kind,rotate):
    mask=[int(i>=first and (shape=='suffix' or i==first or (i*13+7)%5<3)) for i in range(32)]
    active=[i for i,m in enumerate(mask) if m]
    depths=[(0,1,2,3,7,15,31)[(i*3+5)%7] for i in range(32)]
    if kind.startswith('uniform-'):depths=[{'uniform-deep':3,'uniform-zero':0,'uniform-one':1}[kind]]*32
    else:
        lead={'deep-first':(3,0,1),'zero-first':(0,1,3),'one-first':(1,0,3)}[kind]
        for lane,d in zip(active,lead):depths[lane]=d
    labels=[(i-first+rotate)%3 if mask[i] else (rotate+1)%3 for i in range(32)]
    site=P.drm.control_main()[1]
    targets=[0x2000+site+LANDINGS[label] for label in labels]
    return depths+targets+mask+[SENT]*(464-96)


def target_models(table):
    incoming=[d if m else 1 for d,m in zip(table[:32],table[64:96])]
    after_exec=[d==1 or d>=2 and bool(m) for d,m in zip(incoming,table[64:96])]
    def pick(mask):return next((table[32+i] for i,m in enumerate(mask) if m),None)
    return dict(issue=pick(table[64:96]),zero=pick([d==0 for d in incoming]),after=pick(after_exec))


def oracle(table,control=False,target=None):
    tab=table.copy();tab[96:128]=table[32:64];tab[128:160]=table[:32];tab[160:192]=table[64:96]
    active=[bool(m) for m in table[64:96]]
    counters=[0 if m else 1 for m in active] if control else [d if m else 1 for d,m in zip(table[:32],active)]
    if not control:
        active=[d==1 or d>=2 and m for d,m in zip(counters,active)]
        counters=[2 if d==0 else 0 if d==1 else d for d in counters]
    if target is None:target=target_models(table)['issue']
    label=(0x2000+P.drm.control_main()[1]+LANDINGS[0],0x2000+P.drm.control_main()[1]+LANDINGS[1],0x2000+P.drm.control_main()[1]+LANDINGS[2]).index(target)
    for phase in range(3):
        if phase:
            counters=[max(d-1,0) for d in counters];active=[d==0 for d in counters]
        tab[192+64*phase:224+64*phase]=[MARKS[label] if m else SENT for m in active]
        tab[224+64*phase:256+64*phase]=[d if m else SENT for d,m in zip(counters,active)]
    tab[384:416]=[MARKS[label]]*32;tab[416:448]=[0]*32
    return [SENT]*48+[0xa5a50000+i for i in range(16)],tab


def construct(table,control=False):
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store;site=P.drm.control_main()[1]
    def emit_store(reg,base):
        return mov(12,base)+e('iadd r13, r20, r12')+store(reg,8,13)+e('wait 0')
    setup=e('iadd r20, r1, 0')+B.load(10,20,True)
    for base,reg in ((32,30),(64,11)):
        setup+=mov(12,base)+e('iadd r13, r20, r12')+B.load(reg,13,True)
    setup+=e('wait 0')+mov(29,0xffff)
    for reg,base in ((30,96),(10,128),(11,160)):setup+=emit_store(reg,base)
    setup+=e('if_icmp r0l, ueq, r11, 1, 1')
    if not control:setup+=e('mov r0l, r10l')
    transfer_pc=site+len(setup)
    if control:
        delta=target_models(table)['issue']-0x2000-transfer_pc
        setup+=e(f'jmp_exec_any pc+{delta}',f'jmp_exec_any pc+{delta}')
    else:setup+=e('ret r30')+e('wait 0')*2
    def landing(label):
        body=b''
        for phase in range(3):
            if phase:body+=e('pop_exec r0l, 1')
            body+=mov(28,MARKS[label])+emit_store(28,192+64*phase)
            body+=e('and r28, r0, r29')+emit_store(28,224+64*phase)
        body+=e('pop_exec r0l, 3')*12
        body+=mov(28,MARKS[label])+emit_store(28,384)
        body+=e('and r28, r0, r29')+emit_store(28,416)+e('stop')
        return body
    setup+=landing(3)
    for label,offset in enumerate(LANDINGS):
        assert len(setup)<=offset and (offset-len(setup))%2==0
        setup+=e('stop')*((offset-len(setup))//2)+landing(label)
    code=P.drm.build_main(setup);P.cov.gate(code,allow=() if control else ('ret',))
    boundaries=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code) and all(t-0x2000 in boundaries for t in table[32:64])
    assert transfer_pc in boundaries and len(code)<4096
    return code,transfer_pc,boundaries


def build(first,shape,kind,rotate):
    assert (first,shape) in MASKS and kind in KINDS and rotate in (0,1,2)
    P.cov.install();table=table_for(first,shape,kind,rotate)
    code,pc,bounds=construct(table);control,_,_=construct(table,True)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,True),'independent IF/jump control mismatch'
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table),'actual stale-target complete-program mismatch'
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,expected=oracle(table,True),data_dir=DATA,
        gate=dict(first=first,shape=shape,kind=kind,rotate=rotate,ret_pc=pc,boundaries=bounds,
                  target_models=target_models(table),no_ret_control_exact=True,actual_measured_model_exact=True,
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,choices=(0,5,31),default=0)
    ap.add_argument('--shape',choices=('suffix','scatter'),default='suffix')
    ap.add_argument('--kind',choices=KINDS,default='deep-first')
    ap.add_argument('--rotate',type=int,choices=(0,1,2),default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.first,a.shape,a.kind,a.rotate)
    print(json.dumps(dict(gates=True,first=a.first,shape=a.shape,kind=a.kind,rotate=a.rotate,models=p['gate']['target_models'])),flush=True)
    if not a.hardware:return
    name=f'ret-stale-target-k{a.first}-{a.shape}-{a.kind}-r{a.rotate}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];models=p['gate']['target_models']
        r['target_analysis']=dict(exact=got==oracle(p['table']),
            model_matches={key:value is not None and got==oracle(p['table'],target=value) for key,value in models.items()},
            final_values=sorted(set(v['table_after'][384:416])),
            different_words=[i for i,(x,y) in enumerate(zip(v['table_after'],oracle(p['table'])[1])) if x!=y])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('target_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('target_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
