#!/usr/bin/env python3
"""Check retained arithmetic results and compare chain-shape timing to the model.

No GPU access. Complete hardware buffers are checked independently; the model
uses saved shader bytes. Timing residuals remain visible, without recalibration.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st
import subprocess
import tempfile
import probe_integer_chain_cost as B

SIM=B.ROOT.parent/'AGX-Performance-Simulator'
MODEL=SIM/'rust/target/release/agx_dispatch'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(n,chains,adds):
    outputs=[0xcdcdcdcd]*(n+16)+[0xa5a50000+i for i in range(16)]
    final=[]
    for chain in range(chains):
        value=100+7*chain
        for j in range(chain,adds,chains):value+=3
        final.extend([value]*n)
    return outputs,final+[0xcdcdcdcd]*16


def prediction(code,n,wg,directory):
    path=directory/'shader.bin';path.write_bytes(code)
    args=[str(MODEL),str(path),'--grid',str(n),'--wg',str(wg),'--regs','64','--clock','1398']
    for uniform in ('4=0',f'5={n}','6=1048576','7=0','8=2097152','9=0'):args+=['--uniform',uniform]
    run=subprocess.run(args,capture_output=True,text=True,timeout=60);assert run.returncode==0,run.stderr
    result=json.loads(run.stdout);assert not result['warnings'] and result['paths']=='cost-emulation'
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    wanted={f'integer-chain-n131072-w128-c{c}-a{a}-r{r}.json.gz' for c in (1,2,4,8) for a in (64,256,1024,2048) for r in range(5)}
    wanted|={'integer-chain-n32-w32-c1-a64-r0.json.gz','integer-chain-n32768-w128-c1-a1024-r0.json.gz','integer-chain-n32768-w128-c8-a1024-r0.json.gz'}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==wanted
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},cells={},slopes={},dispatch_model_sha256=sha(MODEL),
        functional_model_sha256=sha(B.P.cov.RUN),source_sha256={name:sha(SIM/name) for name in
        ('rust/src/cost.rs','rust/src/dispatch.rs','rust/src/func.rs','rust/src/fsem.rs','rust/src/isa/compiled.rs','rust/src/isa/exec.rs')},
        parameter_sha256={name:sha(SIM/name) for name in ('results/2026-10-11-instruction-bench/bench.json.gz','results/2026-10-11-cost-model/calibration.json')})
    cache={};cells={};codes={};boots=set()
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];key=(r['n'],g['chains'],g['adds'],r['wg'])
        if key not in cache:cache[key]=B.build(*key)
        p=cache[key]
        assert r['code']==p['code'].hex() and r['control_code']==p['control'].hex() and r['table_in']==p['table']
        assert g['builder_sha256']==sha(Path(B.__file__))
        assert r['harness_sha256']==sha(B.P.bench.REPO/'tests/drm_compute.c')
        assert r['phase']=='finished' and not r.get('halted') and r['recovery_control_passed'] and r['arithmetic_exact']
        assert r['before']['budget_used']==r['after']['budget_used']==0
        assert r['before']['boot_id']==r['after']['boot_id'];boots.add(r['before']['boot_id'])
        assert r['before']['ac_online']==r['after']['ac_online']=='1'
        for phase in ('control_before','variant','control_after'):
            v=r[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            samples=v['samples'];assert len(samples)==1 and samples[0]['wait']==samples[0]['errno']==0
            assert 0<samples[0]['fw_ts'][0]<samples[0]['fw_ts'][1]
            assert (v['out'],v['table_after'])==scalar(r['n'],g['chains'],g['adds'] if phase=='variant' else 0),(path.name,phase)
        if r['n']==131072:
            cell=(g['chains'],g['adds']);cells.setdefault(cell,[]).append(dict(record=path.name,ns=r['variant']['fw_ns'],
                control_before_ns=r['control_before']['fw_ns'],control_after_ns=r['control_after']['fw_ns']))
            codes[cell]=p['code']
        report['records'][path.name]=sha(path)
    assert len(boots)==1
    with tempfile.TemporaryDirectory() as tmp:
        directory=Path(tmp)
        for (chains,adds),samples in sorted(cells.items()):
            assert len(samples)==5
            low=min(x['ns'] for x in samples);fast=[x for x in samples if x['ns']<=1.05*low]
            model=prediction(codes[chains,adds],131072,128,directory)
            report['cells'][f'{chains}:{adds}']=dict(minimum_ns=low,median_ns=st.median(x['ns'] for x in samples),
                maximum_ns=max(x['ns'] for x in samples),fast_cluster_count=len(fast),
                fast_cluster_median_ns=st.median(x['ns'] for x in fast),samples=samples,
                model_ns=1000*model['time_us'],model=model,shader_bytes=len(codes[chains,adds]))
    for chains in (1,2,4,8):
        slopes={}
        for lo,hi in ((256,1024),(1024,2048)):
            a,b=(report['cells'][f'{chains}:{n}'] for n in (lo,hi))
            hardware=(b['fast_cluster_median_ns']-a['fast_cluster_median_ns'])/(hi-lo)
            model=(b['model_ns']-a['model_ns'])/(hi-lo)
            slopes[f'{lo}:{hi}']=dict(hardware_ns_per_extra_add=hardware,model_ns_per_extra_add=model,ratio=hardware/model)
        report['slopes'][str(chains)]=slopes
    assert report['dispatch_model_sha256']==sha(MODEL) and report['functional_model_sha256']==sha(B.P.cov.RUN)
    report.update(cases=83,dispatches=249,all_results_exact=True,ac_online='1',faults=0,
        timing_note='Slopes use candidate fast-cluster medians; bracketing controls verify correctness but their timing is not a matched launch baseline.',
        calibration_changed=False)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 83 programs / 249 dispatches: all main/table words, guards, provenance, AC/boot/recovery checks exact, zero faults')
    print('PASS 16 timing cells, five interleaved samples each; current model predictions retain all residuals')
    for chains,slopes in report['slopes'].items():
        print('CHAINS',chains,slopes)


if __name__=='__main__':main()
