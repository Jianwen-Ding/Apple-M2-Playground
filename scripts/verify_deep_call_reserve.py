#!/usr/bin/env python3
"""Independent per-frame counter/link/participation checks for balanced calls."""
import gzip
import json
import probe_deep_call_reserve as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,g):
    d=g['depth'];result=table.copy();links=g['links'];target=0x2000+B.P.drm.control_main()[1]+B.target_offsets(d)[g['winner']]
    caller,full,final=3+8*d,4+8*d,5+8*d
    for lane,operand in enumerate(table[:32]):
        admitted=lane>=g['first'];leaf=admitted and operand==target
        result[64+lane]=0xe3300001
        result[full*32+lane]=0xe3300003
        result[final*32+lane]=links[0] if admitted else lane
        if not admitted:continue
        result[caller*32+lane]=0xe3300002
        for j in range(d):
            base=3+8*j
            if j<d-1 or leaf:
                result[base*32+lane]=links[j]
                result[(base+1)*32+lane]=3+2*j
                result[(base+2)*32+lane]=(0xe3301000+j) if j<d-1 else {'A':0xa1100011,'B':0xb2200011,'C':0xc3300011}[g['winner']]
            if j==d-1 and not leaf:
                result[(base+3)*32+lane]=1+2*d
                result[(base+4)*32+lane]=0xe3302000+j
            result[(base+5)*32+lane]=0xe3303000+j
            result[(base+6)*32+lane]=links[j]
            result[(base+7)*32+lane]=1+2*j
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'deep-reserve-d{d}-{p}-k{k}-{w}-s{s}.json.gz' for d in (3,4,8) for p in (B.KINDS if d==3 else ('alternating','reverse')) for k in (1,5,16,24) for w in ('A','B','C') for s in (17,257)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['depth'],g['pattern'],g['first'],g['winner'],g['seed'])
        common(r,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        assert p['table'][32:64]==[int(i>=g['first']) for i in range(32)] and g['all_saved_links_initialized']
        assert g['links']==[0x2000+pc+(6 if kind=='direct' else 2) for pc,kind in zip(g['call_pcs'],g['call_kinds'])]
        want=expected(p['table'],g)
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        a=r['deep_analysis'];assert a['exact']
        assert a['entry_counter_values']==[[3+2*j] for j in range(g['depth'])]
        assert a['restored_counter_values']==[[1+2*j] for j in range(g['depth'])]
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(r['variant']['out'],r['variant']['table_after'])
    print('PASS balanced masks and saved links through 3/4/8 calls, mixed forms and divergent three-way leaf')
    print('PASS direct initialized masked-counter reads at odd depths 3..17 and matching two-count restoration per call')
    print('PASS 192 variants / 576 dispatches: every per-frame word, caller mask, original excluded r1 IDs, guards and controls exact, zero faults')


if __name__=='__main__':main()
