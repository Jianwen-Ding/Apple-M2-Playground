#!/usr/bin/env python3
"""Independently check three-target nested calls, link scopes and pop checkpoints."""
import gzip
import json
import probe_nested_divergent as B
from verify_ret_mask_state import common


def expected(table,g):
    result=table.copy();ol,il=g['outer_link'],g['inner_link']
    target=0x2000+B.P.drm.control_main()[1]+B.CALLEES[g['winner']]
    for lane,operand in enumerate(table[:32]):
        same=operand==target
        values={1:0xe1100001,2:ol,3:0xe1100002,8:0,9:il,10:ol,11:0xe1100003,12:ol}
        if same:values.update({4:il,5:{'A':0xa1100011,'B':0xb2200011,'C':0xc3300011}[g['winner']]})
        else:values.update({6:0,7:0})
        for plane,value in values.items():result[plane*32+lane]=value
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'nested-divergent-{o}-{w}-s{s}.json.gz' for o in ('direct','indirect') for w in B.CALLEES for s in (17,257)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['outer_kind'],g['winner'],g['seed'])
        common(r,p,B)
        assert g['outer_link']==0x2000+g['outer_pc']+(6 if g['outer_kind']=='direct' else 2)
        assert g['inner_link']==0x2000+g['inner_pc']+2
        assert len(set(p['table'][:32]))==3 and p['table'][0]==0x2000+B.P.drm.control_main()[1]+B.CALLEES[g['winner']]
        want=expected(p['table'],g)
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        assert r['nested_analysis']['exact']
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(r['variant']['out'],r['variant']['table_after'])
    print('PASS nested direct/indirect outer calls with three-way divergent inner calls, complete saved/restored links and pre-pop traces')
    print('PASS 12 variants / 36 dispatches: all words/guards/known-op controls exact, zero faults; all model replays exact')


if __name__=='__main__':main()
