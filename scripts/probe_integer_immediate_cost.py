#!/usr/bin/env python3
"""Matched bounded timing trains for ordinary positive immediate additions."""
import argparse
import hashlib
import json
from pathlib import Path
import probe_integer_chain_train as T

B,P=T.B,T.P
DATA=B.ROOT/'results/2026-10-20-integer-immediate-cost'


def scalar(n,chains,adds,increment):
    # Independent summation rather than the shader's interleaved construction.
    values=[]
    for c in range(chains):
        value=100+7*c
        for _ in range(adds//chains):value+=increment
        values.extend([value]*n)
    return [B.SENT]*(n+16)+[0xa5a50000+i for i in range(16)],values+[B.SENT]*16


def construct(n,chains,adds,increment):
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    body=e('iadd r20, r1, 0')+b''.join(mov(10+c,100+7*c) for c in range(chains))
    for j in range(adds):body+=e(f'iadd r{10+j%chains}, r{10+j%chains}, {increment}')
    for c in range(chains):
        body+=mov(28,c*n)+e('iadd r29, r20, r28')+store(10+c,8,29)+e('wait 0')
    code=P.drm.build_main(body+e('stop'));P.cov.gate(code)
    pc=0;bounds=[]
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16])
        assert info and info[0] in ('get_sr','iadd','mov_imm','if_icmp','device_store','wait','stop','pop_exec')
        bounds.append(pc);pc+=info[1]
    assert pc==len(code) and len(code)<65536
    return code,bounds


def build(n,chains,adds,wg,repeats,increment):
    assert n in (32,131072) and chains in (1,8) and adds in (64,1024,2048)
    assert wg in (32,128) and n%wg==0 and repeats in (4,64) and increment in (1,3)
    P.cov.install();code,bounds=construct(n,chains,adds,increment)
    control,_=construct(n,chains,0,increment);table=[B.SENT]*(n*chains+16)
    expected=scalar(n,chains,adds,increment);zero=scalar(n,chains,0,increment)
    assert P.cov.simulate(control,n,wg,64,0,table)==zero
    previous=table
    for _ in range(3):
        actual=P.cov.simulate(code,n,wg,64,0,previous)
        assert actual==expected;previous=actual[1]
    instruction=P.RS.e(f'iadd r10, r10, {increment}')
    # The immediate-3 baseline must be byte-identical to the preceding study.
    if increment==3:assert code==B.construct(n,chains,adds)[0]
    base=dict(lanes=n,chains=chains,adds=adds,wg=wg,increment=increment,register_halves=64,
        code_bytes=len(code),boundaries=bounds,maximum_result=max(expected[1][:-16]),
        instruction_hex=instruction.hex(),instruction_decode=P.cov.ASMB.info(instruction+bytes(16)),
        complete_program_exact=True,zero_add_control_exact=True)
    return dict(code=code,control=control,table=table,n=n,wg=wg,regs=64,expected=zero,final_expected=expected,
        train_prefix=f'integer-immediate-i{increment}',train_data_dir=DATA,
        train_scratch=Path('/scratch/apple-m2-playground/integer-immediate-cost'),
        gate=dict(base_gate=base,repeats=repeats,repeat_invariance_exact=True,final_buffer_oracle_exact=True,
            intermediate_buffers_captured=False,builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            train_runner_sha256=hashlib.sha256(Path(T.__file__).read_bytes()).hexdigest()))


def run(p,trial):
    r=T.hardware(p,trial)
    print(json.dumps(dict(name=r['name'],exact=r.get('final_arithmetic_exact'),
        recovery=r.get('recovery_control_passed'),halted=r.get('halted'),timing=r.get('timing',{}).get('last_quarter_median_ns'),
        budget=r['after']['budget_used'])),flush=True)
    if r.get('halted') or not r.get('final_arithmetic_exact'):raise RuntimeError('stop: candidate or recovery failed')
    return r


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lanes',type=int,default=32);ap.add_argument('--chains',type=int,default=1)
    ap.add_argument('--adds',type=int,default=64);ap.add_argument('--wg',type=int,default=32)
    ap.add_argument('--repeats',type=int,default=4);ap.add_argument('--increment',type=int,choices=(1,3),default=1)
    ap.add_argument('--trial',type=int,default=0);ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.lanes,a.chains,a.adds,a.wg,a.repeats,a.increment)
    print(json.dumps(dict(gates=True,base=p['gate']['base_gate'],repeats=a.repeats)),flush=True)
    if a.hardware:run(p,a.trial)


if __name__=='__main__':main()
