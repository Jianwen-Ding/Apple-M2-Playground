#!/usr/bin/env python3
"""Matched arithmetic/tag trains across workgroup and neighboring grid sizes."""
import argparse
import gzip
import json
from pathlib import Path
import random
import probe_integer_core_distribution as C

S,P=C.S,C.P
DATA=S.ROOT/'results/2026-10-20-integer-geometry-cost'
SCRATCH=Path('/scratch/apple-m2-playground/integer-geometry-cost')
GEOMETRIES=((131072,32),(131072,64),(131072,128),(131072,256),(130944,128),(131200,128))


def configure():C.DATA=DATA;C.SCRATCH=SCRATCH


def build(n,c,a,wg,k,sr):
    assert (n,wg) in GEOMETRIES or (wg in (32,64,128,256) and n==wg)
    assert c in (1,8) and a in (1024,4096) and k in (4,64) and sr in (19,20)
    P.cov.install();code,bounds,pc=C.construct(n,c,a,sr);twin,_,other_pc=C.construct(n,c,a,39-sr)
    assert pc==other_pc and len(code)==len(twin)
    assert int.from_bytes(code,'little')^int.from_bytes(twin,'little')==(19^20)<<(8*pc+16)
    control,_,_=C.construct(n,c,0,19);table=[C.I.B.SENT]*(n*(c+1)+16)
    expected=C.literal(n,c,0,64);assert P.cov.simulate(control,n,wg,64,0,table)==expected
    previous=table;model_expected=C.literal(n,c,a,64 if sr==19 else 0)
    for _ in range(3):
        actual=P.cov.simulate(code,n,wg,64,0,previous)
        assert actual==model_expected;C.check(*actual,n,c,a,wg,sr);previous=actual[1]
    return dict(code=code,control=control,table=table,n=n,wg=wg,regs=64,expected=expected,
        gate=dict(base_gate=dict(lanes=n,chains=c,adds=a,wg=wg,selector=sr,increment=1,register_halves=64,
            code_bytes=len(code),boundaries=bounds,selector_pc=pc,twins_differ_only_in_selector=True,maximum_result=100+a),
            repeats=k,simulator_complete_scalar_exact=True,repeat_invariance_exact=True,
            core_plane_uses_properties_on_hardware=sr==20,intermediate_buffers_captured=False,gap_us=1000,
            builder_sha256=S.sha(Path(__file__)),core_runner_sha256=S.sha(Path(C.__file__)),
            arithmetic_builder_sha256=S.sha(Path(C.I.__file__)),sr_encoder_sha256=S.sha(Path(P.bench.get_sr.__code__.co_filename)),
            train_runner_sha256=S.sha(Path(C.T.__file__)),shared_runner_sha256=S.sha(Path(C.H.__file__)),
            native_source_sha256=S.sha(S.NATIVE),output_dataset=DATA.name))


def pilot_names():
    return [f'integer-core-s{sr}-n{wg}-w{wg}-c{c}-a4096-k4-t0.json.gz'
        for wg in (32,64,128,256) for c in (1,8) for sr in (19,20)]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--matrix',action='store_true');ap.add_argument('--hardware',action='store_true')
    args=ap.parse_args();configure()
    if args.matrix:
        if args.hardware:
            for name in pilot_names():
                r=json.load(gzip.open(DATA/name))
                assert r['phase']=='finished' and r['arithmetic_and_guards_exact'] and r['recovery_control_passed'] and not r.get('halted')
        programs={}
        for n,wg in GEOMETRIES:
            for c in (1,8):
                for a in (1024,4096):
                    for sr in (19,20):
                        key=n,c,a,wg,64,sr;programs[key]=build(*key);print('GATED',key,flush=True)
        if not args.hardware:return
        exe=S.native();print('ALL 48 FULL-PROGRAM GATES PASSED; serial matrix',flush=True)
        for trial in range(3):
            keys=list(programs);random.Random(20261020+trial).shuffle(keys)
            for key in keys:C.run(programs[key],trial,exe)
    else:
        for wg in (32,64,128,256):
            for c in (1,8):
                for sr in (19,20):
                    p=build(wg,c,4096,wg,4,sr);print('PILOT GATED',wg,c,sr,flush=True)
                    if args.hardware:C.run(p,0,S.native())


if __name__=='__main__':main()
