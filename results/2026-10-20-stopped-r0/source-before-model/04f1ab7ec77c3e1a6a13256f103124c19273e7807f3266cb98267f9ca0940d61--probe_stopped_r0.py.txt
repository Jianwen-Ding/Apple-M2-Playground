#!/usr/bin/env python3
"""Observe low r0 storage and survival after partial STOP, using bounded gathers.

The exact wait control pops once and gathers both counters and initialized
payloads. The candidate differs by only wait -> stop before that pop.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_masked_r0 as B

P,E,CF=B.P,B.E,B.CF
DATA=B.L.ROOT/'results/2026-10-20-stopped-r0'


def oracle(table,stop=False,dead_value=0,payload="depth",fallback=False):
    result=table.copy();result[64:96]=[B.PRE]*32
    original=table[:32]
    for phase in range(2):
        for bank in range(2):
            values=(list(range(32)) if payload=='lane' else original) if bank else (original if phase==0 else [dead_value if stop and d==0 else max(d-1,0) for d in original])
            if fallback=="quad" and stop and phase and bank:
                values=[values[next((k for k in range(j//4*4,j//4*4+4) if original[k]!=0),j)] if original[j]==0 else values[j] for j in range(32)]
            for j in range(32):
                base=B.BASE+phase*B.PHASE_WORDS+bank*1024+j*32
                result[base:base+32]=[(values[i] if fallback=='self' and stop and phase and original[j]==0 else values[j]) if (d==0 if phase==0 else (d==1 or not stop and d==0)) else E.SENT for i,d in enumerate(original)]
    result[B.END:B.END+32]=[E.SENT if stop and d==0 else B.DONE for d in original]
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],result


def construct(table,stop,payload="depth"):
    assert payload in ("depth","lane")
    code,pc=B.construct(table,'original')
    e=P.RS.e;site=P.drm.control_main()[1];landing=site+B.LANDING
    prefix=code[:pc]
    if payload=='lane':
        at=site+len(e('iadd r20, r1, 0'))
        prefix=code[:at]+e('iadd r14, r20, 0')+code[at:pc]
        for j in range(32):
            old=e(f'simd_shuffle r28, r10, {j}');new=e(f'simd_shuffle r28, r14, {j}')
            assert len(old)==len(new)
            prefix=prefix.replace(old,new)
            code=code[:landing]+code[landing:].replace(old,new)
        pc=len(prefix)
    body=e('stop' if stop else 'wait 0')+e('pop_exec r0l, 1')
    delta=landing-pc-len(body)
    body+=e(f'jmp_exec_any pc+{delta}',f'jmp_exec_any pc+{delta}')
    body+=e('pop_exec r0l, 1')*4+P.RS.mov(28,B.FALL)+P.RS.agx_loop.store(28,8,22)+e('wait 0')+e('stop')
    assert len(body)<=landing-pc and (landing-pc-len(body))%2==0
    body+=e('stop')*((landing-pc-len(body))//2)
    code=prefix+body+code[landing:]
    P.cov.gate(code)
    return code,pc


def build(maximum,rotate,payload="depth"):
    assert 1<=maximum<=4
    table=B.table_for(maximum,rotate)
    code,pc=construct(table,True,payload);control,_=construct(table,False,payload)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,payload=payload)
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table,True,payload=payload)
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,
                expected=oracle(table,payload=payload),data_dir=DATA,
                gate=dict(maximum=maximum,rotate=rotate,stop_pc=pc,payload=payload,
                          wait_control_exact=True,actual_storage_hypothesis_exact=True,
                          hypothesis='stopped lanes stay dead and retain low r0 = 0 across pop',
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--depth',type=int,choices=range(1,5),default=3)
    ap.add_argument('--rotate',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    ap.add_argument('--payload',choices=('depth','lane'),default='lane')
    a=ap.parse_args();p=build(a.depth,a.rotate,a.payload)
    print(json.dumps(dict(depth=a.depth,rotate=a.rotate,stop_storage_gate=True)),flush=True)
    if not a.hardware:return
    name=f'stopped-r0-{a.depth}-r{a.rotate}'+('-lane' if a.payload=='lane' else '');r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=(v['out'],v['table_after']);want=oracle(p['table'],True,payload=a.payload)
        r['stopped_r0_analysis']=dict(models={str(x):got==oracle(p['table'],True,x,a.payload) for x in (0,1,2,0xffff)},
             quad_first_live_payload=got==oracle(p['table'],True,0,a.payload,'quad'),
             stopped_source_self=got==oracle(p['table'],True,0,a.payload,'self'),
             gathered_low=[[sorted(set(v['table_after'][B.BASE+B.PHASE_WORDS+bank*1024+j*32:B.BASE+B.PHASE_WORDS+bank*1024+(j+1)*32])-{E.SENT}) for j in range(32)] for bank in range(2)],
             different_words=[i for i,(x,y) in enumerate(zip(v['table_after'],want[1])) if x!=y])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('stopped_r0_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not any(r.get('stopped_r0_analysis',{}).get('models',{}).values()) and not r.get('stopped_r0_analysis',{}).get('quad_first_live_payload') and not r.get('stopped_r0_analysis',{}).get('stopped_source_self'):raise SystemExit(3)


if __name__=='__main__':main()
