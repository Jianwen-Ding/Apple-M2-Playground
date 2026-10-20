#!/usr/bin/env python3
"""Independently verify per-call reserve accounting and direct depth-5 reads."""
import gzip
import json
import probe_call_mask_reserve as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,g):
    result=table.copy();ol,il=g['outer_link'],g['inner_link'];total=g['outer_reserve']+g['inner_reserve']
    target=0x2000+B.P.drm.control_main()[1]+B.B.N.CALLEES[g['winner']]
    for lane,operand in enumerate(table[:32]):
        admitted=lane>=g['first'];entered=admitted and operand==target
        final_link=ol if admitted or total==0 else lane
        values={1:0xe1100001,16:0xe2200001,17:final_link}
        if admitted:values.update({2:ol,3:0xe1100002})
        if entered:values.update({4:il,5:{'A':0xa1100011,'B':0xb2200011,'C':0xc3300011}[g['winner']]})
        if not entered and (admitted or total==0):values.update({6:0,7:0,18:0 if total==0 else total+1})
        if admitted or total==0:values.update({8:0,9:il if admitted else lane,10:ol})
        if not admitted and total==2:values.update({13:0,14:0})
        if admitted or total<4:values.update({11:0xe1100003,12:final_link})
        for plane,value in values.items():result[plane*32+lane]=value
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'call-reserve-{o}-k{k}-{w}-s{s}-r{a}{b}.json.gz' for o in ('direct','indirect') for k in (1,5,16,24) for w in B.B.N.CALLEES for s in (17,257) for a in (0,2) for b in (0,2)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['outer_kind'],g['first'],g['winner'],g['seed'],g['outer_reserve'],g['inner_reserve'])
        common(r,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        assert p['table'][480:512]==[int(i>=g['first']) for i in range(32)]
        assert g['outer_link']==0x2000+g['outer_pc']+(6 if g['outer_kind']=='direct' else 2)
        assert g['inner_link']==0x2000+g['inner_pc']+2
        want=expected(p['table'],g)
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        total=g['outer_reserve']+g['inner_reserve'];a=r['reserve_analysis']
        assert a['exact'] and a['masked_counter_values']==[0 if total==0 else 1+total]
        assert a['caller_writers']==list(range(g['first'],32) if total==4 else range(32))
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(r['variant']['out'],r['variant']['table_after'])
    print('PASS balanced push_exec 2 before each call / pop_exec 2 after return preserves original caller mask')
    print('PASS either missing reserve allows excluded lanes at caller; direct masked counter reads 0/3/5 separate the cases')
    print('PASS 192 variants / 576 dispatches: exact controls, link formulas, final full-group markers, guards and replay, zero faults')


if __name__=='__main__':main()
