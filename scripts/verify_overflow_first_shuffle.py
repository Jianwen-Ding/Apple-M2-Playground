#!/usr/bin/env python3
"""Verify complete overflow traces while retaining explicit model counterexamples."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import probe_overflow_first_shuffle as D
from verify_ret_mask_state import common
from verify_probe_sources import require_source
from overflow_hypothesis import counter_sync_hypothesis


def expected(table,n,cached):
    original=table[:32];after=[(d+n)%65536 if d else 0 for d in original]
    assert table[32:64]==after and table[64:96]==[max(d-1,0) for d in after]
    result=table.copy();result[96:128]=[0xf6600001]*32
    for phase in range(4):
        counters=original if phase==0 else after if phase<3 else [max(d-1,0) for d in after]
        writers=[i for i,d in enumerate(counters) if d==0 or phase==0 and cached]
        for bank in range(2):
            values=original if bank else counters
            for j,value in enumerate(values):
                for lane in writers:result[128+2048*phase+1024*bank+32*j+lane]=value
    result[8320:8352]=[0xf6600002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(utc=datetime.now(timezone.utc).isoformat(),simulator_binary_sha256=sha(D.P.cov.RUN),records={})
    def retain(path,r,prediction):
        hardware=r['variant']['out'],r['variant']['table_after']
        manifest['records'][str(path.relative_to(D.E.ROOT))]=dict(sha256=sha(path),model_exact=prediction==hardware,
            table_differences=[dict(word=i,actual=x,predicted=y) for i,(x,y) in enumerate(zip(hardware[1],prediction[1])) if x!=y])
    base_paths=sorted(D.B.DATA.glob('*.json.gz'));assert len(base_paths)==3
    for path in base_paths:
        r=json.load(gzip.open(path));g=r['gate'];p=D.B.build(g['maximum'],g['push_n'],g['cached'],g['rotate'])
        common(r,p,D.B,ac_online='0');want=expected(p['table'],g['push_n'],g['cached'])
        for phase in ('control_before','control_after'):assert (r[phase]['out'],r[phase]['table_after'])==want
        actual=(want[0],want[1].copy())
        if g['maximum']==65535:actual[1][2188]=64
        assert (r['variant']['out'],r['variant']['table_after'])==actual
        assert r['push_analysis']['exact']==(g['maximum']==31)
        with D.E.measured_model(), counter_sync_hypothesis():prediction=D.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==want;retain(path,r,prediction)
    # Explicit retained diagnostics, rather than requiring unrun plan options.
    simple=('repeat','wait1','seed1234','payload','half','integer','alu','sync','seed5678','repeat2','down','up','xor','rotate','postwait','postsync','payload-no-and','postmove')
    names={'overflow-first-shuffle-'+k+'.json.gz' for k in simple}
    names|={f'overflow-first-shuffle-{k}-n{n}-synced-r0.json.gz' for k in ('repeat','wait1') for n in (2,3)}
    names|={'overflow-first-shuffle-repeat-n1-cached-r0.json.gz','overflow-first-shuffle-repeat-n1-synced-r1.json.gz'}
    paths=sorted(D.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    exact=0;counterexamples=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];base=g['base_gate']
        n=base['push_n'];cached=base['cached'];rotate=base['rotate'];kind=g['kind']
        p=D.build(kind,n,cached,rotate);common(r,p,D,ac_online='0')
        require_source(D.B.__file__,g['base_builder_sha256'])
        want=expected(p['table'],n,cached)
        for phase in ('control_before','control_after'):assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        settled=cached or kind in ('repeat2','repeat4','sync','postsync','wait1','wait2','wait4')
        hardware=(want[0],want[1].copy())
        if settled:exact+=1
        else:
            counterexamples+=1
            lane=next(i for i,d in enumerate(p['table'][:32]) if d==65536-n)
            # 0x40 is the retained observation, not a derived architectural rule.
            # Explicit destination seeds isolate retention of their low halves.
            observed=int(kind[4:],16) if kind.startswith('seed') else 0x40
            hardware[1][128+2048+lane]=observed
            if kind=='payload-no-and':
                hardware[1][128+2048+lane]=0xcdcdcdcd
                hardware[1][64+lane]=64
        assert (r['variant']['out'],r['variant']['table_after'])==hardware,path.name
        assert r['first_shuffle_analysis']['exact']==settled
        assert r['variant']['table_after'][8352:]==[0xcdcdcdcd]*16
        with D.E.measured_model(), counter_sync_hypothesis():prediction=D.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==want
        assert (prediction==hardware)==settled
        retain(path,r,prediction)
    assert (exact,counterexamples)==(7,17)
    print('PASS 24 diagnostics / 72 dispatches: every full buffer/guard/control and recovery record verified; zero faults')
    print('PASS 7 complete model matches and 17 explicit counterexamples retained; no claim of an implemented hazard model')
    print('PASS n1/n2/n3, all five native forms, half/payload/integer variants, destination seeds, lane rotation and settling controls')
    assert manifest['simulator_binary_sha256']==sha(D.P.cov.RUN)
    manifest.update(cases=27,model_exact=9,model_counterexamples=18,independent_hardware_checks_passed=True,
        simulator_sources={name:sha(D.E.ROOT.parent/'AGX-Performance-Simulator'/name) for name in
                           ('rust/src/func.rs','rust/src/fsem.rs','rust/src/isa/exec.rs','rust/src/isa/compiled.rs','rust/src/isa/mod.rs')})
    if args.result:args.result.write_text(json.dumps(manifest,indent=1,sort_keys=True)+'\n')
    print('PASS including the base family: 27 programs / 81 dispatches, 9 model matches, 18 retained model counterexamples')


if __name__=='__main__':main()
