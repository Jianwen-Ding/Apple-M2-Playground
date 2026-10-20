#!/usr/bin/env python3
"""Check default overflow refusal and explicitly incomplete experimental replay.

Uses saved original shader/input/readback bytes only. No shader regeneration
or GPU access. Accepted paths must match complete hardware buffers; refused
paths must report the specific unresolved activation diagnostic.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import probe_empty_stop as E
from overflow_hypothesis import counter_sync_hypothesis

DATA=E.ROOT/'results/2026-10-20-overflow-guard'
GROUPS={'push-overflow':3,'overflow-first-shuffle':24,'overflow-register-visibility':27}


@contextmanager
def default_overflow_model():
    key='AGX_EXPERIMENTAL_EXEC_OVERFLOW';old=os.environ.pop(key,None)
    try:yield
    finally:
        if old is not None:os.environ[key]=old


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    E.P.cov.install();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(utc=datetime.now(timezone.utc).isoformat(),simulator_binary_sha256=sha(E.P.cov.RUN),
                simulator_sources={n:sha(E.ROOT.parent/'AGX-Performance-Simulator'/n) for n in
                                   ('rust/src/func.rs','rust/src/fsem.rs','rust/src/isa/exec.rs','rust/src/isa/compiled.rs','rust/src/isa/mod.rs')},records={})
    accepted=refused=hyp_matches=hyp_mismatches=0
    with E.measured_model():
        for group,count in GROUPS.items():
            paths=sorted((E.ROOT/'results'/('2026-10-20-'+group)).glob('*.json.gz'));assert len(paths)==count
            for path in paths:
                r=json.load(gzip.open(path));assert r['phase']=='finished' and r['recovery_control_passed'] and not r.get('halted')
                assert r['before']['budget_used']==r['after']['budget_used']==0
                code=bytes.fromhex(r['code']);table=r['table_in'];hardware=r['variant']['out'],r['variant']['table_after']
                info=dict(sha256=sha(path))
                with default_overflow_model():
                    control=E.P.cov.simulate(bytes.fromhex(r['control_code']),32,32,64,0,table)
                    assert control==(r['control_before']['out'],r['control_before']['table_after'])==(r['control_after']['out'],r['control_after']['table_after'])
                    try:prediction=E.P.cov.simulate(code,32,32,64,0,table)
                    except RuntimeError as error:
                        assert 'execution-counter overflow activation spacing unresolved' in str(error),(path.name,str(error))
                        info['default']='refused_unresolved_activation';refused+=1
                    else:
                        assert prediction==hardware,path.name
                        info['default']='exact_hardware_match';accepted+=1
                with counter_sync_hypothesis():prediction=E.P.cov.simulate(code,32,32,64,0,table)
                matches=prediction==hardware;hyp_matches+=matches;hyp_mismatches+=not matches
                info['counter_sync_hypothesis_exact']=matches
                info['hypothesis_table_differences']=[dict(word=i,actual=a,predicted=b) for i,(a,b) in enumerate(zip(hardware[1],prediction[1])) if a!=b]
                report['records'][str(path.relative_to(E.ROOT))]=info
    assert (accepted,refused,hyp_matches,hyp_mismatches)==(11,43,19,35),(accepted,refused,hyp_matches,hyp_mismatches)
    assert report['simulator_binary_sha256']==sha(E.P.cov.RUN)
    report.update(cases=54,default_exact=accepted,default_refused=refused,experimental_exact=hyp_matches,
                  experimental_counterexamples=hyp_mismatches,passed=True)
    if args.result:
        args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(report,sort_keys=True,indent=1)+'\n')
    print('PASS default model: 11 exact accepted programs, 43 explicit unresolved-activation refusals, all controls exact')
    print('PASS explicit counter-sync hypothesis: 19 exact programs, all 35 original counterexamples retained; no claim of timing accuracy')
    print('PASS 54 original byte/input replays; no GPU or shader regeneration, original 162 dispatches all recovered with zero faults')


if __name__=='__main__':main()
