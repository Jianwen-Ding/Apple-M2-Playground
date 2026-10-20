#!/usr/bin/env python3
"""Independently verify excluded outer lanes and initialized return operands."""
import gzip
import json
import probe_nested_partial_outer as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,g):
    tab=table.copy();ol,il=g['outer_link'],g['inner_link'];pops=g['inner_pops']
    target=0x2000+B.P.drm.control_main()[1]+B.N.CALLEES[g['winner']]
    for lane,operand in enumerate(table[:32]):
        admitted=lane>=g['first'];entered=admitted and operand==target
        values={1:0xe1100001,11:0xe1100003,12:il if entered and pops<2 else ol}
        if admitted:values.update({2:ol,3:0xe1100002})
        if entered:values.update({4:il,5:{'A':0xa1100011,'B':0xb2200011,'C':0xc3300011}[g['winner']]})
        else:values.update({6:0,7:0})
        if not entered or pops==2:values.update({8:0,9:il if admitted else lane,10:ol})
        if entered and pops==1:values.update({13:0,14:0})
        for plane,value in values.items():tab[plane*32+lane]=value
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'nested-partial-{o}-k{k}-{w}-s{s}-p{p}.json.gz' for o in ('direct','indirect') for k in (1,5,16,24) for w in B.N.CALLEES for s in (17,257) for p in (0,1,2)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['outer_kind'],g['first'],g['winner'],g['seed'],g['inner_pops'])
        common(r,p,B);require_source(B.N.__file__,g['base_builder_sha256'])
        assert g['all_saved_links_initialized']
        assert p['table'][480:512]==[int(i>=g['first']) for i in range(32)]
        assert p['table'][g['first']]==0x2000+B.P.drm.control_main()[1]+B.N.CALLEES[g['winner']]
        assert g['outer_link']==0x2000+g['outer_pc']+(6 if g['outer_kind']=='direct' else 2)
        assert g['inner_link']==0x2000+g['inner_pc']+2
        want=expected(p['table'],g)
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        assert r['partial_analysis']['exact']
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(r['variant']['out'],r['variant']['table_after'])
    print('PASS originally excluded outer lanes reactivate at inner return and retain original IDs in r1 until restoration')
    print('PASS 144 variants / 432 dispatches: four suffix starts, two outer forms, three winners, two seeds, three pop counts')
    print('PASS initialized in-program saved links; all words/guards/controls/replay exact, zero faults')


if __name__=='__main__':main()
