#!/usr/bin/env python3
"""Ordinary positive-integer add timing: dependent versus interleaved chains.

Straight-line measured arithmetic only. Register allocation and total add
count stay fixed across chain shapes. Whole programs and complete buffers
must match scalar oracles before hardware; zero-add controls bracket each run.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_control_followup as H

P=H.P
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'results/2026-10-20-integer-chain-cost'
SENT=0xcdcdcdcd


def oracle(n,chains,steps):
    out=[SENT]*(n+16)+[0xa5a50000+i for i in range(16)]
    table=[]
    for c in range(chains):table += [100+7*c+3*(steps//chains)]*n
    return out,table+[SENT]*16


def construct(n,chains,steps):
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    body=e('iadd r20, r1, 0')+b''.join(mov(10+c,100+7*c) for c in range(chains))
    for j in range(steps):body+=e(f'iadd r{10+j%chains}, r{10+j%chains}, 3')
    for c in range(chains):
        body+=mov(28,c*n)+e('iadd r29, r20, r28')+store(10+c,8,29)+e('wait 0')
    body+=e('stop');code=P.drm.build_main(body);P.cov.gate(code)
    assert len(code)<1024*1024
    pc=0;boundaries=[]
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        assert info[0] in ('get_sr','iadd','mov_imm','if_icmp','device_store','wait','stop','pop_exec')
        boundaries.append(pc);pc+=info[1]
    assert pc==len(code)
    return code,boundaries


def build(n,chains,steps,wg):
    assert n in (32,32768,131072) and chains in (1,2,4,8)
    assert steps in (0,64,256,1024,2048,4096) and steps%chains==0
    assert wg in (32,128,256) and n%wg==0
    P.cov.install();table=[SENT]*(n*chains+16)
    code,bounds=construct(n,chains,steps);control,_=construct(n,chains,0)
    assert P.cov.simulate(control,n,wg,64,0,table)==oracle(n,chains,0),'zero-add complete control failed'
    assert P.cov.simulate(code,n,wg,64,0,table)==oracle(n,chains,steps),'complete arithmetic oracle failed'
    return dict(code=code,control=control,table=table,n=n,wg=wg,regs=64,expected=oracle(n,chains,0),data_dir=DATA,
        gate=dict(lanes=n,chains=chains,adds=steps,wg=wg,register_halves=64,code_bytes=len(code),boundaries=bounds,
                  maximum_result=100+7*(chains-1)+3*(steps//chains),complete_program_exact=True,
                  zero_add_control_exact=True,builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def run(p,rep):
    g=p['gate'];name=f'integer-chain-n{p["n"]}-w{p["wg"]}-c{g["chains"]}-a{g["adds"]}-r{rep}'
    r=H.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        r['arithmetic_exact']=(v['out'],v['table_after'])==oracle(p['n'],g['chains'],g['adds'])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(name=name,exact=r.get('arithmetic_exact'),firmware_ns=v.get('fw_ns'),
                         power=r['after']['ac_online'],recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted') or not r.get('arithmetic_exact'):raise RuntimeError('arithmetic/recovery check failed; stop batch')
    return r


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lanes',type=int,choices=(32,32768,131072),default=32)
    ap.add_argument('--chains',type=int,choices=(1,2,4,8),default=1)
    ap.add_argument('--adds',type=int,choices=(0,64,256,1024,2048,4096),default=64)
    ap.add_argument('--wg',type=int,choices=(32,128,256),default=32)
    ap.add_argument('--rep',type=int,default=0);ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.lanes,a.chains,a.adds,a.wg)
    print(json.dumps(dict(gates=True,lanes=a.lanes,chains=a.chains,adds=a.adds,wg=a.wg,bytes=len(p['code']))),flush=True)
    if a.hardware:run(p,a.rep)


if __name__=='__main__':main()
