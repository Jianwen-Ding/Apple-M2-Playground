#!/usr/bin/env python3
"""Seed wider low-r0 counters, synchronize, and directly gather transfer/pop state.

Controls never seed wide counters: they read initialized payloads under simple
IF masks. Candidate drains are fully unrolled and bounded; all transfer/fallback
targets are decoded in-program. Stage hardware only after lower widths recover.
"""
import argparse
import gzip
import hashlib
import json
import random
from pathlib import Path
import probe_masked_r0 as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-wide-r0'
STAGES={63:(31,32,33,62,63),255:(63,64,65,126,127,128,129,254,255),
        511:(255,256,257,510,511),1023:(511,512,513,1022,1023),
        4095:(1023,1024,1025,2047,2048,2049,4094,4095),
        16383:(4095,4096,4097,8191,8192,8193,16382,16383),
        32767:(16383,16384,16385,32766,32767),65534:(32767,32768,32769,65533,65534),65535:(65534,65535)}
LANDING=8192
BASE=96
PHASE_WORDS=2048
END=BASE+3*PHASE_WORDS
FALL_SLOT=END+32
PRE=0xf4400001
DONE=0xf4400002
FALL=0xfa440001


def table_for(maximum,rotate):
    ds=[0,1,2,3]+list(STAGES[maximum]);rng=random.Random(3100+maximum)
    while len(ds)<32:ds.append(rng.randrange(maximum+1))
    if rotate:ds=ds[-rotate:]+ds[:-rotate]
    mapped=[2 if d==0 else 0 if d==1 else d for d in ds]
    return ds+mapped+[E.SENT]*(FALL_SLOT+32+16-64)


def oracle(table,mode,control=False):
    original=table[:32];state=table[32:64] if mode=='ret' else original
    snapshots=[original,state,[max(d-1,0) for d in state]]
    result=table.copy();result[64:96]=[PRE]*32
    for phase,ds in enumerate(snapshots):
        if control:
            ds=original if phase<2 else [max(d-1,0) for d in original]
        for lane,d in enumerate(ds):
            if d:continue
            for bank in range(2):
                sources=original if bank or control else ds
                for j,value in enumerate(sources):result[BASE+phase*PHASE_WORDS+bank*1024+j*32+lane]=value
    result[END:END+32]=[DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],result


def construct(table,mode,control=False):
    P.cov.install();e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store;site=P.drm.control_main()[1]
    maximum=max(table[:32]);drain=(maximum+2)//3+2
    body=e('iadd r20, r1, 0')
    for base,reg in ((64,21),(END,22),(FALL_SLOT,23)):
        body+=mov(12,base)+e(f'iadd r{reg}, r20, r12')
    body+=B.load(10,20,True)+e('wait 0')+mov(29,0xffff)+mov(30,0x2000+site+LANDING)+mov(28,PRE)+store(28,8,21)+e('wait 0')
    if control:body+=e('if_icmp r0l, ueq, r10, 0, 1')
    else:body+=e('mov r0l, r10l')+e('pop_exec r0l, 0')
    def gather(phase):
        g=b''
        for bank in range(2):
            source=10 if bank or control else 0
            for j in range(32):
                g+=e(f'simd_shuffle r28, r{source}, {j}')+e('and r28, r28, r29')
                g+=mov(12,BASE+phase*PHASE_WORDS+bank*1024+j*32)+e('iadd r13, r20, r12')+store(28,8,13)+e('wait 0')
        return g
    body+=gather(0);transfer_pc=site+len(body)
    if mode=='ret' and not control:body+=e('ret r30')+e('wait 0')*2
    else:
        delta=site+LANDING-transfer_pc;body+=e(f'jmp_exec_any pc+{delta}',f'jmp_exec_any pc+{delta}')
    landing=gather(1)+e('pop_exec r0l, 1')
    if control:landing+=e('if_icmp r0l, ult, r10, 2, 1')
    landing+=gather(2);drain_pc=site+LANDING+len(landing)
    # A competing fallthrough still reaches the bounded drain regardless of
    # execution state, while leaving a separate diagnostic marker intact.
    body+=mov(28,FALL)+store(28,8,23)+e('wait 0')
    for op in ('jmp_exec_any','jmp_exec_none'):
        at=site+len(body);delta=drain_pc-at;body+=e(f'{op} pc+{delta}',f'{op} pc+{delta}')
    assert len(body)<=LANDING and (LANDING-len(body))%2==0
    body+=e('stop')*((LANDING-len(body))//2)+landing
    body+=(e('pop_exec r0l, 1')*2 if control else e('pop_exec r0l, 3')*drain)
    body+=mov(28,DONE)+store(28,8,22)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code,allow=('ret',) if mode=='ret' and not control else ())
    assert len(code)<1024*1024
    boundaries=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code) and site+LANDING in boundaries and drain_pc in boundaries
    return code,transfer_pc,drain,boundaries


def build(maximum,rotate,mode):
    assert maximum in STAGES and rotate in (0,1) and mode in ('original','ret')
    table=table_for(maximum,rotate);code,pc,drain,bounds=construct(table,mode)
    ctrl,_,_,_=construct(table,'original',True)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==oracle(table,'original',True),'known payload-only control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table,mode),'complete wide-counter hypothesis failed'
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,
        expected=oracle(table,'original',True),data_dir=DATA,
        gate=dict(maximum=maximum,rotate=rotate,mode=mode,transfer_pc=pc,drain_pop3_count=drain,
                  target=0x2000+P.drm.control_main()[1]+LANDING,code_bytes=len(code),boundaries=bounds,
                  actual_wide_counter_hypothesis_exact=True,payload_control_exact=True,
                  control_uses_wide_counter_write=False,control_uses_zero_pop=False,
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--maximum',type=int,choices=tuple(STAGES),default=63)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--mode',choices=('original','ret'),default='original')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.maximum,a.rotate,a.mode)
    print(json.dumps(dict(maximum=a.maximum,rotate=a.rotate,mode=a.mode,gates=True,drain=p['gate']['drain_pop3_count'],bytes=len(p['code']))),flush=True)
    if not a.hardware:return
    name=f'wide-r0-m{a.maximum}-r{a.rotate}-{a.mode}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];want=oracle(p['table'],a.mode)
        r['wide_analysis']=dict(exact=got==want,
            counter_values=[[[*sorted(set(v['table_after'][BASE+phase*PHASE_WORDS+j*32:BASE+phase*PHASE_WORDS+(j+1)*32])-{E.SENT})] for j in range(32)] for phase in range(3)],
            different_words=[i for i,(x,y) in enumerate(zip(v['table_after'],want[1])) if x!=y])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(exact=r.get('wide_analysis',{}).get('exact'),differences=r.get('wide_analysis',{}).get('different_words',[])[:12],
                         recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('wide_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
