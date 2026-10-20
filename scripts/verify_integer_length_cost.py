#!/usr/bin/env python3
"""Offline validation and adjacent-length residuals for controlled-gap trains."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st
import tempfile
import probe_integer_length_cost as L
from verify_integer_immediate_cost import expected
import verify_integer_chain_cost as A


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    names={f'integer-state-n131072-w128-c{c}-a{a}-g1000-k64-t{trial}.json.gz'
        for c in (1,8) for a in L.ADDS for trial in range(3)}
    names|={f'integer-state-n32-w32-c{c}-a4096-g1000-k4-t0.json.gz' for c in (1,8)}
    paths=sorted(L.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    L.configure();S=L.S;exe=S.native()
    previous=S.ROOT/'results/2026-10-20-integer-timing-state/analysis.json'
    previous_report=json.loads(previous.read_text())
    assert previous_report['native_source_sha256']==sha(S.NATIVE) and previous_report['native_binary_sha256']==sha(exe)
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},slopes={},
        builder_sha256=sha(Path(L.__file__)),native_source_sha256=sha(S.NATIVE),native_binary_sha256=sha(exe),
        origin_harness_sha256=sha(S.P.bench.REPO/'tests/drm_compute.c'),previous_analysis_sha256=sha(previous),
        arithmetic_builder_sha256=sha(Path(L.I.__file__)),train_runner_sha256=sha(Path(S.T.__file__)),
        gap_runner_sha256=sha(Path(S.__file__)),shared_runner_sha256=sha(Path(S.H.__file__)),
        functional_binary_sha256=sha(S.P.cov.RUN),dispatch_binary_sha256=sha(A.MODEL),
        model_sources={n:sha(A.SIM/n) for n in ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameters={n:sha(A.SIM/n) for n in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    prepared={};cells={};boots=set();windows=[];codes={};descriptors=set();dispatches=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];b=g['base_gate'];k=g['repeats']
        n,c,a,w=r['n'],b['chains'],b['adds'],r['wg'];key=n,c,a,w,k
        if key not in prepared:prepared[key]=L.build(*key)
        p=prepared[key];assert g==json.loads(json.dumps(p['gate']))
        assert r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert r['native_binary_sha256']==report['native_binary_sha256'] and r['simulator_sha256']==report['functional_binary_sha256']
        assert hashlib.sha256(r['wrapper_text'].encode()).hexdigest()==r['wrapper_sha256']
        assert r['phase']=='finished' and not r.get('halted') and r['final_arithmetic_exact'] and r['recovery_control_passed']
        assert r['before']['budget_used']==r['after']['budget_used']==0
        assert r['before']['ac_online']==r['after']['ac_online']=='1'
        assert r['before']['boot_id']==r['after']['boot_id'];boots.add(r['before']['boot_id'])
        for phase,count in (('control_before',1),('train',k),('control_after',1)):
            v=r[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            events=[json.loads(line) for line in v['stdout'].splitlines() if line.startswith('{')]
            assert [e['timing_gap_us'] for e in events if 'timing_gap_us' in e]==[1000]
            params=[e['params'] for e in events if 'params' in e];assert len(params)==1
            assert (params[0]['gen'],params[0]['variant'],params[0]['rev'],params[0]['clusters'],params[0]['ts_hz'])==(14,'C',17,4,1000000000)
            assert [e for e in events if e.get('completed')]==[dict(completed=True,count=n,words=n+32,repeats=count)]
            ss=v['samples'];assert len(ss)==count and [s['rep'] for s in ss]==list(range(count))
            assert (v['out'],v['table_after'])==expected(n,c,a if phase=='train' else 0,1)
            for s in ss:
                assert s['wait']==s['errno']==0 and s['drm_time'][0]<=s['fw_ts'][0]<s['fw_ts'][1]<=s['drm_time'][1]
                assert s['host_ns']>0
            if phase=='train':descriptors.add((n,tuple(e['usc_words_hex'] for e in events if 'usc_words_hex' in e),tuple(e['cdm_hex'] for e in events if 'cdm_hex' in e)))
        ss=r['train']['samples'];all_samples=r['control_before']['samples']+ss+r['control_after']['samples']
        assert all(x['fw_ts'][1]<=y['fw_ts'][0] for x,y in zip(all_samples,all_samples[1:]))
        windows.append((all_samples[0]['fw_ts'][0],all_samples[-1]['fw_ts'][1],path.name))
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in ss]
        idle=[y['fw_ts'][0]-x['fw_ts'][1] for x,y in zip(ss,ss[1:])]
        host_gap=[y['drm_time'][0]-x['drm_time'][1] for x,y in zip(ss,ss[1:])]
        assert all(v>=1000000 for v in host_gap)
        q=k//4;quarters=[st.median(ns[j:j+q]) for j in range(0,k,q)]
        entry=dict(sha256=sha(path),program_sha256=hashlib.sha256(bytes.fromhex(r['code'])).hexdigest(),
            firmware_ns=ns,preceding_firmware_idle_ns=idle,host_inter_submission_ns=host_gap,
            quarter_medians_ns=quarters,late_median_ns=quarters[-1],host_gap_median_ns=st.median(host_gap),
            observed_train_duty=sum(ns)/(ss[-1]['fw_ts'][1]-ss[0]['fw_ts'][0]),probe_start_fw=windows[-1][0])
        report['records'][path.name]=entry;dispatches+=k+2
        if n==131072:cells.setdefault((c,a),[]).append(entry);codes[c,a]=p['code']
    windows.sort();assert all(x[1]<=y[0] for x,y in zip(windows,windows[1:]))
    assert len(boots)==1 and dispatches==3180 and len(descriptors)==2
    report['chronological_records']=[x[2] for x in windows]
    with tempfile.TemporaryDirectory() as tmp:
        for (c,a),trials in sorted(cells.items()):
            assert len(trials)==3 and len({t['program_sha256'] for t in trials})==1
            late=[v for t in trials for v in t['firmware_ns'][-16:]];early=[v for t in trials for v in t['firmware_ns'][:16]]
            medians=[t['late_median_ns'] for t in trials];model=A.prediction(codes[c,a],131072,128,Path(tmp))
            report['cells'][f'{c}:{a}']=dict(trial_late_medians_ns=medians,early_median_ns=st.median(early),late_median_ns=st.median(late),
                trial_late_max_to_min_ratio=max(medians)/min(medians),minimum_late_sample_ns=min(late),maximum_late_sample_ns=max(late),
                host_gap_median_ns=st.median([v for t in trials for v in t['host_inter_submission_ns']]),
                observed_train_duty_median=st.median([t['observed_train_duty'] for t in trials]),
                code_bytes=len(codes[c,a]),model=model,model_ns=1000*model['time_us'])
    for c in (1,8):
        slopes={}
        for lo,hi in zip(L.ADDS,L.ADDS[1:]):
            low,high=[report['cells'][f'{c}:{a}'] for a in (lo,hi)]
            hw=(high['late_median_ns']-low['late_median_ns'])/(hi-lo)
            model=(high['model_ns']-low['model_ns'])/(hi-lo)
            slopes[f'{lo}:{hi}']=dict(hardware_ns_per_extra_add=hw,model_ns_per_extra_add=model,ratio=hw/model)
        report['slopes'][str(c)]=slopes
    report.update(trains=50,dispatches=3180,timed_dispatches=3080,final_train_buffers_exact=50,control_buffers_exact=100,
        fault_events=0,own_probe_windows_nonoverlapping=True,intermediate_buffers_captured=False,calibration_changed=False)
    assert report['functional_binary_sha256']==sha(S.P.cov.RUN) and report['native_binary_sha256']==sha(exe)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 50 trains / 3180 dispatches, every final buffer and 100 controls exact, zero faults')
    print('PASS actual delay, every timestamp bracket, source/binary bindings and disjoint windows')
    for cell,e in report['cells'].items():print('CELL',cell,'early/late ns',e['early_median_ns'],e['late_median_ns'],'trial ratio',e['trial_late_max_to_min_ratio'])
    print('SLOPES',report['slopes'])


if __name__=='__main__':main()
