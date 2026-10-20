#!/usr/bin/env python3
"""Check call r1's fallthrough and implicit-link write from complete records."""
import gzip
import hashlib
import json
from pathlib import Path

import probe_call_r1 as R
import probe_call_r1_link as L
import probe_call_r1_mask as M
import verify_call_winner as C
from verify_probe_sources import require_source


def fall(table,link,snapshot=False,writes_link=True,prepop=False):
    tab=table.copy();tab[64:96]=[0xfeed0001]*32;tab[192:224]=[0xfa110001]*32
    if prepop:
        tab[96:128]=[0xc1000001 if table[32+i] else 0xcdcdcdcd for i in range(32)]
    if snapshot:
        tab[224:256]=[link if writes_link and table[32+i] else table[i] for i in range(32)]
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'call-r1-k{k}-B-r0.json.gz' for k in (0,1)}
    names|={f'call-r1-link-k{k}-{w}-r0.json.gz' for k in (0,1,2,17,31) for w in ('A','B')}
    names.add('call-r1-link-k1-B-r1.json.gz')
    names|={f'call-r1-mask-k{k}-{w}-r0.json.gz' for k in (0,1,17,31) for w in ('A','B')}
    names.add('call-r1-mask-k1-B-r1.json.gz')
    paths=sorted(R.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names,'missing/extra alias records'
    known_link_surrogates=0
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];k,w=g['first'],g['winner']
        prepop=bool(g.get('prepop_checkpoint'))
        snapshot=bool(g.get('fallback_r1_snapshot'));builder=M if prepop else L if snapshot else R
        p=builder.build(k,w)
        assert rec['phase']=='finished' and not rec.get('halted') and rec['recovery_control_passed']
        assert rec['before']['budget_used']==rec['after']['budget_used']==0
        assert rec['before']['boot_id']==rec['after']['boot_id']
        assert rec['before']['ac_online']==rec['after']['ac_online']=='1'
        assert rec['code']==p['code'].hex() and rec['control_code']==p['control'].hex()
        assert rec['table_in']==p['table']
        require_source(builder.__file__,g['builder_sha256'])
        require_source(R.C.__file__,g['base_builder_sha256'])
        if snapshot:require_source(R.__file__,g['parent_builder_sha256'])
        if prepop:require_source(L.__file__,g['parent_snapshot_builder_sha256'])
        assert rec['harness_sha256']==hashlib.sha256((R.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
        code=bytes.fromhex(rec['code']);at=g['call_pc']
        assert code[at:at+2]==bytes.fromhex('0402')
        assert R.P.cov.ASMB.info(code[at:at+16])[2]=='call r1'
        for phase in ('control_before','variant','control_after'):
            v=rec[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            s=v['samples'];assert len(s)==1 and s[0]['wait']==s[0]['errno']==0
            assert 0<s[0]['fw_ts'][0]<s[0]['fw_ts'][1]
            if phase=='variant':want=fall(p['table'],g['link'],snapshot=snapshot,prepop=prepop)
            elif snapshot:want=fall(p['table'],g['link'],snapshot=True,writes_link=False,prepop=prepop)
            else:want=C.expected(p['table'],'B',g['link'],jump=True)
            assert (v['out'],v['table_after'])==want,(path.name,phase)
        with R.E.measured_model():
            prediction=R.P.cov.simulate(code,32,32,64,0,p['table'])
        assert prediction==(rec['variant']['out'],rec['variant']['table_after']),'measured alias model differs from hardware'
        if prepop:
            assert rec['alias_analysis']['exact'] and rec['alias_analysis']['prepop_lanes']==list(range(k,32))
        elif snapshot:
            assert rec['alias_analysis']['matches_link_fallthrough'] and not rec['alias_analysis']['matches_noop']
        elif not snapshot:assert not rec['alias_analysis']['exact']
        if 'link_fall_surrogate_code' in g:
            with R.E.measured_model():
                result=R.P.cov.simulate(bytes.fromhex(g['link_fall_surrogate_code']),32,32,64,0,p['table'])
            assert result==fall(p['table'],g['link'],snapshot=True,prepop=prepop)
            known_link_surrogates+=1
    assert known_link_surrogates==18
    print('PASS 22 variants / 66 dispatches: call r1 falls through; no callee entry, complete guards and controls exact')
    print('PASS 20 fallback snapshots: issue-active r1 becomes the link; inactive r1 retains the initialized target')
    print('PASS no-call controls validate copies; 18 refined link-write/fallthrough surrogates validate the observed hypothesis')
    print('PASS nine pre-pop checkpoints: original issue-active lanes remain active before reconvergence')
    print('PASS all 22 original alias cases now replay exactly; legacy counterexample provenance retained')


if __name__=='__main__':main()
