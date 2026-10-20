#!/usr/bin/env python3
"""Verify paired immediate/register source-liveness probes against scalar lane sets."""
import gzip
import json
import probe_stopped_shuffle_index as B
from verify_ret_mask_state import common


def expected(table,index,stop):
    tab=table.copy();tab[32:64]=[0xd1100001]*32;ds=table[:32]
    for writer,d in enumerate(ds):
        if d==0:
            tab[64+writer]=index;tab[96+writer]=index
        if d==1 or not stop and d==0:
            selected=writer if stop and ds[index]==0 else index
            tab[128+writer]=selected;tab[160+writer]=selected
        if not stop or d!=0:tab[192+writer]=0xd1100002
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'stopped-shuffle-index-{d}-r{r}-i{i}.json.gz' for d in range(1,5) for r in (0,1) for i in range(32)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    counterexamples=0;source_depths={}
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['maximum'],g['rotate'],g['index'])
        common(r,p,B)
        pc=g['stop_pc'];assert p['code'][:pc]==p['control'][:pc] and p['code'][pc+2:]==p['control'][pc+2:]
        assert p['code'][pc:pc+2]==bytes.fromhex('8800') and p['control'][pc:pc+2]==bytes.fromhex('3800')
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==expected(p['table'],g['index'],phase=='variant'),(path.name,phase)
        a=r['index_analysis'];source=p['table'][g['index']]
        assert a['self_fallback_exact'] and a['immediate_equals_register'] and a['source_depth']==source
        assert a['legacy_exact']==(source!=0)
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        mismatch=pred!=(r['variant']['out'],r['variant']['table_after'])
        assert mismatch==(source==0)
        counterexamples+=mismatch;source_depths[source]=source_depths.get(source,0)+1
    assert counterexamples==82
    print('PASS 256 variants / 768 dispatches: all 32 indices, four depth patterns, two rotations, paired immediate/register forms')
    print('PASS stopped sources return own value; masked living sources remain readable; source-depth counts:',source_depths)
    print('PASS all words/guards/controls exact, zero faults; 82 simulator source-liveness counterexamples retained')


if __name__=='__main__':main()
