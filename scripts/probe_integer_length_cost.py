#!/usr/bin/env python3
"""Program-length comparison with a fixed 1000 us host gap and exact oracles."""
import argparse
import gzip
import json
from pathlib import Path
import random
import probe_integer_timing_state as S

I,P=S.I,S.P
DATA=S.ROOT/'results/2026-10-20-integer-length-cost'
SCRATCH=Path('/scratch/apple-m2-playground/integer-length-cost')
ADDS=(64,256,512,768,1024,1536,2048,4096)


def configure():
    # The existing runner owns these output destinations. Its submission,
    # watchdog, parser, lock and recovery code is reused without changes.
    S.DATA=DATA;S.SCRATCH=SCRATCH


def build(n,chains,adds,wg,repeats):
    assert n in (32,131072) and chains in (1,8) and adds in ADDS
    assert wg in (32,128) and n%wg==0 and repeats in (4,64)
    P.cov.install();code,bounds=I.construct(n,chains,adds,1)
    control,_=I.construct(n,chains,0,1);table=[I.B.SENT]*(n*chains+16)
    final=I.scalar(n,chains,adds,1);zero=I.scalar(n,chains,0,1)
    assert P.cov.simulate(control,n,wg,64,0,table)==zero
    previous=table
    for _ in range(3):
        actual=P.cov.simulate(code,n,wg,64,0,previous)
        assert actual==final;previous=actual[1]
    assert max(final[1][:-16])<=4196
    base=dict(lanes=n,chains=chains,adds=adds,wg=wg,increment=1,register_halves=64,
        code_bytes=len(code),boundaries=bounds,maximum_result=max(final[1][:-16]),
        complete_program_exact=True,zero_add_control_exact=True)
    return dict(code=code,control=control,table=table,n=n,wg=wg,regs=64,expected=zero,final_expected=final,
        gate=dict(base_gate=base,repeats=repeats,repeat_invariance_exact=True,final_buffer_oracle_exact=True,
            intermediate_buffers_captured=False,builder_sha256=S.sha(Path(__file__)),
            arithmetic_builder_sha256=S.sha(Path(I.__file__)),train_runner_sha256=S.sha(Path(S.T.__file__)),
            timing_state=dict(gap_us=1000,runner_sha256=S.sha(Path(S.__file__)),
                native_source_sha256=S.sha(S.NATIVE),origin_harness_sha256=S.sha(P.bench.REPO/'tests/drm_compute.c'),
                output_dataset=DATA.name)))


def require_pilots():
    for c in (1,8):
        path=DATA/f'integer-state-n32-w32-c{c}-a4096-g1000-k4-t0.json.gz'
        r=json.load(gzip.open(path))
        assert r['phase']=='finished' and r['final_arithmetic_exact'] and r['recovery_control_passed'] and not r.get('halted')
        assert r['after']['budget_used']==0


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--matrix',action='store_true')
    ap.add_argument('--hardware',action='store_true');a=ap.parse_args();configure()
    if a.matrix:
        if a.hardware:require_pilots()
        programs={}
        for c in (1,8):
            for adds in ADDS:
                programs[c,adds]=build(131072,c,adds,128,64)
                print(json.dumps(dict(gated=True,chains=c,adds=adds,bytes=len(programs[c,adds]['code']))),flush=True)
        if not a.hardware:return
        exe=S.native();print('ALL FULL-PROGRAM GATES PASSED; serial hardware matrix',flush=True)
        for trial in range(3):
            keys=list(programs);random.Random(20261020+trial).shuffle(keys)
            for key in keys:S.run(programs[key],trial,exe)
    else:
        for c in (1,8):
            p=build(32,c,4096,32,4);print(json.dumps(dict(pilot_gated=True,chains=c,bytes=len(p['code']))),flush=True)
            if a.hardware:S.run(p,0,S.native())


if __name__=='__main__':main()
