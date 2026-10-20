#!/usr/bin/env python3
"""CPU-only verification of complete buffers, controlled gaps and timing states."""
import argparse
from integer_recorded_model import RECORDED_FUNCTIONAL_SHA256
from datetime import datetime,timezone
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st
import subprocess
import tempfile
import probe_integer_timing_state as S
from verify_integer_immediate_cost import expected
import verify_integer_chain_cost as A


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    names={f'integer-state-n131072-w128-c{c}-a1024-g{gap}-k64-t{trial}.json.gz'
        for c in (1,8) for gap in (0,250,1000) for trial in range(6)}
    names|={f'integer-state-n32-w32-c1-a64-g{gap}-k4-t0.json.gz' for gap in (0,250,1000)}
    paths=sorted(S.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    exe=S.native();origin=S.P.bench.REPO/'tests/drm_compute.c'
    diff=''.join(difflib.unified_diff(origin.read_text().splitlines(True),S.NATIVE.read_text().splitlines(True),
        fromfile='AGX-Performance-Simulator/tests/drm_compute.c',tofile='experiments/arithmetic/drm_integer_timing.c'))
    assert diff==(S.DATA/'native-origin.patch').read_text()
    for invalid in ('10001','-1'):
        v=subprocess.run([str(exe),'/dev/null','/dev/null','32','/tmp/agx-unused-timing-readback','4','64'],
            env=dict(PATH='/usr/bin',AGX_REPEAT_GAP_US=invalid),capture_output=True,text=True)
        assert v.returncode==1 and 'timing-gap-bound' in v.stdout
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},models={},
        builder_sha256=sha(Path(S.__file__)),native_source_sha256=sha(S.NATIVE),native_binary_sha256=sha(exe),
        origin_harness_sha256=sha(origin),origin_diff_sha256=sha(S.DATA/'native-origin.patch'),
        arithmetic_builder_sha256=sha(Path(S.I.__file__)),train_runner_sha256=sha(Path(S.T.__file__)),
        shared_runner_sha256=sha(Path(S.H.__file__)),functional_binary_sha256=sha(S.P.cov.RUN),dispatch_binary_sha256=sha(A.MODEL),
        model_sources={n:sha(A.SIM/n) for n in ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameters={n:sha(A.SIM/n) for n in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    prepared={};cells={};boots=set();windows=[];codes={};descriptors=set();dispatches=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];b=g['base_gate'];k=g['repeats'];gap=g['timing_state']['gap_us']
        n,c,a,w=r['n'],b['chains'],b['adds'],r['wg'];key=n,c,a,w,k
        if key not in prepared:prepared[key]=S.build(*key,0)
        p=prepared[key];wanted=json.loads(json.dumps(p['gate']));wanted['timing_state']['gap_us']=gap
        assert g==wanted and r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert r['native_binary_sha256']==report['native_binary_sha256'] and r['simulator_sha256']==RECORDED_FUNCTIONAL_SHA256
        assert hashlib.sha256(r['wrapper_text'].encode()).hexdigest()==r['wrapper_sha256']
        assert r['phase']=='finished' and not r.get('halted') and r['final_arithmetic_exact'] and r['recovery_control_passed']
        assert r['before']['budget_used']==r['after']['budget_used']==0
        assert r['before']['ac_online']==r['after']['ac_online']=='1'
        assert r['before']['boot_id']==r['after']['boot_id'];boots.add(r['before']['boot_id'])
        for phase,count in (('control_before',1),('train',k),('control_after',1)):
            v=r[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            events=[json.loads(line) for line in v['stdout'].splitlines() if line.startswith('{')]
            assert [e['timing_gap_us'] for e in events if 'timing_gap_us' in e]==[gap]
            params=[e['params'] for e in events if 'params' in e];assert len(params)==1
            assert (params[0]['gen'],params[0]['variant'],params[0]['rev'],params[0]['clusters'],params[0]['ts_hz'])==(14,'C',17,4,1000000000)
            assert [e for e in events if e.get('completed')]==[dict(completed=True,count=n,words=n+32,repeats=count)]
            ss=v['samples'];assert len(ss)==count and [s['rep'] for s in ss]==list(range(count))
            assert (v['out'],v['table_after'])==expected(n,c,a if phase=='train' else 0,1)
            for s in ss:
                assert s['wait']==s['errno']==0 and s['drm_time'][0]<=s['fw_ts'][0]<s['fw_ts'][1]<=s['drm_time'][1]
                assert s['host_ns']>0
            if phase=='train':
                descriptors.add((n,tuple(e['usc_words_hex'] for e in events if 'usc_words_hex' in e),tuple(e['cdm_hex'] for e in events if 'cdm_hex' in e)))
        ss=r['train']['samples'];all_samples=r['control_before']['samples']+ss+r['control_after']['samples']
        assert all(x['fw_ts'][1]<=y['fw_ts'][0] for x,y in zip(all_samples,all_samples[1:]))
        windows.append((all_samples[0]['fw_ts'][0],all_samples[-1]['fw_ts'][1],path.name))
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in ss]
        idle=[y['fw_ts'][0]-x['fw_ts'][1] for x,y in zip(ss,ss[1:])]
        host_gap=[y['drm_time'][0]-x['drm_time'][1] for x,y in zip(ss,ss[1:])]
        assert all(v>=gap*1000 for v in host_gap),'configured sleep missing from observed submission interval'
        q=k//4;quarters=[st.median(ns[j:j+q]) for j in range(0,k,q)]
        entry=dict(sha256=sha(path),program_sha256=hashlib.sha256(bytes.fromhex(r['code'])).hexdigest(),
            firmware_ns=ns,preceding_firmware_idle_ns=idle,host_inter_submission_ns=host_gap,
            host_wait_ns=[s['host_ns'] for s in ss],drm_bracket_ns=[s['drm_time'][1]-s['drm_time'][0] for s in ss],
            quarter_medians_ns=quarters,late_median_ns=quarters[-1],host_gap_median_ns=st.median(host_gap),
            observed_train_duty=sum(ns)/(ss[-1]['fw_ts'][1]-ss[0]['fw_ts'][0]),probe_start_fw=windows[-1][0])
        report['records'][path.name]=entry;dispatches+=k+2
        if n==131072:cells.setdefault((c,gap),[]).append(entry);codes[c]=p['code']
    windows.sort();assert all(x[1]<=y[0] for x,y in zip(windows,windows[1:]))
    assert len(boots)==1 and dispatches==2394 and len(descriptors)==2
    report['chronological_records']=[x[2] for x in windows]
    with tempfile.TemporaryDirectory() as tmp:
        for c,code in codes.items():report['models'][str(c)]=A.prediction(code,131072,128,Path(tmp))
    for (c,gap),trials in sorted(cells.items()):
        assert len(trials)==6 and len({t['program_sha256'] for t in trials})==1
        late=[t['late_median_ns'] for t in trials]
        report['cells'][f'{c}:{gap}']=dict(trial_late_medians_ns=late,median_trial_late_ns=st.median(late),
            trial_late_max_to_min_ratio=max(late)/min(late),minimum_trial_late_ns=min(late),maximum_trial_late_ns=max(late),
            host_gap_median_ns=st.median([v for t in trials for v in t['host_inter_submission_ns']]),
            observed_train_duty_median=st.median([t['observed_train_duty'] for t in trials]))
    report['recorded_functional_sha256']=RECORDED_FUNCTIONAL_SHA256
    report.update(trains=39,dispatches=2394,timed_dispatches=2316,final_train_buffers_exact=39,control_buffers_exact=78,
        fault_events=0,own_probe_windows_nonoverlapping=True,intermediate_buffers_captured=False,calibration_changed=False)
    assert report['functional_binary_sha256']==sha(S.P.cov.RUN) and report['native_binary_sha256']==sha(exe)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 39 trains / 2394 dispatches, every final buffer and 78 controls exact, zero faults')
    print('PASS actual delay configuration, every timestamp bracket, measured host delays, source/binary bindings and disjoint windows')
    for cell,e in report['cells'].items():print('CELL',cell,e)


if __name__=='__main__':main()
