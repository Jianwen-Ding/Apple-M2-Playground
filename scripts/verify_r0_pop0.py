#!/usr/bin/env python3
"""Independently verify zero-count synchronization, with controls lacking pop0."""
import gzip
import json
import probe_r0_pop0 as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table):
    tab=table.copy();tab[32:64]=[0xf1100001]*32;tab[64:96]=table[:32]
    tab[96:128]=[0 if d==0 else 0xcdcdcdcd for d in table[:32]]
    tab[128:160]=[0xf1100002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def count_zero(code):
    pc=0;n=0
    while pc<len(code):
        info=B.P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        n+=info[2]=='pop_exec r0l, 0';pc+=info[1]
    assert pc==len(code)
    return n


def main():
    cases=[(op,m,r,False) for op in B.B.OPS[:3] for m in (1,3,31) for r in (0,1)]
    cases += [(op,m,0,True) for op in B.B.OPS for m in (1,2,3,31)]
    names={f'r0-pop0-{op}-m{m}-r{r}-'+('uniform' if u else 'mixed')+'.json.gz' for op,m,r,u in cases}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['op'],g['maximum'],g['rotate'],g['uniform'])
        common(r,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        assert count_zero(p['code'])==1 and count_zero(p['control'])==0
        want=expected(p['table'])
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        a=r['zero_pop_analysis'];assert a['sync_exact'] and not a['skip_exact']
        assert a['checkpoint_writers']==[list(range(32)),[i for i,d in enumerate(p['table'][:32]) if d==0]]
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==(r['variant']['out'],r['variant']['table_after'])
    print('PASS pop_exec 0 synchronizes execution to written zero counters; it is not a skipped no-op')
    print('PASS controls contain no zero-count pop; uniform nonzero inputs become empty until the bounded drain')
    print('PASS 34 variants / 102 dispatches: every word/guard/control and replay exact, zero faults')


if __name__=='__main__':main()
