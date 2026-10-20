#!/usr/bin/env python3
"""Independent complete-buffer checks for three-address call/return evidence."""
import gzip
import hashlib
import json
from pathlib import Path

import probe_three_targets as R


def expected(kind,table,target,link,control=False):
    result=table.copy();result[64:96]=[0xfeed0001]*32
    one,two={'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002),'C':(0xc3300001,0xc3300002)}[target]
    site=R.P.drm.control_main()[1]
    addr=0x2000+site+{'A':1024,'B':1536,'C':2048}[target]
    active={i for i in range(32) if table[32+i]}
    matching={i for i in active if table[i]==addr}
    if kind=='call':
        result[96:128]=[one if i in matching else 0xcdcdcdcd for i in range(32)]
        result[128:160]=[link if i in matching else 0xcdcdcdcd for i in range(32)]
        result[160:192]=[two]*32
        result[224:256]=[link if control or i in active else 0xf1f10000 for i in range(32)]
    else:
        result[96:128]=[one if control or i not in active else 0xcdcdcdcd for i in range(32)]
        result[128:160]=[two]*32
        result[224:256]=[0xf1f10000]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'targets3-{kind}-k{k}-{w}-s{seed}.json.gz' for kind in ('call','ret')
           for k in (0,1,5,8,16,24) for w in ('A','B','C') for seed in (103,809)}
    paths=sorted(R.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names,'missing/extra records'
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];kind,k,w,seed=g['kind'],g['first'],g['winner'],g['seed']
        p=R.build(kind,k,w,seed)
        assert rec['phase']=='finished' and not rec.get('halted') and rec['recovery_control_passed']
        assert rec['before']['budget_used']==rec['after']['budget_used']==0
        assert rec['before']['boot_id']==rec['after']['boot_id']
        assert rec['before']['ac_online']==rec['after']['ac_online']=='1'
        assert rec['code']==p['code'].hex() and rec['control_code']==p['control'].hex()
        assert rec['table_in']==p['table']
        active=[i for i in range(32) if p['table'][32+i]]
        assert min(active)==k and {p['table'][i] for i in active}==set(g['targets'].values())
        assert p['table'][k]==g['targets'][w] and not p['table'][32+k+1]
        assert len(g['targets'])==3 and g['all_three_targets_active'] and g['actual_model_exact']
        assert g['builder_sha256']==hashlib.sha256(Path(R.__file__).read_bytes()).hexdigest()
        assert rec['harness_sha256']==hashlib.sha256((R.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
        assert g['surrogates']==p['gate']['surrogates']
        for phase in ('control_before','variant','control_after'):
            v=rec[phase];assert v['ok'] and v['returncode']==0 and not v.get('host_timeout')
            s=v['samples'];assert len(s)==1 and s[0]['wait']==s[0]['errno']==0
            assert 0<s[0]['fw_ts'][0]<s[0]['fw_ts'][1]
            params=next(json.loads(line)['params'] for line in v['stdout'].splitlines() if '"params"' in line)
            assert (params['gen'],params['variant'],params['rev'])==(14,'C',17)
            want=expected(kind,p['table'],w,g['link']) if phase=='variant' else expected(kind,p['table'],'A',g['link'],control=True)
            assert (v['out'],v['table_after'])==want,(path.name,phase)
        assert rec['three_target_analysis']['exact']
    print('PASS 72 variants / 216 dispatches: all three addresses live, both transfer kinds, six first-active positions, all target assignments, two seeds')
    print('PASS exact actual-program gates and every uniform/jump path; all input, trace, link, r1, guard and tail words exact')
    print('PASS lowest-active winner, call partition/global links and return pop membership/r1 preservation; no faults, all recovery controls pass')


if __name__=='__main__':main()
