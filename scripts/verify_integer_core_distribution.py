#!/usr/bin/env python3
"""Offline arithmetic/core-plane validation and measured-peak model sensitivity."""
import argparse
from integer_recorded_model import RECORDED_FUNCTIONAL_SHA256
from collections import Counter
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st
import subprocess
import tempfile
import probe_integer_core_distribution as C
from verify_integer_immediate_cost import expected
import verify_integer_chain_cost as A


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def recorded_builder_available(digest):
    paths=[Path(C.__file__)]+list((C.DATA/'source-versions').glob('*--probe_integer_core_distribution.py.txt'))
    return any(sha(p)==digest for p in paths)


def independent_buffers(v,n,c,a,wg,sr):
    out,table=v['out'],v['table_after'];want_out,arith=expected(n,c,a,1)
    assert out==want_out and len(table)==n*(c+1)+16
    assert table[:n*c]==arith[:-16] and table[-16:]==[0xcdcdcdcd]*16
    tags=table[n*c:-16]
    if sr==19:
        assert tags==[64]*n
        return dict(allocation_tag_exact=True)
    masks=(0x3ff,0x1ff,0x1ff,0x3ff);counts=Counter()
    for start in range(0,n,wg):
        tag=tags[start];cluster,core=tag>>4,tag&15
        assert cluster<4 and masks[cluster]&(1<<core)
        assert all(v==tag for v in tags[start:start+wg])
        counts[tag]+=1
    clusters=Counter()
    for tag,groups in counts.items():clusters[tag>>4]+=groups
    assert sum(counts.values())==n//wg
    return dict(core_ids_valid=True,workgroups_uniform=True,cores_seen=len(counts),
        workgroups_per_core={str(k):v for k,v in sorted(counts.items())},
        workgroups_per_cluster={str(k):v for k,v in sorted(clusters.items())},
        minimum_workgroups_on_used_core=min(counts.values()),maximum_workgroups_on_used_core=max(counts.values()),
        final_dispatch_only=True)


