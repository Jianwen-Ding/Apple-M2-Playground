#!/usr/bin/env python3
"""Independent checks of outer return before inner reconvergence."""
import gzip
import json
import probe_nested_early_return as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,g):
    tab=table.copy();ol,il=g['outer_link'],g['inner_link']
    target=0x2000+B.P.drm.control_main()[1]+B.B.CALLEES[g['winner']]
    for lane,operand in enumerate(table[:32]):
        matching=operand==target
        values={1:0xe1100001,2:ol,3:0xe1100002,11:0xe1100003,12:il if matching else ol}
        if matching:
            values.update({4:il,5:{'A':0xa1100011,'B':0xb2200011,'C':0xc3300011}[g['winner']]})
            if g['inner_pops']==1:values.update({13:0,14:0})
        else:values.update({6:0,7:0,8:0,9:il,10:ol})
        for plane,value in values.items():tab[32*plane+lane]=value
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'nested-early-{o}-{w}-s{s}-p{p}.json.gz' for o in ('direct','indirect') for w in B.B.CALLEES for s in (17,257) for p in (0,1)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['outer_kind'],g['winner'],g['seed'],g['inner_pops'])
        common(r,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        assert g['outer_link']==0x2000+g['outer_pc']+(6 if g['outer_kind']=='direct' else 2)
        assert g['inner_link']==0x2000+g['inner_pc']+2
        want=expected(p['table'],g)
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        assert r['early_analysis']['exact']
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(r['variant']['out'],r['variant']['table_after'])
    print('PASS outer RET with one inner pop immediately reactivates inner participants; zero-pop return leaves them masked')
    print('PASS r1 restoration follows issuing lanes: inner participants retain inner links in final r1')
    print('PASS 24 variants / 72 dispatches: exact full words/guards/no-call controls, zero faults; all model replays exact')


if __name__=='__main__':main()
