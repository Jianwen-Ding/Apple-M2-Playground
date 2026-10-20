#!/usr/bin/env python3
"""Offline geometry, arithmetic, core-map and cluster-packet evidence checks."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics as st
import subprocess
import tempfile
import probe_integer_geometry_cost as G
import verify_integer_core_distribution as V
import verify_integer_chain_cost as A


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def packets(table,n,c,wg):
    clusters=[v>>4 for v in table[n*c:-16:wg]]
    mixed={str(q):sum(len(set(clusters[j:j+q]))>1 for j in range(0,len(clusters),q)) for q in (1,2,4,8,16,32,64,128)}
    return dict(workgroups=len(clusters),mixed_aligned_blocks=mixed,
        largest_unmixed_tested_width=max(int(q) for q,v in mixed.items() if v==0),
        hypothesis_1024_thread_packet_wgs=1024//wg,
        hypothesis_mixed_blocks=mixed[str(1024//wg)])


def prediction(code,n,wg,directory,peak=None):
    path=directory/'shader.bin';path.write_bytes(code)
    args=[str(A.MODEL),str(path),'--grid',str(n),'--wg',str(wg),'--regs','64','--clock','1398']
    if peak is not None:args+=['--busiest-core-wgs',str(peak)]
    for u in ('4=0',f'5={n}','6=1048576','7=0','8=2097152','9=0'):args+=['--uniform',u]
    v=subprocess.run(args,capture_output=True,text=True,timeout=60);assert v.returncode==0,v.stderr
    p=json.loads(v.stdout);assert p['warnings']==[] and p['paths']=='cost-emulation'
    if peak is not None:assert p['busiest_core_wgs']==p['busiest_core_wgs_input']==peak
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    names={f'integer-core-s{sr}-n{n}-w{wg}-c{c}-a{a}-k64-t{t}.json.gz'
        for n,wg in G.GEOMETRIES for c in (1,8) for a in (1024,4096) for sr in (19,20) for t in range(3)}
    names|=set(G.pilot_names());paths=sorted(G.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    G.configure();exe=G.S.native();previous=G.S.ROOT/'results/2026-10-20-integer-core-distribution/analysis.json'
    old=json.loads(previous.read_text())
    assert old['native_binary_sha256']==sha(exe) and old['native_source_sha256']==sha(G.S.NATIVE)
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},paired={},placement_sensitivity={},cluster_packets={},
        builder_sha256=sha(Path(G.__file__)),core_runner_sha256=sha(Path(G.C.__file__)),verifier_helpers_sha256=sha(Path(V.__file__)),
        sr_encoder_sha256=sha(Path(G.P.bench.get_sr.__code__.co_filename)),native_source_sha256=sha(G.S.NATIVE),native_binary_sha256=sha(exe),
        functional_binary_sha256=sha(G.P.cov.RUN),dispatch_binary_sha256=sha(A.MODEL),previous_analysis_sha256=sha(previous),
        arithmetic_builder_sha256=sha(Path(G.C.I.__file__)),train_runner_sha256=sha(Path(G.C.T.__file__)),shared_runner_sha256=sha(Path(G.C.H.__file__)),
        model_sources={n:sha(A.SIM/n) for n in ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/bin/agx_dispatch.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameters={n:sha(A.SIM/n) for n in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    prepared={};cells={};codes={};boots=set();windows=[];dispatches=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];b=g['base_gate'];n,c,a,wg,k,sr=r['n'],b['chains'],b['adds'],r['wg'],g['repeats'],b['selector']
        key=n,c,a,wg,k,sr
        if key not in prepared:prepared[key]=G.build(*key)
        p=prepared[key];assert g==json.loads(json.dumps(p['gate']))
        assert r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert r['native_binary_sha256']==report['native_binary_sha256'] and r['simulator_sha256']==report['functional_binary_sha256']
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
            checked=V.independent_buffers(v,n,c,a if phase=='train' else 0,wg,sr if phase=='train' else 19)
            if phase=='train':assert checked==r['final_buffer_checks']
            for s in ss:assert s['wait']==s['errno']==0 and s['drm_time'][0]<=s['fw_ts'][0]<s['fw_ts'][1]<=s['drm_time'][1]
        ss=r['train']['samples'];all_samples=r['control_before']['samples']+ss+r['control_after']['samples']
        assert all(x['fw_ts'][1]<=y['fw_ts'][0] for x,y in zip(all_samples,all_samples[1:]))
        windows.append((all_samples[0]['fw_ts'][0],all_samples[-1]['fw_ts'][1],path.name))
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in ss];host=[y['drm_time'][0]-x['drm_time'][1] for x,y in zip(ss,ss[1:])]
        assert all(t>=1000000 for t in host);q=k//4
        entry=dict(sha256=sha(path),firmware_ns=ns,host_inter_submission_ns=host,
            quarter_medians_ns=[st.median(ns[j:j+q]) for j in range(0,k,q)],final_buffer_checks=r['final_buffer_checks'],probe_start_fw=windows[-1][0])
        if sr==20:entry['cluster_packets']=packets(r['train']['table_after'],n,c,wg)
        report['records'][path.name]=entry;dispatches+=k+2
        if k==64:cells.setdefault((n,wg,c,a,sr),[]).append(entry);codes[n,wg,c,a,sr]=p['code']
    windows.sort();assert all(x[1]<=y[0] for x,y in zip(windows,windows[1:]))
    assert len(boots)==1 and dispatches==9600;report['chronological_records']=[x[2] for x in windows]
    cache={}
    with tempfile.TemporaryDirectory() as tmp:
        for (n,wg,c,a,sr),trials in sorted(cells.items()):
            assert len(trials)==3;code=codes[n,wg,c,a,sr];model=prediction(code,n,wg,Path(tmp))
            late=[v for t in trials for v in t['firmware_ns'][-16:]];medians=[t['quarter_medians_ns'][-1] for t in trials]
            cell=f'{n}:{wg}:{c}:{a}:{sr}'
            report['cells'][cell]=dict(late_median_ns=st.median(late),trial_late_medians_ns=medians,
                trial_late_max_to_min_ratio=max(medians)/min(medians),model=model,model_ns=1000*model['time_us'])
            if sr==20:
                per_trial=[]
                for t in trials:
                    peak=t['final_buffer_checks']['maximum_workgroups_on_used_core'];pk=n,wg,c,a,peak
                    if pk not in cache:cache[pk]=prediction(code,n,wg,Path(tmp),peak)
                    pred=cache[pk]
                    per_trial.append(dict(core_map=t['final_buffer_checks'],cluster_packets=t['cluster_packets'],last_dispatch_ns=t['firmware_ns'][-1],
                        model_with_observed_peak=pred,peak_to_default_model_ratio=pred['time_us']/model['time_us'],
                        last_dispatch_to_peak_model_ratio=t['firmware_ns'][-1]/(1000*pred['time_us'])))
                report['placement_sensitivity'][cell]=per_trial
    for n,wg in G.GEOMETRIES:
        packet_rows=[t for (rn,rw,c,a,sr),trials in cells.items() if rn==n and rw==wg and sr==20 for t in trials]
        totals=[v for t in packet_rows for v in t['final_buffer_checks']['workgroups_per_cluster'].values()]
        report['cluster_packets'][f'{n}:{wg}']=dict(records=len(packet_rows),
            cluster_total_gcd=math.gcd(*totals),cluster_totals=sorted(set(totals)),
            observed_largest_unmixed_widths=sorted({t['cluster_packets']['largest_unmixed_tested_width'] for t in packet_rows}),
            hypothesis_mixed_blocks=sum(t['cluster_packets']['hypothesis_mixed_blocks'] for t in packet_rows))
        for c in (1,8):
            for a in (1024,4096):
                tag,core=[report['cells'][f'{n}:{wg}:{c}:{a}:{sr}'] for sr in (19,20)]
                report['paired'][f'{n}:{wg}:{c}:{a}']=dict(sr20_to_sr19_late_ratio=core['late_median_ns']/tag['late_median_ns'])
    report.update(trains=160,dispatches=9600,timed_dispatches=9280,arithmetic_and_guards_exact=160,
        literal_final_buffers_exact=80,core_property_buffers_valid=80,recovery_controls_exact=320,fault_events=0,
        own_probe_windows_nonoverlapping=True,intermediate_buffers_captured=False,calibration_changed=False)
    assert report['functional_binary_sha256']==sha(G.P.cov.RUN) and report['dispatch_binary_sha256']==sha(A.MODEL)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 160 trains / 9600 dispatches: exact arithmetic/guards, 80 exact SR19 buffers, 80 valid SR20 maps, 320 exact controls, zero faults')
    print('PACKETS',report['cluster_packets'])


if __name__=='__main__':main()
