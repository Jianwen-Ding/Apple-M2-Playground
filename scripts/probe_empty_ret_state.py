#!/usr/bin/env python3
"""Observe empty-issued return's counter state and transfer/fallthrough choice.

A full five-stage trace is placed in the bounded fallthrough as well as the
valid return landing. Wait controls validate original state; known jump
surrogates validate original/swap states at both possible trace locations.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_ret_levels as L

P,E,CF=L.P,L.E,L.CF
DATA=L.ROOT/'results/2026-10-20-empty-ret-state'


def table_for(maximum,rotate):
    original=[1+(i+rotate)%maximum for i in range(32)]
    return original+L.transformed(original,'swap')+[E.SENT]*(7*32+16)


def fall_trace(code,transfer_pc):
    start=transfer_pc+6;landing=P.drm.control_main()[1]+L.LANDING
    e=P.RS.e;body=b''
    for phase,reg in enumerate(range(22,27)):
        if phase:body+=e('pop_exec r0l, 1')
        body+=e('mov r28, r0l')+P.RS.agx_loop.store(28,8,reg)+e('wait 0')
    body+=P.RS.mov(28,L.FALL)+P.RS.agx_loop.store(28,8,27)+e('wait 0')+e('stop')
    assert len(body)<=landing-start and (landing-start-len(body))%2==0
    body+=e('stop')*((landing-start-len(body))//2)
    result=code[:start]+body+code[landing:]
    assert len(result)==len(code)
    return result


def oracle(table,model,falls=True):
    out,tab=L.oracle(table,model)
    if falls:tab[256:288]=[L.FALL]*32
    return out,tab


def build(maximum,rotate,known=False):
    if maximum not in range(1,5):raise ValueError(maximum)
    table=table_for(maximum,rotate)
    actual,pc,decoded=L.construct(table,'ret');actual=fall_trace(actual,pc)
    control=actual[:pc]+P.RS.e('wait 0')+actual[pc+2:]
    original_jump,_,_=L.construct(table,'original-jump')
    desired_jump,desired_pc,_=L.construct(table,'desired-jump')
    desired_fall=fall_trace(desired_jump,desired_pc)
    op='jmp_exec_any' if 0 in table[32:64] else 'jmp_exec_none'
    desired_fall=desired_fall[:desired_pc]+P.RS.e(f'{op} pc+6',f'{op} pc+6')+desired_fall[desired_pc+6:]
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,'original')
        assert P.cov.simulate(actual,32,32,64,0,table)==oracle(table,'legacy')
        assert P.cov.simulate(original_jump,32,32,64,0,table)==oracle(table,'original',False)
        assert P.cov.simulate(desired_jump,32,32,64,0,table)==oracle(table,'swap',False)
        assert P.cov.simulate(desired_fall,32,32,64,0,table)==oracle(table,'swap')
    P.cov.gate(control)
    return dict(code=desired_fall if known else actual,control=control,table=table,n=32,wg=32,regs=64,
                expected=oracle(table,'original'),data_dir=DATA,
                gate=dict(maximum=maximum,rotate=rotate,known_surrogate=known,issuing_mask_empty=True,
                          target=0x2000+P.drm.control_main()[1]+L.LANDING,ret_pc=pc,
                          original_control_exact=True,actual_legacy_hypothesis_exact=True,
                          original_landing_surrogate=original_jump.hex(),desired_landing_surrogate=desired_jump.hex(),
                          desired_fallthrough_surrogate=desired_fall.hex(),actual_ret_code=actual.hex(),
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--depth',type=int,choices=range(1,5),default=1)
    ap.add_argument('--rotate',type=int,default=0)
    ap.add_argument('--known-surrogate',action='store_true')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.depth,a.rotate,a.known_surrogate)
    print(json.dumps({'depth':a.depth,'rotate':a.rotate,'known':a.known_surrogate,'empty_ret_gates':True}),flush=True)
    if not a.hardware:return
    name=f'empty-ret-{a.depth}-r{a.rotate}-'+('surrogate' if a.known_surrogate else 'actual')
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=(v.get('out'),v.get('table_after'))
        r['empty_ret_analysis']=dict(models={f'{m}-{location}':got==oracle(p['table'],m,location=='fall')
                                            for m in ('legacy','swap','decrement','clear') for location in ('fall','landing')},
                                     writers=[[i for i in range(32) if v['table_after'][(3+phase)*32+i]!=E.SENT] for phase in range(5)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('empty_ret_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__=='__main__':main()
