#!/usr/bin/env python3
"""Offline full-buffer and timing verification of matched immediate-add trains."""
import argparse
from integer_recorded_model import RECORDED_FUNCTIONAL_SHA256
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st
import tempfile
import probe_integer_immediate_cost as I
import verify_integer_chain_cost as A


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def expected(n,c,a,i):
    return ([I.B.SENT]*(n+16)+[0xa5a50000+j for j in range(16)],
        [v for chain in range(c) for v in [100+7*chain+i*(a//c)]*n]+[I.B.SENT]*16)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    names={f'integer-immediate-i{i}-n131072-w128-c{c}-a{a}-k64-t{t}.json.gz'
        for i in (1,3) for c in (1,8) for a in (1024,2048) for t in range(3)}
    names|={f'integer-immediate-i{i}-n32-w32-c1-a64-k4-t0.json.gz' for i in (1,3)}
    paths=sorted(I.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},paired={},slopes={},
        builder_sha256=sha(Path(I.__file__)),runner_sha256=sha(Path(I.T.__file__)),
        shared_runner_sha256=sha(Path(I.T.H.__file__)),functional_binary_sha256=sha(I.P.cov.RUN),
        harness_sha256=sha(I.P.bench.REPO/'tests/drm_compute.c'),dispatch_binary_sha256=sha(A.MODEL),
        model_sources={n:sha(A.SIM/n) for n in ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameters={n:sha(A.SIM/n) for n in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    prepared={};cells={};boots=set();windows=[];dispatches=0;instructions={}
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];b=g['base_gate'];n,c,a,w,k,i=r['n'],b['chains'],b['adds'],r['wg'],g['repeats'],b['increment']
        key=n,c,a,w,k,i
        if key not in prepared:prepared[key]=I.build(*key)
        p=prepared[key]
        assert g==json.loads(json.dumps(p['gate']))
        assert r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert r['harness_sha256']==report['harness_sha256'] and r['simulator_sha256']==RECORDED_FUNCTIONAL_SHA256
        assert r['phase']=='finished' and not r.get('halted') and r['final_arithmetic_exact'] and r['recovery_control_passed']
        assert r['before']['budget_used']==r['after']['budget_used']==0
        assert r['before']['ac_online']==r['after']['ac_online']=='1'
        assert r['before']['boot_id']==r['after']['boot_id'];boots.add(r['before']['boot_id'])
        for phase in ('control_before','control_after'):
            v=r[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout') and len(v['samples'])==1
            assert (v['out'],v['table_after'])==expected(n,c,0,i)
        v=r['train'];ss=v['samples']
        assert v['ok'] and v['returncode']==0 and not v.get('host_timeout') and len(ss)==k
        assert [s['rep'] for s in ss]==list(range(k))
        assert v['completion']==[dict(completed=True,count=n,words=n+32,repeats=k)]
        assert (v['out'],v['table_after'])==expected(n,c,a,i)
        all_samples=r['control_before']['samples']+ss+r['control_after']['samples']
        for s in all_samples:assert s['wait']==s['errno']==0 and 0<s['fw_ts'][0]<s['fw_ts'][1]
        assert all(x['fw_ts'][1]<=y['fw_ts'][0] for x,y in zip(all_samples,all_samples[1:]))
        windows.append((all_samples[0]['fw_ts'][0],all_samples[-1]['fw_ts'][1],path.name))
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in ss];q=k//4
        timing=dict(ns=ns,first_ns=ns[0],last_ns=ns[-1],minimum_ns=min(ns),maximum_ns=max(ns),
            first_quarter_median_ns=st.median(ns[:q]),last_quarter_median_ns=st.median(ns[-q:]))
        assert timing==r['timing'];dispatches+=k+2
        report['records'][path.name]=dict(sha256=sha(path),timing=timing,probe_start_fw=windows[-1][0])
        instructions[i]=b['instruction_hex']
        if n==131072:cells.setdefault((c,a,i),[]).append(timing)
    windows.sort();assert all(x[1]<=y[0] for x,y in zip(windows,windows[1:]))
    assert len(boots)==1 and dispatches==1596
    report['chronological_records']=[x[2] for x in windows]
    report['instructions']=instructions
    # Check that the only bit difference is immediate 1 versus 3, with equal length.
    assert len(bytes.fromhex(instructions[1]))==len(bytes.fromhex(instructions[3]))==8
    assert int.from_bytes(bytes.fromhex(instructions[1]),'little')^int.from_bytes(bytes.fromhex(instructions[3]),'little')==2<<28
    with tempfile.TemporaryDirectory() as tmp:
        for (c,a,i),trials in sorted(cells.items()):
            late=[v for t in trials for v in t['ns'][-16:]];all_ns=[v for t in trials for v in t['ns']]
            p=prepared[131072,c,a,128,64,i];model=A.prediction(p['code'],131072,128,Path(tmp))
            report['cells'][f'{c}:{a}:{i}']=dict(trials=trials,late_median_ns=st.median(late),
                late_minimum_ns=min(late),late_maximum_ns=max(late),all_minimum_ns=min(all_ns),
                model=model,model_ns=1000*model['time_us'],shader_bytes=len(p['code']))
    for c in (1,8):
        for a in (1024,2048):
            one,three=[report['cells'][f'{c}:{a}:{i}'] for i in (1,3)]
            assert one['shader_bytes']==three['shader_bytes'] and one['model_ns']==three['model_ns']
            report['paired'][f'{c}:{a}']=dict(i3_to_i1_late_ratio=three['late_median_ns']/one['late_median_ns'],
                trial_ratios=[y['last_quarter_median_ns']/x['last_quarter_median_ns'] for x,y in zip(one['trials'],three['trials'])])
        for i in (1,3):
            low,high=[report['cells'][f'{c}:{a}:{i}'] for a in (1024,2048)]
            hw=(high['late_median_ns']-low['late_median_ns'])/1024
            model=(high['model_ns']-low['model_ns'])/1024
            report['slopes'][f'{c}:{i}']=dict(hardware_ns_per_extra_add=hw,model_ns_per_extra_add=model,ratio=hw/model)
    report['recorded_functional_sha256']=RECORDED_FUNCTIONAL_SHA256
    report.update(trains=26,dispatches=1596,timed_dispatches=1544,final_train_buffers_exact=26,control_buffers_exact=52,
        fault_events=0,own_probe_windows_nonoverlapping=True,intermediate_buffers_captured=False,calibration_changed=False)
    assert report['functional_binary_sha256']==sha(I.P.cov.RUN) and report['dispatch_binary_sha256']==sha(A.MODEL)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 26 trains / 1596 dispatches; every final buffer and 52 controls exact, zero faults')
    print('PAIRED',report['paired']);print('SLOPES',report['slopes'])


if __name__=='__main__':main()
