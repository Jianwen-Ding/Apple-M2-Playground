#!/usr/bin/env python3
"""Verify bounded arithmetic trains and summarize consecutive-dispatch timing.

No GPU access. Final buffers and bracketing controls are checked in full;
timestamps are checked for every completed dispatch. Intermediate result
buffers are explicitly outside what the retained harness captures.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st
import tempfile
import probe_integer_chain_train as B
import verify_integer_chain_cost as A


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_available(digest):
    paths=[Path(B.__file__)]+list((B.DATA/'source-versions').glob('*--probe_integer_chain_train.py.txt'))
    return any(sha(p)==digest for p in paths)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    names={f'integer-train-n131072-w128-c{c}-a{a}-k64-t{trial}.json.gz' for c in (1,8) for a in (1024,2048,4096) for trial in range(3)}
    names.add('integer-train-n32-w32-c1-a64-k4-t0.json.gz')
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},slopes={},
        functional_binary_sha256=sha(B.P.cov.RUN),dispatch_binary_sha256=sha(A.MODEL),
        harness_sha256=sha(B.P.bench.REPO/'tests/drm_compute.c'),shared_runner_sha256=sha(Path(B.H.__file__)),
        model_sources={n:sha(A.SIM/n) for n in ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameters={n:sha(A.SIM/n) for n in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    prepared={};cells={};codes={};boots=set();windows=[];dispatches=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];base=g['base_gate'];k=g['repeats']
        key=(r['n'],base['chains'],base['adds'],r['wg'],k)
        if key not in prepared:prepared[key]=B.build(*key)
        p=prepared[key]
        assert source_available(g['builder_sha256']) and g['base_builder_sha256']==sha(Path(B.B.__file__))
        assert r['harness_sha256']==report['harness_sha256'] and r['simulator_sha256']==report['functional_binary_sha256']
        assert r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert g['repeat_invariance_exact'] and g['final_buffer_oracle_exact'] and not g['intermediate_buffers_captured']
        assert r['phase']=='finished' and not r.get('halted') and r['final_arithmetic_exact'] and r['recovery_control_passed']
        assert r['before']['budget_used']==r['after']['budget_used']==0
        assert r['before']['ac_online']==r['after']['ac_online']=='1'
        assert r['before']['boot_id']==r['after']['boot_id'];boots.add(r['before']['boot_id'])
        for phase in ('control_before','control_after'):
            v=r[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            assert len(v['samples'])==1
            assert (v['out'],v['table_after'])==A.scalar(r['n'],base['chains'],0)
        v=r['train'];samples=v['samples']
        assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
        assert len(samples)==k and [s['rep'] for s in samples]==list(range(k))
        assert v['completion']==[dict(completed=True,count=r['n'],words=r['n']+32,repeats=k)]
        assert (v['out'],v['table_after'])==A.scalar(r['n'],base['chains'],base['adds'])
        all_samples=r['control_before']['samples']+samples+r['control_after']['samples']
        for s in all_samples:assert s['wait']==s['errno']==0 and 0<s['fw_ts'][0]<s['fw_ts'][1]
        assert all(a['fw_ts'][1]<=b['fw_ts'][0] for a,b in zip(all_samples,all_samples[1:]))
        windows.append((all_samples[0]['fw_ts'][0],all_samples[-1]['fw_ts'][1],path.name))
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in samples];quarter=k//4
        timing=dict(ns=ns,first_ns=ns[0],last_ns=ns[-1],minimum_ns=min(ns),maximum_ns=max(ns),
            first_quarter_median_ns=st.median(ns[:quarter]),last_quarter_median_ns=st.median(ns[-quarter:]))
        assert r['timing']==timing
        report['records'][path.name]=dict(sha256=sha(path),samples=k,timing=timing)
        dispatches+=k+2
        if r['n']==131072:
            cell=(base['chains'],base['adds']);cells.setdefault(cell,[]).append(timing);codes[cell]=p['code']
    windows.sort();assert all(a[1]<=b[0] for a,b in zip(windows,windows[1:])), 'measured probe windows overlap'
    assert len(boots)==1 and dispatches==1194
    isolated_path=B.B.DATA/'analysis.json';isolated=json.loads(isolated_path.read_text())
    report['isolated_analysis_sha256']=sha(isolated_path)
    with tempfile.TemporaryDirectory() as tmp:
        for (chains,adds),trials in sorted(cells.items()):
            assert len(trials)==3
            late=[n for t in trials for n in t['ns'][-16:]]
            early=[n for t in trials for n in t['ns'][:16]]
            model=A.prediction(codes[chains,adds],131072,128,Path(tmp))
            entry=dict(trials=3,timings=trials,early_median_ns=st.median(early),late_median_ns=st.median(late),
                early_to_late_ratio=st.median(early)/st.median(late),model_ns=1000*model['time_us'],model=model,
                late_minimum_ns=min(late),late_maximum_ns=max(late),shader_bytes=len(codes[chains,adds]))
            if adds in (1024,2048):entry['late_to_isolated_fast_ratio']=entry['late_median_ns']/isolated['cells'][f'{chains}:{adds}']['fast_cluster_median_ns']
            report['cells'][f'{chains}:{adds}']=entry
    for chains in (1,8):
        rows={}
        for lo,hi in ((1024,2048),(2048,4096)):
            a,b=(report['cells'][f'{chains}:{n}'] for n in (lo,hi))
            hw=(b['late_median_ns']-a['late_median_ns'])/(hi-lo);model=(b['model_ns']-a['model_ns'])/(hi-lo)
            rows[f'{lo}:{hi}']=dict(hardware_ns_per_extra_add=hw,model_ns_per_extra_add=model,ratio=hw/model)
        report['slopes'][str(chains)]=rows
    assert report['functional_binary_sha256']==sha(B.P.cov.RUN) and report['dispatch_binary_sha256']==sha(A.MODEL)
    report.update(trains=19,dispatches=1194,timed_dispatches=1156,final_train_buffers_exact=19,control_buffers_exact=38,
        fault_events=0,own_probe_windows_nonoverlapping=True,intermediate_buffers_captured=False,calibration_changed=False)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 19 bounded trains / 1194 completed dispatches, 19 final buffers and 38 controls exact, zero faults')
    print('PASS every timestamp/wait, repeat indices, source/binary provenance and nonoverlapping probe windows; intermediate buffers are not captured')
    for cell,entry in report['cells'].items():print('CELL',cell,'early/late',entry['early_to_late_ratio'],'late ns',entry['late_median_ns'])
    print('SLOPES',report['slopes'])


if __name__=='__main__':main()
