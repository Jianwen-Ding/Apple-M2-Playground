#!/usr/bin/env python3
"""Check scattered-mask hardware traces independently of the probe oracle."""
import gzip
import hashlib
import json
from pathlib import Path

import probe_sparse_control as S
import verify_call_winner as C
from verify_probe_sources import require_source


def ret_expected(table,landing,jump=False):
    tab=table.copy();tab[64:96]=[0xfeed0001]*32
    one,two={'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002)}[landing]
    tab[96:128]=[one if jump or not table[32+i] else 0xcdcdcdcd for i in range(32)]
    tab[128:160]=[two]*32;tab[192:224]=[0]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'sparse-{kind}-k{k}-{w}-s{seed}.json.gz' for kind in ('ret','call')
           for k in range(1,32) for w in ('A','B') for seed in (211,701)}
    paths=sorted(S.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names,'missing/extra sparse cases'
    unsupported=0
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate']
        kind,k,w,seed=g['sparse_kind'],g['first'],g['winner'],g['sparse_seed']
        p=S.build(kind,k,w,seed)
        assert rec['phase']=='finished' and not rec.get('halted') and rec['recovery_control_passed']
        assert rec['before']['budget_used']==rec['after']['budget_used']==0
        assert rec['before']['boot_id']==rec['after']['boot_id']
        assert rec['before']['ac_online']==rec['after']['ac_online']=='1'
        assert rec['code']==p['code'].hex() and rec['control_code']==p['control'].hex()
        assert rec['table_in']==p['table']
        assert g['sparse_mask']==S.mask_for(k,seed)
        assert g['sparse_mask']&((1<<k)-1)==0 and g['sparse_mask']&(1<<k)
        if k<30:assert not g['sparse_mask']&(1<<(k+1))
        require_source(S.__file__,g['builder_sha256'])
        base=S.R if kind=='ret' else S.L
        require_source(base.__file__,g['base_builder_sha256'])
        assert g['surrogates']==p['gate']['surrogates']
        assert g['sparse_actual_gate'].get('uniform_active_case_exact') if kind=='ret' and k==31 else g['sparse_actual_gate'].get('unsupported_as_expected')
        assert g['sparse_surrogates_exact']
        assert rec['harness_sha256']==hashlib.sha256((S.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
        unsupported+=bool(g['sparse_actual_gate'].get('unsupported_as_expected'))
        for phase in ('control_before','variant','control_after'):
            v=rec[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            s=v['samples'];assert len(s)==1 and s[0]['wait']==s[0]['errno']==0
            assert 0<s[0]['fw_ts'][0]<s[0]['fw_ts'][1]
            if kind=='ret':
                want=ret_expected(p['table'],w) if phase=='variant' else ret_expected(p['table'],'A',jump=True)
            else:
                want=(C.expected(p['table'],w,g['link'],post_link=True) if phase=='variant'
                      else C.expected(p['table'],'B',g['link'],post_link=True,jump=True))
            assert (v['out'],v['table_after'])==want,(path.name,phase)
        assert rec['sparse_analysis']['oracle_exact']
    assert unsupported==244
    print('PASS 248 variants / 744 dispatches: call and ret, every first-active position 1..31, swapped targets, two seeded masks')
    print('PASS inactive holes: ret pop-1 membership, call entry partition, all-active call link write and inactive r1 preservation')
    print('PASS exact programs/inputs, all surrogate paths, guards/tails and recovery controls; zero recorded faults')
    print('PASS all 248 actual programs now replay exactly; 244 original rejections retain recorded source provenance')


if __name__=='__main__':main()
