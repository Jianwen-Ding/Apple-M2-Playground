#!/usr/bin/env python3
"""Three valid call/return targets under scattered masks, with exact model gates.

One full SIMD group, no loop/barrier/returning call. Both uniform substitutions
and direct jumps validate all three landing paths, then the exact original
program must match the independent host oracle before hardware submission.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random

import probe_empty_stop as E
from run_drm_cpu_clock import load

P,CF=E.P,E.CF
ROOT=E.ROOT
DATA=ROOT/'results/2026-10-20-three-targets'
OFFSETS={'A':1024,'B':1536,'C':2048}
MARKS={'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002),'C':(0xc3300001,0xc3300002)}
INITIAL=0xf1f10000
PRE=0xfeed0001
FALL=0xfa110001


def table_for(first,winner,seed):
    rng=random.Random(seed*101+first)
    names=list(OFFSETS);wi=names.index(winner)
    selected=[rng.choice(names) for _ in range(32)]
    mask=rng.getrandbits(32)&(0xffffffff^((1<<first)-1))
    mask|=(1<<first)|(1<<(first+2))|(1<<31)
    mask&=~(1<<(first+1))
    selected[first]=winner
    selected[first+2]=names[(wi+1)%3]
    selected[31]=names[(wi+2)%3]
    if first:selected[0]=names[(wi+1)%3]
    site=P.drm.control_main()[1]
    return ([0x2000+site+OFFSETS[name] for name in selected]
            +[(mask>>i)&1 for i in range(32)]+[E.SENT]*(6*32+16))


def oracle(kind,table,chosen,link,mode='actual'):
    tab=table.copy();tab[64:96]=[PRE]*32
    active=[bool(table[32+i]) for i in range(32)]
    address=0x2000+P.drm.control_main()[1]+OFFSETS[chosen]
    matching=[active[i] and table[i]==address for i in range(32)]
    if kind=='call':
        tab[96:128]=[MARKS[chosen][0] if matching[i] else E.SENT for i in range(32)]
        tab[128:160]=[link if matching[i] else E.SENT for i in range(32)]
        tab[160:192]=[MARKS[chosen][1]]*32
        writers=[True]*32 if mode=='jump' else matching if mode=='uniform' else active
        tab[224:256]=[link if writers[i] else INITIAL for i in range(32)]
    else:
        tab[96:128]=[MARKS[chosen][0] if mode=='jump' or not active[i] else E.SENT for i in range(32)]
        tab[128:160]=[MARKS[chosen][1]]*32
        tab[224:256]=[INITIAL]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def build(kind,first,winner,seed):
    if kind not in ('call','ret') or first not in (0,1,5,8,16,24) or winner not in OFFSETS:
        raise ValueError((kind,first,winner))
    P.cov.install()
    e,mov,st=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    site=P.drm.control_main()[1]
    setup=e('iadd r20, r1, 0')
    for slot,reg in zip(range(2,8),range(21,27)):
        setup+=mov(27,slot*32)+e(f'iadd r{reg}, r20, r27')
    setup+=load(30,20,True)+mov(27,32)+e('iadd r27, r20, r27')+load(10,27,True)+e('wait 0')
    setup+=mov(28,PRE)+st(28,8,21)+e('wait 0')
    initial_pc=site+len(setup);setup+=mov(1,INITIAL)
    uniform_pc=site+len(setup);setup+=mov(31,0x2000+site+OFFSETS['A'])
    setup+=e('icmpsel ueq, r29, r30, r31, r10, 0')
    mask_pc=site+len(setup);setup+=e('if_icmp r0l, ugt, r10, 0, 1')
    transfer_pc=site+len(setup);link=0x2000+transfer_pc+2
    body=setup+e(f'{kind} r30')+e('wait 0')*2
    body+=e('pop_exec r0l, 2')+mov(28,FALL)+st(28,8,25)+e('mov r28, r1')+st(28,8,26)+e('wait 0')+e('stop')
    for name,offset in OFFSETS.items():
        assert len(body)<=offset and (offset-len(body))%2==0
        body+=e('stop')*((offset-len(body))//2)
        if kind=='call':
            body+=mov(28,MARKS[name][0])+st(28,8,22)+st(1,8,23)+e('wait 0')
            body+=e('pop_exec r0l, 1')+mov(28,MARKS[name][1])+st(28,8,24)
        else:
            body+=e('pop_exec r0l, 1')+mov(28,MARKS[name][0])+st(28,8,22)+e('wait 0')
            body+=e('pop_exec r0l, 1')+mov(28,MARKS[name][1])+st(28,8,23)
        body+=e('mov r28, r1')+st(28,8,26)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);table=table_for(first,winner,seed)
    assert {table[i] for i in range(32) if table[32+i]}=={0x2000+site+offset for offset in OFFSETS.values()}
    surrogates={};control=None
    for name,offset in OFFSETS.items():
        uniform=code[:uniform_pc]+mov(31,0x2000+site+offset)+code[uniform_pc+6:]
        if kind=='call':
            old=e('if_icmp r0l, ugt, r10, 0, 1');new=e('if_icmp r0l, ugt, r29, 0, 1')
            assert len(old)==len(new)
            uniform=uniform[:mask_pc]+new+uniform[mask_pc+len(old):]
        uniform=uniform[:transfer_pc]+e(f'{kind} r31')+uniform[transfer_pc+2:]
        delta=site+offset-transfer_pc
        jump=uniform[:transfer_pc]+e(f'jmp_exec_any pc+{delta}',f'jmp_exec_any pc+{delta}')+uniform[transfer_pc+6:]
        if kind=='call':jump=jump[:initial_pc]+mov(1,link)+jump[initial_pc+6:]
        with E.measured_model():
            assert P.cov.simulate(uniform,32,32,64,0,table)==oracle(kind,table,name,link,'uniform')
            assert P.cov.simulate(jump,32,32,64,0,table)==oracle(kind,table,name,link,'jump')
        surrogates[name]=dict(uniform_code=uniform.hex(),jump_code=jump.hex(),uniform_exact=True,jump_exact=True)
        if name=='A':control=jump
    with E.measured_model():
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(kind,table,winner,link), 'actual three-target gate failed'
    P.cov.gate(code,allow=(kind,));P.cov.gate(control)
    decoded=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        decoded.append([pc,info[0],info[1]]);pc+=info[1]
    assert pc==len(code) and [transfer_pc,kind,2] in decoded
    assert all(any(row[0]==site+offset for row in decoded) for offset in OFFSETS.values())
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,data_dir=DATA,
                expected=oracle(kind,table,'A',link,'jump'),
                gate=dict(kind=kind,first=first,winner=winner,seed=seed,transfer_pc=transfer_pc,link=link,
                          targets={name:0x2000+site+offset for name,offset in OFFSETS.items()},decoded=decoded,
                          all_three_targets_active=True,actual_model_exact=True,surrogates=surrogates,
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kind',choices=('call','ret'),required=True)
    ap.add_argument('--first',type=int,default=1)
    ap.add_argument('--winner',choices=tuple(OFFSETS),default='C')
    ap.add_argument('--seed',type=int,default=103)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.kind,a.first,a.winner,a.seed)
    print(json.dumps({'kind':a.kind,'first':a.first,'winner':a.winner,'three_target_gates':True}),flush=True)
    if not a.hardware:return
    name=f'targets3-{a.kind}-k{a.first}-{a.winner}-s{a.seed}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        r['three_target_analysis']=dict(exact=(v.get('out'),v.get('table_after'))==oracle(a.kind,p['table'],a.winner,p['gate']['link']))
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('three_target_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('three_target_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
