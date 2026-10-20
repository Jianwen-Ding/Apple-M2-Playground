#!/usr/bin/env python3
"""Gather initialized low execution counters from every lane before/after RET.

Immediate shuffle indices avoid index-register quad contamination. The upper
r0 half is masked away. A payload-only no-return control checks every source,
writer and address. All complete paths are gated before optional hardware.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_ret_levels as L
from run_drm_cpu_clock import load

P,E,CF=L.P,L.E,L.CF
DATA=L.ROOT/'results/2026-10-20-masked-r0'
LANDING=8192
BASE=96
PHASE_WORDS=2048
END=BASE+2*PHASE_WORDS
PRE=0xcafe0001
DONE=0xcafe0002
FALL=0xfa110002


def table_for(maximum,rotate):
    ds=L.depths(maximum,rotate)
    return ds+L.transformed(ds,'swap')+[E.SENT]*(END+32+16-64)


def oracle(table,mode,payload_only=False):
    result=table.copy();result[64:96]=[PRE]*32
    states=[table[:32],table[:32] if mode=='original' else table[32:64]]
    for phase,ds in enumerate(states):
        for bank in range(2):
            source=table[:32] if bank or payload_only else ds
            for j in range(32):
                base=BASE+phase*PHASE_WORDS+bank*1024+j*32
                result[base:base+32]=[source[j] if d==0 else E.SENT for d in ds]
    result[END:END+32]=[DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],result


def construct(table,mode,payload_only=False):
    P.cov.install();e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    site=P.drm.control_main()[1]
    body=e('iadd r20, r1, 0')
    for base,reg in ((64,21),(END,22)):
        body+=mov(12,base)+e(f'iadd r{reg}, r20, r12')
    body+=load(10,20,True)+mov(12,32)+e('iadd r13, r20, r12')+load(11,13,True)+e('wait 0')
    body+=mov(29,0xffff)+mov(30,0x2000+site+LANDING)+mov(28,PRE)+store(28,8,21)+e('wait 0')
    for threshold in range(max(table[:32]),0,-1):body+=e(f'if_icmp r0l, ult, r10, {threshold}, 1')
    def gather(phase):
        b=b''
        for bank in range(2):
            source=10 if bank or payload_only else 0
            for j in range(32):
                base=BASE+phase*PHASE_WORDS+bank*1024+j*32
                b+=e(f'simd_shuffle r28, r{source}, {j}')+e('and r28, r28, r29')
                b+=mov(12,base)+e('iadd r13, r20, r12')+store(28,8,13)+e('wait 0')
        return b
    body+=gather(0)
    if mode=='desired':
        body+=e('pop_exec r0l, 1')*4
        for threshold in range(max(table[32:64]),0,-1):body+=e(f'if_icmp r0l, ult, r11, {threshold}, 1')
    pc=site+len(body)
    if mode=='ret':body+=e('ret r30')+e('wait 0')*2
    else:
        delta=site+LANDING-pc
        body+=e(f'jmp_exec_any pc+{delta}',f'jmp_exec_any pc+{delta}')
    body+=e('pop_exec r0l, 1')*4+mov(28,FALL)+store(28,8,22)+e('wait 0')+e('stop')
    assert len(body)<=LANDING and (LANDING-len(body))%2==0
    body+=e('stop')*((LANDING-len(body))//2)
    body+=gather(1)+e('pop_exec r0l, 1')*4+mov(28,DONE)+store(28,8,22)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code,allow=('ret',) if mode=='ret' else ())
    # Every byte decodes, and the target is an instruction boundary.
    boundaries=[];at=0
    while at<len(code):
        info=P.cov.ASMB.info(code[at:at+16]);assert info and info[1]>0
        boundaries.append(at);at+=info[1]
    assert at==len(code) and site+LANDING in boundaries
    return code,pc


def build(maximum,rotate,mode):
    assert 1<=maximum<=4 and mode in ('original','desired','ret')
    table=table_for(maximum,rotate)
    actual,pc=construct(table,mode)
    control,_=construct(table,'original',True)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,'original',True)
        for m in ('original','desired','ret'):
            code,_=construct(table,m)
            assert P.cov.simulate(code,32,32,64,0,table)==oracle(table,m),m
    return dict(code=actual,control=control,table=table,n=32,wg=32,regs=64,
                expected=oracle(table,'original',True),data_dir=DATA,
                gate=dict(maximum=maximum,rotate=rotate,mode=mode,transfer_pc=pc,
                          target=0x2000+P.drm.control_main()[1]+LANDING,
                          actual_exact=True,all_three_paths_exact=True,payload_control_exact=True,
                          low_bits=16,immediate_indices=list(range(32)),
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--depth',type=int,choices=range(1,5),default=3)
    ap.add_argument('--rotate',type=int,default=0)
    ap.add_argument('--mode',choices=('original','desired','ret'),default='original')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.depth,a.rotate,a.mode)
    print(json.dumps(dict(depth=a.depth,rotate=a.rotate,mode=a.mode,gates=True,code_bytes=len(p['code']))),flush=True)
    if not a.hardware:return
    name=f'masked-r0-{a.depth}-r{a.rotate}-{a.mode}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=(v['out'],v['table_after']);want=oracle(p['table'],a.mode)
        r['masked_r0_analysis']=dict(exact=got==want,
            phase_values=[[[sorted(set(v['table_after'][BASE+phase*PHASE_WORDS+bank*1024+j*32:BASE+phase*PHASE_WORDS+bank*1024+(j+1)*32])-{E.SENT}) for j in range(32)] for bank in range(2)] for phase in range(2)],
            different_words=[i for i,(x,y) in enumerate(zip(v['table_after'],want[1])) if x!=y])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('masked_r0_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('masked_r0_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
