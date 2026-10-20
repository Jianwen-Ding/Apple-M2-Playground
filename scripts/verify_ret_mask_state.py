#!/usr/bin/env python3
"""Independent checks of return-arrival r0 and incoming-depth transformations."""
import gzip
import hashlib
import json
from pathlib import Path

import probe_ret_prepop as R
import probe_ret_levels as L
from verify_probe_sources import require_source


def shallow(table,target,control=False):
    result=table.copy();result[64:96]=[0xfeed0001]*32
    one,two={'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002),'C':(0xc3300001,0xc3300002)}[target]
    result[96:128]=[one if control or not table[32+i] else 0xcdcdcdcd for i in range(32)]
    result[128:160]=[two]*32
    result[224:256]=[0 if bool(table[32+i])==control else 0xcdcdcdcd for i in range(32)]
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def level_trace(table,original=False):
    result=table.copy();result[64:96]=[0xface0001]*32
    counters=(table[:32] if original else [2 if d==0 else 0 if d==1 else d for d in table[:32]])
    for phase in range(5):
        result[(3+phase)*32:(4+phase)*32]=[0 if d<=phase else 0xcdcdcdcd for d in counters]
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def common(rec,p,builder,*,ac_online='1'):
    assert rec['phase']=='finished' and not rec.get('halted') and rec['recovery_control_passed']
    assert rec['before']['budget_used']==rec['after']['budget_used']==0
    assert rec['before']['boot_id']==rec['after']['boot_id']
    assert rec['before']['ac_online']==rec['after']['ac_online']==ac_online
    assert rec['code']==p['code'].hex() and rec['control_code']==p['control'].hex()
    assert rec['table_in']==p['table']
    require_source(builder.__file__,rec['gate']['builder_sha256'])
    assert rec['harness_sha256']==hashlib.sha256((R.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
    for phase in ('control_before','variant','control_after'):
        v=rec[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
        s=v['samples'];assert len(s)==1 and s[0]['wait']==s[0]['errno']==0
        assert 0<s[0]['fw_ts'][0]<s[0]['fw_ts'][1]


def main():
    names={f'ret-prepop-k{k}-{w}-s{seed}.json.gz' for k in (0,1,5,8,16,24) for w in ('A','B','C') for seed in (103,809)}
    paths=sorted(R.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];p=R.build(g['first'],g['winner'],g['seed'])
        common(rec,p,R);require_source(R.R.__file__,g['base_builder_sha256'])
        for phase in ('control_before','variant','control_after'):
            want=shallow(p['table'],g['winner']) if phase=='variant' else shallow(p['table'],'A',control=True)
            assert (rec[phase]['out'],rec[phase]['table_after'])==want,(path.name,phase)
        assert rec['prepop_analysis']['writers']==[i for i,x in enumerate(p['table'][32:64]) if not x]
        assert set(rec['prepop_analysis']['values'].values())=={0}
        with R.E.measured_model():prediction=R.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==(rec['variant']['out'],rec['variant']['table_after'])
    names={f'ret-levels-{m}-r{rot}-hswap-{kind}.json.gz' for m in range(5) for rot in (0,1) for kind in ('actual','surrogate')}
    names.add('ret-levels-3-r0-actual.json.gz')
    paths=sorted(L.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate']
        p=L.build(g['maximum'],g['rotate'],g['known_surrogate'],g.get('desired_model','decrement'))
        common(rec,p,L)
        for phase in ('control_before','variant','control_after'):
            want=level_trace(p['table']) if phase=='variant' else level_trace(p['table'],original=True)
            assert (rec[phase]['out'],rec[phase]['table_after'])==want,(path.name,phase)
        with R.E.measured_model():prediction=R.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        mismatch=prediction!=(rec['variant']['out'],rec['variant']['table_after'])
        assert not mismatch
    print('PASS 36 shallow cases: only originally inactive lanes run before pop and read r0l=0')
    print('PASS 21 depth cases including ten hardware-tested known-op state surrogates and a full-group repeat')
    print('PASS nonempty ret map through incoming depth 4: 0 -> 2, 1 -> 0, deeper unchanged')
    print('PASS 57 variants / 171 dispatches: all words/guards/controls exact, no faults; all measured-model replays exact; original rejected hypotheses retained')


if __name__=='__main__':main()
