#!/usr/bin/env python3
"""Observe RET when ordinary r0 writes leave the original issuing mask stale.

All physical lanes remain issue-active after the ordinary write. Uniform valid
r30 targets avoid selection ambiguity. IF/jump controls construct known arrival
state without RET or ordinary r0 writes. All traces and drains are bounded.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_r0_write_mask as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-ret-stale-exec'
LANDING=1024
PRE=0xf2200001
DONE=0xf2200002
FALL=0xfa220001


def oracle(table,model):
    tab=table.copy();ds=table[:32];tab[32:64]=[PRE]*32
    if model=='falls':tab[192:224]=[FALL]*32
    else:
        state=[2]*32 if model=='issue' else [2 if d==0 else 0 if d==1 else d for d in ds] if model in ('counter','counter-stale') else ds.copy()
        for phase in range(4):
            if phase:state=[max(d-1,0) for d in state]
            tab[(2+phase)*32:(3+phase)*32]=[d if phase==0 and (model=='branch-only' or model=='counter-stale' and original!=0) else 0 if d==0 else E.SENT for d,original in zip(state,ds)]
        tab[192:224]=[DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def build(op,maximum,rotate=0,uniform=False):
    assert op in B.OPS and 1<=maximum<=31 and rotate in (0,1)
    assert op!='mov-imm' or uniform
    P.cov.install();e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    table=B.values(maximum,rotate,uniform)+[E.SENT]*(6*32+16)
    setup=e('iadd r20, r1, 0')+B.load(10,20,True)+e('wait 0')
    for plane,reg in zip(range(1,7),range(21,27)):
        setup+=mov(29,plane*32)+e(f'iadd r{reg}, r20, r29')
    setup+=mov(28,PRE)+store(28,8,21)+e('wait 0')+mov(30,0x2000+P.drm.control_main()[1]+LANDING)
    write={'mov-half':'mov r0l, r10l','mov-full':'mov r0, r10','add-half':'iadd r0l, r10l, 0','mov-imm':f'mov_imm r0l, {maximum}'}[op]
    actual=setup+e(write)+e('wait 0');ret_pc=P.drm.control_main()[1]+len(actual)
    actual+=e('ret r30')+e('wait 0')*2
    ctrl=setup+e('if_icmp r0l, ueq, r20, 255, 1')+e('if_fcmp r0l, eq, 0.0, 0.0, 1','push_exec r0l, 1')
    delta=LANDING-len(ctrl);ctrl+=e(f'jmp_exec_none pc+{delta}',f'jmp_exec_none pc+{delta}')
    fallback=e('pop_exec r0l, 1')*(maximum+3)+mov(28,FALL)+store(28,8,26)+e('wait 0')+e('stop')
    landing=b''
    for phase,reg in enumerate(range(22,26)):
        if phase:landing+=e('pop_exec r0l, 1')
        landing+=e('mov r28, r0l')+store(28,8,reg)+e('wait 0')
    landing+=e('pop_exec r0l, 1')*(maximum+2)+mov(28,DONE)+store(28,8,26)+e('wait 0')+e('stop')
    def finish(body):
        body+=fallback;assert len(body)<=LANDING and (LANDING-len(body))%2==0
        return P.drm.build_main(body+e('stop')*((LANDING-len(body))//2)+landing)
    code=finish(actual);control=finish(ctrl)
    P.cov.gate(code,allow=('ret',));P.cov.gate(control)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,'issue'),'known depth-two jump control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table,'counter-stale'),'measured conditional RET update gate failed'
    boundaries=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code) and P.drm.control_main()[1]+LANDING in boundaries
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,expected=oracle(table,'issue'),data_dir=DATA,
        gate=dict(op=op,maximum=maximum,rotate=rotate,uniform=uniform,write=write,ret_pc=ret_pc,
                  target=0x2000+P.drm.control_main()[1]+LANDING,boundaries=boundaries,
                  actual_measured_model_exact=True,no_ret_control_exact=True,
                  base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--op',choices=B.OPS,default='mov-half')
    ap.add_argument('--maximum',type=int,choices=range(1,32),default=3)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--uniform',action='store_true')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.op,a.maximum,a.rotate,a.uniform)
    print(json.dumps(dict(op=a.op,maximum=a.maximum,rotate=a.rotate,uniform=a.uniform,gates=True)),flush=True)
    if not a.hardware:return
    name=f'ret-stale-{a.op}-m{a.maximum}-r{a.rotate}-'+('uniform' if a.uniform else 'mixed');r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['stale_ret_analysis']=dict(
            models={m:got==oracle(p['table'],m) for m in ('issue','counter','counter-stale','branch-only','sync-only','falls')},
            snapshot_values=[sorted(set(v['table_after'][(2+j)*32:(3+j)*32])-{E.SENT}) for j in range(4)],
            writers=[[i for i,x in enumerate(v['table_after'][(2+j)*32:(3+j)*32]) if x!=E.SENT] for j in range(4)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('stale_ret_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not any(r.get('stale_ret_analysis',{}).get('models',{}).values()):raise SystemExit(3)


if __name__=='__main__':main()
