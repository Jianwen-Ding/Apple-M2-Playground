#!/usr/bin/env python3
"""Host-only supplied-map cost checks: independent partitions/footprints and unchanged legacy predictions."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import statistics
import struct
import subprocess
import tempfile
import verify_observed_core_map_replay as R

ROOT = R.ROOT
SIM = ROOT.parent / 'AGX-Performance-Simulator'
MODEL = SIM / 'rust/target/release/agx_dispatch'
OLD_SHA = '6c7b860e32e6734102cd77147cd58f37cbbe1fb8788313ad366a37f4452a0720'
OLD = Path('/scratch/apple-m2-playground/model-versions') / OLD_SHA / 'agx_dispatch'
DATA = ROOT / 'results/2026-10-20-observed-core-map-cost'


def invoke(binary, args):
    r = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def launch(r, directory, mapped=False):
    n, wg = r['n'], r['wg']
    (directory/'code').write_bytes(bytes.fromhex(r['code'])+bytes(16))
    args = [str(directory/'code'), '--grid', str(n), '--wg', str(wg), '--regs', '64', '--clock', '1398']
    for u in ('4=0', f'5={n}', '6=1048576', '7=0', '8=2097152', '9=0'):
        args += ['--uniform', u]
    if mapped:
        c = r['gate']['base_gate']['chains']
        cores = r['train']['table_after'][n*c:-16:wg]
        (directory/'cores.json').write_text(json.dumps(cores))
        (directory/'table').write_bytes(struct.pack(f'<{len(r["table_in"])}I', *r['table_in']))
        args += ['--m2-core-map', str(directory/'cores.json'), '--map', f'2097152={directory/"table"}',
                 '--alloc', f'1048576={(n+32)*4}']
    return args


def check_partitions(pred, cores, wg):
    assert pred['core_map'] == 'm2' and pred['paths'] == 'functional' and pred['warnings'] == []
    assert pred['mapped_workgroups'] == pred['workgroups'] == len(cores)
    assert pred['active_cores'] == len(set(cores))
    assert pred['busiest_core_wgs'] == max(Counter(cores).values())
    assert pred['waves_exhaustive'] and pred['wave_order_assumption'] == 'linear-workgroup-id'
    assert pred['memory_assumption'] == 'isolated-workgroup-snapshots'
    assert pred['slot_assumption'] == 'group-index-within-workgroup'
    expected = {core:[i for i,c in enumerate(cores) if c == core] for core in sorted(set(cores))}
    assert [c['id'] for c in pred['cores']] == list(expected)
    gpw = (wg+31)//32
    resident = min(96, 2*(3328//(2*64)), 55 if wg <= 32 else 84 if wg <= 64 else 96) // gpw
    assert pred['wgs_per_core'] == resident
    for c in pred['cores']:
        wgs = expected[c['id']]
        assert c['workgroups'] == wgs
        chunks = [wgs[i:i+resident] for i in range(0,len(wgs),resident)]
        assert [w['workgroups'] for w in c['waves']] == chunks
        assert [w['index'] for w in c['waves']] == list(range(len(chunks)))
        assert c['core_cycles'] == sum(w['cycles'] for w in c['waves'])
        launch_us = max(len(wgs)*100, len(wgs)*gpw*13.6)/1000
        assert abs(c['launch_core_us']-launch_us) < 1e-10
        assert abs(c['completion_us']-max(c['core_cycles']/1398,launch_us)) < 1e-10
    critical = max(pred['cores'], key=lambda c:c['completion_us'])
    assert pred['critical_core'] == critical['id']
    assert pred['waves'] == len(critical['waves'])
    assert pred['core_cycles'] == critical['core_cycles']
    assert abs(pred['time_us']-(critical['completion_us']+pred['launch_us'])) < 1e-10
    assert sorted(i for c in pred['cores'] for w in c['waves'] for i in w['workgroups']) == list(range(len(cores)))


def invalid_cli(directory):
    good = [0,1,2,3,4,5,6,7,16,17,18,19]
    disabled = good.copy(); disabled[0] = 25
    mixed = good.copy(); mixed[0] = 16
    cases = [('length',good[:-1],[]),('disabled',disabled,[]),('mixed',mixed,[]),('negative',[-1],[]),
             ('object',{},[]),('peak',good,['--busiest-core-wgs','2']),
             ('max-waves',good,['--max-waves','2']),('profile',good,['--cores','37'])]
    for name, value, extra in cases:
        (directory/'invalid.json').write_text(json.dumps(value))
        args = [str(directory/'missing-shader'),'--grid','1536','--wg','128','--m2-core-map',str(directory/'invalid.json'),
                '--preamble',str(directory/'missing-preamble'),'--map',f'4096={directory/"missing-buffer"}',*extra]
        r = subprocess.run([str(MODEL),*args], capture_output=True, text=True, timeout=10)
        assert r.returncode != 0 and 'M2 core map' in r.stderr and 'missing-shader:' not in r.stderr,(name,r.stderr)
    (directory/'stop').write_bytes(bytes.fromhex('8800'))
    batch = []
    for core in [0,25,16]:
        path = directory/f'batch-{core}.json';path.write_text(json.dumps([core]))
        batch.append([str(directory/'stop'),'--grid','32','--m2-core-map',str(path)])
    (directory/'batch').write_text(''.join(json.dumps(row)+'\n' for row in batch))
    r = subprocess.run([str(MODEL),'--batch',str(directory/'batch')],capture_output=True,text=True,timeout=30)
    rows = [json.loads(row) for row in r.stdout.splitlines()]
    assert r.returncode == 1 and len(rows) == 3
    assert rows[0]['critical_core'] == 0 and 'disabled' in rows[1]['error'] and rows[2]['critical_core'] == 16
    return dict(invalid_cases=len(cases),batch_jobs=3,batch_order_and_error_isolation=True)


def address_fixture(directory):
    fixture = json.loads((ROOT/'results/2026-10-20-observed-core-map-tracing/analysis.json').read_text())
    (directory/'fixture').write_bytes(bytes.fromhex(fixture['shader_hex']))
    n, wg = 80*32, 32
    cores = [1 if i%4 == 0 else 0 for i in range(80)]
    (directory/'fixture-map').write_text(json.dumps(cores))
    (directory/'stride').write_bytes(struct.pack('<I',n))
    args = [str(directory/'fixture'),'--grid',str(n),'--wg',str(wg),'--m2-core-map',str(directory/'fixture-map'),
            '--uniform','8=4096','--uniform','9=0','--uniform','10=0','--uniform','11=16',
            '--alloc',f'4096={n*8}','--map',f'{1<<36}={directory/"stride"}']
    pred = invoke(MODEL,args);check_partitions(pred,cores,wg)
    assert pred['global_device_segments'] == 161 and pred['device_footprint_complete']
    for core in pred['cores']:
        for wave in core['waves']:
            assert abs(wave['sharing']-1/(2*len(wave['workgroups'])+1)) < 1e-12
    return pred


def main():
    ap = argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    baseline_path = R.G.DATA/'analysis.json';baseline = json.loads(baseline_path.read_text())
    assert R.sha(OLD) == OLD_SHA
    sources = [Path(__file__),*sorted((SIM/'rust/src').rglob('*.rs')),SIM/'rust/Cargo.toml',SIM/'rust/Cargo.lock',
               SIM/'results/2026-10-11-instruction-bench/bench.json.gz',SIM/'results/2026-10-11-cost-model/calibration.json']
    hashes = {str(p.relative_to(ROOT.parent)):R.sha(p) for p in sources}
    report = dict(utc=datetime.now(timezone.utc).isoformat(),model_sha256=R.sha(MODEL),archived_model_sha256=OLD_SHA,
        sources=hashes,geometry_analysis_sha256=R.sha(baseline_path),records={},legacy_cases={},hardware_submissions=0,
        model_assumptions_not_observed_schedule=True)
    paths = sorted(R.G.DATA.glob('*.json.gz'));assert {p.name for p in paths} == set(baseline['records'])
    R.G.P.cov.install();seen=set();mapped=0;controls=0
    with tempfile.TemporaryDirectory() as folder:
        directory=Path(folder)
        report['cli_checks']=invalid_cli(directory)
        report['address_fixture']=address_fixture(directory)
        for path in paths:
            assert R.sha(path) == baseline['records'][path.name]['sha256']
            r=json.load(gzip.open(path));b=r['gate']['base_gate']
            n,wg,c,a,sr=r['n'],r['wg'],b['chains'],b['adds'],b['selector']
            assert r['simulator_sha256']==R.RECORDED_FUNCTIONAL_SHA256 and r['phase']=='finished' and not r.get('halted')
            code,_,_=R.G.C.construct(n,c,a,sr);control,_,_=R.G.C.construct(n,c,0,19)
            assert r['code']==code.hex() and r['control_code']==control.hex()
            R.V.independent_buffers(r['train'],n,c,a,wg,sr)
            for name in ('control_before','control_after'):
                assert r[name]['ok'];R.V.independent_buffers(r[name],n,c,0,wg,19);controls+=1
            key=f'{n}:{wg}:{c}:{a}:{sr}'
            if key not in seen:
                default=launch(r,directory)
                peak=(n//wg+37)//38
                for mode,extra in [('default',[]),('peak',['--busiest-core-wgs',str(peak)])]:
                    old=invoke(OLD,default+extra);new=invoke(MODEL,default+extra)
                    assert new==old,(key,mode,old,new)
                    report['legacy_cases'][key+':'+mode]=new
                seen.add(key);print('LEGACY EXACT',key,flush=True)
            entry=dict(sha256=R.sha(path))
            if sr==20:
                cores=r['train']['table_after'][n*c:-16:wg]
                pred=invoke(MODEL,launch(r,directory,True));check_partitions(pred,cores,wg)
                # Each chain and tag plane writes one word per global lane;
                # all planes and workgroups are disjoint and 64-byte aligned.
                assert pred['global_device_segments']==n*(c+1)//16
                assert pred['device_footprint_complete'] and pred['resident_slc_assumed']
                assert all(w['sharing']==0 for core in pred['cores'] for w in core['waves'])
                last=r['train']['samples'][-1]['fw_ts'];ns=last[1]-last[0]
                entry.update(prediction=pred,last_dispatch_ns=ns,last_dispatch_model_ratio=ns/(pred['time_us']*1000))
                mapped+=1;print('MAPPED COST EXACT PARTITIONS',path.name,flush=True)
            report['records'][path.name]=entry
            if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    assert len(seen)==64 and mapped==80 and controls==320
    assert report['model_sha256']==R.sha(MODEL)
    assert hashes=={str(p.relative_to(ROOT.parent)):R.sha(p) for p in sources}
    fixed=[e['last_dispatch_model_ratio'] for name,e in report['records'].items()
           if 'prediction' in e and '-n131072-' in name]
    report.update(observed_maps_checked=mapped,raw_records_checked=len(paths),control_buffers_checked=controls,
        legacy_predictions_unchanged=len(report['legacy_cases']),fixed_grid_last_dispatch_ratio_range=[min(fixed),max(fixed)],
        fixed_grid_last_dispatch_ratio_median=statistics.median(fixed),phase='finished')
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 80 maps: all workgroups assigned once to the correct core/wave, exact footprints and sharing; 128 legacy predictions unchanged')
    print('FIXED GRID LAST-DISPATCH RATIOS',report['fixed_grid_last_dispatch_ratio_range'],report['fixed_grid_last_dispatch_ratio_median'])


if __name__=='__main__':main()
