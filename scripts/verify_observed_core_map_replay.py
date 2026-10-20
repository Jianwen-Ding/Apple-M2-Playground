#!/usr/bin/env python3
"""Host-only replay of recorded M2 core maps, with historical/default regression."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import probe_integer_geometry_cost as G
import verify_integer_core_distribution as V
from integer_recorded_model import RECORDED_FUNCTIONAL_SHA256

ROOT=G.S.ROOT
DATA=ROOT/'results/2026-10-20-observed-core-map-replay'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def literal(n,c,a,sr):
    out=[0xcdcdcdcd]*(n+16)+[0xa5a50000+j for j in range(16)]
    arith=[v for j in range(c) for v in [100+7*j+a//c]*n]
    return out,arith+[64 if sr==19 else 0]*n+[0xcdcdcdcd]*16


def execute(r,binary,cores=None):
    n,wg=r['n'],r['wg'];words=n+32;table=r['table_in']
    out_va=G.P.cov.SIM_DATA_VA+0x8000
    table_off=max(1<<20,(0x8000+words*4+16383)//16384*16384)
    tab_va=G.P.cov.SIM_DATA_VA+table_off
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder);(d/'code').write_bytes(bytes.fromhex(r['code'])+bytes(16))
        (d/'out').write_bytes(struct.pack(f'<{words}I',*([0xcdcdcdcd]*(words-16)+[0xa5a50000+j for j in range(16)])))
        (d/'table').write_bytes(struct.pack(f'<{len(table)}I',*table))
        args=[str(binary),str(d/'code'),'--grid',f'{n},1,1','--wg',f'{wg},1,1','--regs','64','--shared','0']
        for u in ('4=0',f'5={n}',f'6={out_va&0xffffffff}',f'7={out_va>>32}',f'8={tab_va&0xffffffff}',f'9={tab_va>>32}'):
            args+=['--uniform',u]
        args+=['--map',f'{out_va:#x}={d/"out"}','--map',f'{tab_va:#x}={d/"table"}',
            '--dump',f'{out_va:#x}={4*words}:{d/"out-after"}','--dump',f'{tab_va:#x}={4*len(table)}:{d/"table-after"}',
            '--alloc-regs','64','--vm-slot','0','--pipeline','4096']
        if cores is not None:
            (d/'cores.json').write_text(json.dumps(cores));args+=['--m2-core-map',str(d/'cores.json')]
        v=subprocess.run(args,capture_output=True,text=True,timeout=120)
        assert v.returncode==0,v.stdout+v.stderr
        stats=json.loads(v.stdout)
        if cores is None:assert 'core_map' not in stats and 'mapped_workgroups' not in stats
        else:assert stats['core_map']=='m2' and stats['mapped_workgroups']==len(cores)
        raw_out=(d/'out-after').read_bytes();raw_table=(d/'table-after').read_bytes()
        assert len(raw_out)==words*4 and len(raw_table)==len(table)*4
        outputs=list(struct.unpack(f'<{words}I',raw_out)),list(struct.unpack(f'<{len(table)}I',raw_table))
        return outputs,stats,hashlib.sha256(raw_out+raw_table).hexdigest()


def invalid_cli_checks(binary):
    with tempfile.TemporaryDirectory() as folder:
        d=Path(folder);(d/'code').write_bytes(b'\x00');(d/'preamble').write_bytes(b'\x00')
        good=[0,1,2,3,4,5,6,7,16,17,18,19]
        mixed=good.copy();mixed[1]=16
        disabled=good.copy();disabled[0]=25
        cases=[('length',good[:-1]),('disabled',disabled),('mixed',mixed),('negative',[-1]),('object',{})]
        for name,value in cases:
            (d/'map.json').write_text(json.dumps(value));(d/'dump').write_bytes(b'unchanged')
            v=subprocess.run([str(binary),str(d/'code'),'--grid','1536','--wg','128',
                '--m2-core-map',str(d/'map.json'),'--preamble',str(d/'preamble'),
                '--alloc','4096=4','--dump',f'4096=4:{d/"dump"}'],capture_output=True,text=True)
            assert v.returncode!=0 and 'M2 core map' in v.stdout and 'preamble:' not in v.stdout,(name,v.stdout)
            assert (d/'dump').read_bytes()==b'unchanged'
        return len(cases)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--result',type=Path);args=ap.parse_args()
    baseline_path=G.DATA/'analysis.json';baseline=json.loads(baseline_path.read_text())
    version_path=DATA/'recorded-model.json';version=json.loads(version_path.read_text())
    old=Path(version['archived_binary']);new=G.P.cov.RUN
    assert version['geometry_analysis_sha256']==sha(baseline_path)
    assert version['recorded_functional_sha256']==sha(old)==baseline['functional_binary_sha256']==RECORDED_FUNCTIONAL_SHA256
    assert sha(new)!=sha(old),'new replay model was not built'
    invalid=invalid_cli_checks(new);G.P.cov.install()
    report=dict(utc=datetime.now(timezone.utc).isoformat(),records={},defaults={},
        recorded_model_sha256=sha(old),replay_model_sha256=sha(new),recorded_model_metadata_sha256=sha(version_path),
        geometry_analysis_sha256=sha(baseline_path),verifier_sha256=sha(Path(__file__)),buffer_checker_sha256=sha(Path(V.__file__)),
        model_sources={n:sha(G.S.ROOT.parent/'AGX-Performance-Simulator'/n) for n in ('rust/src/func.rs','rust/src/bin/agx_run.rs')})
    names=set(baseline['records']);paths=sorted(G.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    defaults={};replays=0;controls=0
    for path in paths:
        assert sha(path)==baseline['records'][path.name]['sha256']
        r=json.load(gzip.open(path));b=r['gate']['base_gate'];n,c,a,wg,sr=r['n'],b['chains'],b['adds'],r['wg'],b['selector']
        assert r['simulator_sha256']==RECORDED_FUNCTIONAL_SHA256 and r['phase']=='finished' and not r.get('halted')
        code,_,_=G.C.construct(n,c,a,sr);control,_,_=G.C.construct(n,c,0,19)
        assert r['code']==code.hex() and r['control_code']==control.hex()
        V.independent_buffers(r['train'],n,c,a,wg,sr)
        for name in ('control_before','control_after'):
            assert r[name]['ok'];V.independent_buffers(r[name],n,c,0,wg,19);controls+=1
        key=f'{n}:{wg}:{c}:{a}:{sr}'
        if key not in defaults:
            before,old_stats,old_digest=execute(r,old)
            after,new_stats,new_digest=execute(r,new)
            assert before==after==literal(n,c,a,sr) and old_stats==new_stats and old_digest==new_digest
            defaults[key]=new_stats
            report['defaults'][key]=dict(readback_sha256=new_digest,stats=new_stats)
            print('DEFAULT EXACT',key,flush=True)
        entry=dict(sha256=sha(path),default_case=key,arithmetic_and_guards_exact=True)
        if sr==20:
            cores=r['train']['table_after'][n*c:-16:wg]
            outputs,stats,digest=execute(r,new,cores)
            assert outputs==(r['train']['out'],r['train']['table_after'])
            assert {k:v for k,v in stats.items() if k not in ('core_map','mapped_workgroups')}==defaults[key]
            entry.update(literal_full_readback_exact=True,readback_sha256=digest,
                core_map_sha256=hashlib.sha256(json.dumps(cores,separators=(',',':')).encode()).hexdigest(),workgroups=len(cores))
            replays+=1;print('OBSERVED MAP EXACT',path.name,flush=True)
        else:entry['literal_full_readback_exact']=True
        report['records'][path.name]=entry
    assert len(defaults)==64 and replays==80 and controls==320
    assert report['replay_model_sha256']==sha(new) and report['recorded_model_sha256']==sha(old)
    report.update(records_checked=160,observed_maps_replayed=80,default_cases_unchanged=64,recovery_buffers_checked=320,
        invalid_cli_cases=invalid,hardware_submissions=0,placement_is_supplied_not_predicted=True)
    if args.result:args.result.write_text(json.dumps(report,indent=1,sort_keys=True)+'\n')
    print('PASS 80 observed core maps reproduce complete hardware buffers exactly; 64 defaults match historical model and independent oracles')
    print('PASS 160 raw records / 320 exact controls, five CLI failures before execution/dumps, separate recorded/replay fingerprints; no GPU access')


if __name__=='__main__':main()
