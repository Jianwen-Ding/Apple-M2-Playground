#!/usr/bin/env python3
"""Exact independent entry/link/mask oracles for retained indirect-call probes."""
import gzip
import hashlib
import json
from pathlib import Path

import probe_call_winner as C
import probe_call_link_scope as L


def expected(table,landing,link,post_link=False,jump=False):
    tab=table.copy();tab[64:96]=[0xfeed0001]*32
    one,two={'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002)}[landing]
    addr=0x2000+C.P.drm.control_main()[1]+{'A':1024,'B':1536}[landing]
    entered=[bool(table[32+i]) and table[i]==addr for i in range(32)]
    tab[96:128]=[one if entered[i] else 0xcdcdcdcd for i in range(32)]
    tab[128:160]=[link if entered[i] else 0xcdcdcdcd for i in range(32)]
    tab[160:192]=[two]*32
    tab[224:256]=([link if jump or table[32+i] else 0xf1f10000 for i in range(32)] if post_link else [0]*32)
    out=[0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)]
    return out,tab


def main():
    names={f'call-winner-k{k}-{w}-r0.json.gz' for k in range(32) for w in ('A','B')}
    names|={f'call-winner-k1-{w}-r1.json.gz' for w in ('A','B')}
    links=((0,'B',0),(1,'B',0),(1,'A',0),(2,'B',0),(17,'A',0),(17,'B',0),(31,'B',0),(1,'B',1))
    names|={f'call-link-k{k}-{w}-r{r}.json.gz' for k,w,r in links}
    paths=sorted(C.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names,'missing/extra records'
    unsupported=0
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];k,w=g['first'],g['winner']
        link_scope='plane7' in g
        builder=L if link_scope else C
        p=builder.build(k,w)
        assert rec['phase']=='finished' and not rec.get('halted') and rec['recovery_control_passed']
        assert rec['before']['budget_used']==rec['after']['budget_used']==0
        assert rec['before']['boot_id']==rec['after']['boot_id']
        assert rec['before']['ac_online']==rec['after']['ac_online']=='1'
        assert rec['code']==p['code'].hex() and rec['control_code']==p['control'].hex()
        assert rec['table_in']==p['table'] and g['link']==p['gate']['link']
        assert g['builder_sha256']==hashlib.sha256(Path(builder.__file__).read_bytes()).hexdigest()
        if link_scope:assert g['base_builder_sha256']==hashlib.sha256(Path(C.__file__).read_bytes()).hexdigest()
        assert rec['harness_sha256']==hashlib.sha256((C.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
        assert g['surrogates']==p['gate']['surrogates'] and g['actual_gate']==p['gate']['actual_gate']
        unsupported+=bool(g['actual_gate'].get('unsupported_as_expected'))
        for phase in ('control_before','variant','control_after'):
            v=rec[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            s=v['samples'];assert len(s)==1 and s[0]['wait']==s[0]['errno']==0
            assert 0<s[0]['fw_ts'][0]<s[0]['fw_ts'][1]
            if phase=='variant':want=expected(p['table'],w,g['link'],post_link=link_scope)
            else:want=expected(p['table'],'B',g['link'],post_link=link_scope,jump=True)
            assert (v['out'],v['table_after'])==want,(path.name,phase)
        if link_scope:
            assert rec['link_analysis']['link_lanes']==list(range(k,32))
            assert rec['link_analysis']['initial_lanes']==list(range(k))
            # The old matched-lanes-only hypothesis coincides only at k=31.
            assert rec['link_analysis']['matches_partition_oracle']==(k==31)
        else:assert rec['winner_analysis']=={'A':w=='A','B':w=='B','fall':False}
    assert unsupported==71
    print('PASS 66 winner variants: every first-active lane 0..31, swapped targets, k=1 repeats')
    print('PASS 8 post-pop r1 variants: link written in all issue-active lanes; inactive prefix preserved')
    print('PASS 74 variants / 222 dispatches: complete inputs, guarded readbacks, entry/link/mask traces and recovery controls')
    print('PASS all filtered uniform-call and forced-jump gates; 71 actual variants explicitly unsupported, lane-0-active link counterexample retained')


if __name__=='__main__':main()