def peak_prediction(code,peak,directory):
    path=directory/'shader.bin';path.write_bytes(code)
    args=[str(A.MODEL),str(path),'--grid','131072','--wg','128','--regs','64','--clock','1398','--busiest-core-wgs',str(peak)]
    for u in ('4=0','5=131072','6=1048576','7=0','8=2097152','9=0'):args+=['--uniform',u]
    v=subprocess.run(args,capture_output=True,text=True,timeout=60);assert v.returncode==0,v.stderr
    p=json.loads(v.stdout);assert p['warnings']==[] and p['paths']=='cost-emulation'
    assert p['busiest_core_wgs']==p['busiest_core_wgs_input']==peak
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    names={f'integer-core-s{sr}-n131072-w128-c{c}-a{a}-k64-t{t}.json.gz'
        for sr in (19,20) for c in (1,8) for a in (1024,4096) for t in range(3)}
    names|={f'integer-core-s{sr}-n32-w32-c{c}-a4096-k4-t0.json.gz' for sr in (19,20) for c in (1,8)}
    paths=sorted(C.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    exe=C.S.native();baseline_path=C.DATA/'prechange-defaults.json';baseline=json.loads(baseline_path.read_text())
    # Reject invalid CLI counts before a missing shader can be opened.
    for count in ('0','26','1025'):
        v=subprocess.run([str(A.MODEL),'/missing-agx-core-check-shader','--grid','131072','--wg','128','--busiest-core-wgs',count],capture_output=True,text=True)
        assert v.returncode!=0 and 'busiest_core_wgs' in v.stderr and 'No such file' not in v.stderr
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},paired={},placement_sensitivity={},
        builder_sha256=sha(Path(C.__file__)),sr_encoder_sha256=sha(Path(C.P.bench.get_sr.__code__.co_filename)),
        native_source_sha256=sha(C.S.NATIVE),native_binary_sha256=sha(exe),functional_binary_sha256=sha(C.P.cov.RUN),
        arithmetic_builder_sha256=sha(Path(C.I.__file__)),train_runner_sha256=sha(Path(C.T.__file__)),shared_runner_sha256=sha(Path(C.H.__file__)),
        dispatch_binary_sha256=sha(A.MODEL),prechange_defaults_sha256=sha(baseline_path),prechange_model_sha256=baseline['model_sha256'],
        model_sources={n:sha(A.SIM/n) for n in ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/bin/agx_dispatch.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameters={n:sha(A.SIM/n) for n in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    prepared={};cells={};codes={};boots=set();windows=[];dispatches=0;recorded_builders=set()
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];b=g['base_gate'];n,c,a,wg,k,sr=r['n'],b['chains'],b['adds'],r['wg'],g['repeats'],b['selector']
        key=n,c,a,wg,k,sr
        if key not in prepared:prepared[key]=C.build(*key)
        p=prepared[key];wanted=json.loads(json.dumps(p['gate']))
        assert recorded_builder_available(g['builder_sha256']);recorded_builders.add(g['builder_sha256'])
        wanted['builder_sha256']=g['builder_sha256'];assert g==wanted
        assert r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert r['native_binary_sha256']==report['native_binary_sha256'] and r['simulator_sha256']==RECORDED_FUNCTIONAL_SHA256
        assert hashlib.sha256(r['wrapper_text'].encode()).hexdigest()==r['wrapper_sha256']
        assert r['phase']=='finished' and not r.get('halted') and r['arithmetic_and_guards_exact'] and r['recovery_control_passed']
        assert r['before']['budget_used']==r['after']['budget_used']==0 and r['before']['ac_online']==r['after']['ac_online']=='1'
        assert r['before']['boot_id']==r['after']['boot_id'];boots.add(r['before']['boot_id'])
        for phase,count in (('control_before',1),('train',k),('control_after',1)):
            v=r[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            events=[json.loads(line) for line in v['stdout'].splitlines() if line.startswith('{')]
            assert [e['timing_gap_us'] for e in events if 'timing_gap_us' in e]==[1000]
            params=[e['params'] for e in events if 'params' in e];assert len(params)==1
            assert (params[0]['gen'],params[0]['variant'],params[0]['rev'],params[0]['clusters'],params[0]['ts_hz'])==(14,'C',17,4,1000000000)
            assert [e for e in events if e.get('completed')]==[dict(completed=True,count=n,words=n+32,repeats=count)]
            ss=v['samples'];assert len(ss)==count and [s['rep'] for s in ss]==list(range(count))
            checks=independent_buffers(v,n,c,a if phase=='train' else 0,wg,sr if phase=='train' else 19)
            if phase=='train':assert checks==r['final_buffer_checks']
            for s in ss:assert s['wait']==s['errno']==0 and s['drm_time'][0]<=s['fw_ts'][0]<s['fw_ts'][1]<=s['drm_time'][1]
        ss=r['train']['samples'];all_samples=r['control_before']['samples']+ss+r['control_after']['samples']
        assert all(x['fw_ts'][1]<=y['fw_ts'][0] for x,y in zip(all_samples,all_samples[1:]))
        windows.append((all_samples[0]['fw_ts'][0],all_samples[-1]['fw_ts'][1],path.name))
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in ss];host=[y['drm_time'][0]-x['drm_time'][1] for x,y in zip(ss,ss[1:])]
        assert all(t>=1000000 for t in host);q=k//4
        entry=dict(sha256=sha(path),firmware_ns=ns,host_inter_submission_ns=host,
            quarter_medians_ns=[st.median(ns[j:j+q]) for j in range(0,k,q)],final_buffer_checks=r['final_buffer_checks'],
            probe_start_fw=windows[-1][0])
        report['records'][path.name]=entry;dispatches+=k+2
        if n==131072:cells.setdefault((c,a,sr),[]).append(entry);codes[c,a,sr]=p['code']
    windows.sort();assert all(x[1]<=y[0] for x,y in zip(windows,windows[1:]))
    assert len(boots)==1 and dispatches==1608;report['chronological_records']=[x[2] for x in windows]
    with tempfile.TemporaryDirectory() as tmp:
        for (c,a,sr),trials in sorted(cells.items()):
            assert len(trials)==3
            model=A.prediction(codes[c,a,sr],131072,128,Path(tmp));assert model==baseline['predictions'][f'{c}:{a}:{sr}']
            late=[v for t in trials for v in t['firmware_ns'][-16:]]
            report['cells'][f'{c}:{a}:{sr}']=dict(late_median_ns=st.median(late),trial_late_medians_ns=[t['quarter_medians_ns'][-1] for t in trials],
                model=model,model_ns=1000*model['time_us'])
            if sr==20:
                per_trial=[]
                for t in trials:
                    peak=t['final_buffer_checks']['maximum_workgroups_on_used_core']
                    predicted=peak_prediction(codes[c,a,sr],peak,Path(tmp))
                    per_trial.append(dict(core_map=t['final_buffer_checks'],last_dispatch_ns=t['firmware_ns'][-1],
                        model_with_observed_peak=predicted,peak_to_default_model_ratio=predicted['time_us']/model['time_us'],
                        last_dispatch_to_peak_model_ratio=t['firmware_ns'][-1]/(1000*predicted['time_us'])))
                report['placement_sensitivity'][f'{c}:{a}']=per_trial
    for c in (1,8):
        for a in (1024,4096):
            tag,core=[report['cells'][f'{c}:{a}:{sr}'] for sr in (19,20)]
            report['paired'][f'{c}:{a}']=dict(sr20_to_sr19_late_ratio=core['late_median_ns']/tag['late_median_ns'])
    report['recorded_functional_sha256']=RECORDED_FUNCTIONAL_SHA256
    report.update(trains=28,dispatches=1608,timed_dispatches=1552,arithmetic_and_guards_exact=28,
        literal_final_buffers_exact=14,core_property_buffers_valid=14,recovery_controls_exact=56,fault_events=0,
        own_probe_windows_nonoverlapping=True,intermediate_buffers_captured=False,default_predictions_unchanged=8,calibration_changed=False)
    report['recorded_builder_sha256']=sorted(recorded_builders)
    assert report['functional_binary_sha256']==sha(C.P.cov.RUN) and report['dispatch_binary_sha256']==sha(A.MODEL)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 28 trains / 1608 dispatches: exact arithmetic/guards, 14 exact SR19 buffers, 14 valid SR20 maps, 56 exact controls, zero faults')
    print('PASS timestamps, actual delay, disjoint windows, source/binary bindings, CLI validation and eight unchanged default predictions')
    print('PAIRED',report['paired'])
    for cell,rows in report['placement_sensitivity'].items():
        print('PLACEMENT',cell,[(r['core_map']['cores_seen'],r['core_map']['maximum_workgroups_on_used_core'],r['peak_to_default_model_ratio'],r['last_dispatch_to_peak_model_ratio']) for r in rows])


if __name__=='__main__':main()
