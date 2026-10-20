#!/usr/bin/env python3
"""Do ordinary low-r0 writes update execution immediately or at the next pop?

All lanes are initially active. Capture low r0 immediately after a known-source
ordinary write, then after pop1 and a bounded full reconvergence. No transfer,
loop, barrier, uninitialized source or out-of-bounds memory is involved.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_empty_stop as E
from run_drm_cpu_clock import load

P,CF=E.P,E.CF
DATA=E.ROOT/'results/2026-10-20-r0-write-mask'
OPS=('mov-half','mov-full','add-half','mov-imm')
PRE=0xf1100001
DONE=0xf1100002


def values(maximum,rotate,uniform):
    return [maximum]*32 if uniform else [(i+rotate)%(maximum+1) for i in range(32)]


def oracle(table,model='deferred'):
    tab=table.copy();ds=table[:32];tab[32:64]=[PRE]*32
    tab[64:96]=[(0 if model=='ignored' else d) if model!='immediate' or d==0 else E.SENT for d in ds]
    tab[96:128]=[0 if d<=1 or model in ('register-only','ignored') else E.SENT for d in ds]
    tab[128:160]=[DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def build(op,maximum,rotate=0,uniform=False):
    assert op in OPS and 1<=maximum<=31 and rotate in (0,1)
    assert op!='mov-imm' or uniform
    P.cov.install();e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    table=values(maximum,rotate,uniform)+[E.SENT]*(4*32+16)
    setup=e('iadd r20, r1, 0')+load(10,20,True)+e('wait 0')
    for plane,reg in zip(range(1,5),range(21,25)):
        setup+=mov(29,plane*32)+e(f'iadd r{reg}, r20, r29')
    setup+=mov(28,PRE)+store(28,8,21)+e('wait 0')
    write={'mov-half':'mov r0l, r10l','mov-full':'mov r0, r10','add-half':'iadd r0l, r10l, 0','mov-imm':f'mov_imm r0l, {maximum}'}[op]
    candidate=setup+e(write)+e('wait 0')+e('mov r28, r0l')+store(28,8,22)+e('wait 0')
    control=setup+e('mov r28, r10l')+store(28,8,22)+e('wait 0')
    for threshold in range(max(table[:32]),0,-1):control+=e(f'if_icmp r0l, ult, r10, {threshold}, 1')
    tail=e('pop_exec r0l, 1')+e('mov r28, r0l')+store(28,8,23)+e('wait 0')
    tail+=e('pop_exec r0l, 1')*(maximum+2)+mov(28,DONE)+store(28,8,24)+e('wait 0')+e('stop')
    code=P.drm.build_main(candidate+tail);ctrl=P.drm.build_main(control+tail)
    P.cov.gate(code);P.cov.gate(ctrl)
    with E.measured_model():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==oracle(table),'known IF control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table),'current deferred-sync hypothesis failed'
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=oracle(table),data_dir=DATA,
        gate=dict(op=op,maximum=maximum,rotate=rotate,uniform=uniform,write=write,
                  write_pc=P.drm.control_main()[1]+len(setup),write_hex=e(write).hex(),
                  control_exact=True,actual_deferred_hypothesis_exact=True,
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--op',choices=OPS,default='mov-half')
    ap.add_argument('--maximum',type=int,choices=range(1,32),default=3)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--uniform',action='store_true')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.op,a.maximum,a.rotate,a.uniform)
    print(json.dumps(dict(op=a.op,maximum=a.maximum,rotate=a.rotate,uniform=a.uniform,gates=True)),flush=True)
    if not a.hardware:return
    name=f'r0-write-{a.op}-m{a.maximum}-r{a.rotate}-'+('uniform' if a.uniform else 'mixed')
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['r0_write_analysis']=dict(
            models={m:got==oracle(p['table'],m) for m in ('deferred','immediate','register-only','ignored')},
            checkpoint_writers=[[i for i,x in enumerate(v['table_after'][plane*32:(plane+1)*32]) if x!=E.SENT] for plane in (2,3)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('r0_write_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not any(r.get('r0_write_analysis',{}).get('models',{}).values()):raise SystemExit(3)


if __name__=='__main__':main()
