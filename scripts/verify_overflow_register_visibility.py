#!/usr/bin/env python3
"""Verify prepared-index register traces and explicit model limitations."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import probe_overflow_register_visibility as B
from verify_ret_mask_state import common


def cases():
    yield (31,1,False,'shuffle','none','balanced')
    for op in ('imm','shuffle'):yield (65535,1,True,op,'none','balanced')
    for op in ('imm','shuffle','copy','add'):yield (65535,1,False,op,'none','balanced')
    for op,delays in (('imm',('mov1','mov2','mov4','mov5','mov6','mov7','mov8')),('shuffle',('mov2','mov4','mov5','mov6','mov7','mov8','wait'))):
        for delay in delays:yield (65535,1,False,op,delay,'balanced')
    for layout in ('low8','highonly'):yield (65535,1,False,'shuffle','none',layout)
    for n in (2,3):
        for op in ('imm','shuffle'):yield (65535,n,False,op,'none','balanced')


def expected(table,bad=()):
    tab=table.copy();tab[96:128]=[0x1234]*32
    for lane,mask in enumerate(table[64:96]):
        value=0xbeef if mask and lane not in bad else 0x1234
        if mask:tab[128+lane]=tab[160+lane]=value
        tab[192+lane]=value
    tab[224:256]=[0xf7700001]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def observations(g,table):
    # A compact encoding of this exact retained matrix, not an ISA-wide rule.
    if g['maximum']==31 or g['cached'] or g['delay'] in ('wait','mov7','mov8'):return []
    wrapped=[i for i,d in enumerate(table[:32]) if d==65536-g['push_n']]
    if g['op']=='shuffle':return [] if g['delay']=='mov6' else [i for i in wrapped if i<16]
    return [i for i in wrapped if i>=16] if g['delay']=='mov6' else wrapped


def name(case):
    maximum,n,cached,op,delay,layout=case
    return f'overflow-visibility-m{maximum}-n{n}-'+('cached' if cached else 'synced')+f'-{op}-{delay}'+('' if layout=='balanced' else '-'+layout)+'.json.gz'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(utc=datetime.now(timezone.utc).isoformat(),simulator_binary_sha256=sha(B.P.cov.RUN),records={})
    matrix=list(cases());paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}=={name(c) for c in matrix}
    exact=0;counterexamples=0
    for case in matrix:
        path=B.DATA/name(case);r=json.load(gzip.open(path));g=r['gate'];p=B.build(*case);common(r,p,B,ac_online='0')
        tab=p['table'];assert len(tab)==272 and tab[32:64]==[0xbeef]*32
        assert tab[64:96]==[int(d==0 or (d+g['push_n'])%65536==0) for d in tab[:32]]
        bad=observations(g,tab);want=expected(tab);actual=expected(tab,bad)
        for phase in ('control_before','control_after'):assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        assert (r['variant']['out'],r['variant']['table_after'])==actual,path.name
        a=r['visibility_analysis'];assert a['exact']==(not bad)
        assert a['first']==actual[1][128:160] and a['after_wait']==actual[1][160:192] and a['after_drain']==actual[1][192:224]
        assert r['variant']['table_after'][256:]==[0xcdcdcdcd]*16
        # All indices were formed before divergence, and the first store is
        # immediately after the tested first instruction, without any AND/index ALU.
        info=B.P.cov.ASMB.info(p['code'][g['op_pc']:g['op_pc']+16]);next_pc=g['op_pc']+info[1]
        store=B.P.cov.ASMB.info(p['code'][next_pc:next_pc+16]);assert store[0]=='device_store'
        f=dict(store[3]);assert f['R']==56 and f['O']==44
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,tab)
        assert prediction==want and (prediction==actual)==(not bad)
        exact+=not bad;counterexamples+=bool(bad)
        manifest['records'][str(path.relative_to(B.E.ROOT))]=dict(sha256=sha(path),model_exact=not bad,retained_destination_lanes=bad)
    assert (exact,counterexamples)==(10,17)
    assert manifest['simulator_binary_sha256']==sha(B.P.cov.RUN)
    manifest.update(cases=27,model_exact=exact,model_counterexamples=counterexamples,independent_hardware_checks_passed=True,
        simulator_sources={n:sha(B.E.ROOT.parent/'AGX-Performance-Simulator'/n) for n in ('rust/src/func.rs','rust/src/isa/exec.rs','rust/src/isa/compiled.rs','rust/src/isa/mod.rs')})
    if args.result:args.result.write_text(json.dumps(manifest,sort_keys=True,indent=1)+'\n')
    print('PASS 27 prepared-index programs / 81 dispatches: direct first/after-wait/after-drain destination reads, all buffers/guards/controls exact, zero faults')
    print('PASS 10 model matches, 17 explicit counterexamples; immediate/copy/add also affected, masked destinations retain their seeds')
    print('PASS tested spacing boundary and lane dependence recorded without treating instruction counts as calibrated cycles')


if __name__=='__main__':main()
