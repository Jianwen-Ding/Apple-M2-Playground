#!/usr/bin/env python3
"""Verify terminated index-bit exclusion with independently derived lane outputs."""
import gzip
import json
import probe_dead_index_or as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,seed,index,stop,retained=False):
    tab=table.copy();tab[32:64]=[0xd1100001]*32;ds=table[:32]
    for lane,d in enumerate(ds):
        if d==0:tab[64+lane]=tab[96+lane]=seed
        if d==1 or not stop and d==0:
            tab[128+lane]=lane if stop and ds[index]==0 else index
            selected=index if not stop or not retained else (index//4*4+((index|seed)&3))
            tab[160+lane]=lane if stop and ds[selected]==0 else selected
        if not stop or d:tab[192+lane]=0xd1100002
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'dead-index-or-r{r}-s{s}-i{i}.json.gz' for r in (0,1) for s in range(4) for i in range(32)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    decisive=0;counterexamples=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['rotate'],g['seed'],g['index'])
        common(r,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==expected(p['table'],g['seed'],g['index'],phase=='variant'),(path.name,phase)
        a=r['index_or_analysis'];assert a['ignored_dead_bits'] and a['immediate_equals_register']
        distinction=expected(p['table'],g['seed'],g['index'],True)!=expected(p['table'],g['seed'],g['index'],True,True)
        assert a['retained_dead_bits']==(not distinction);decisive+=distinction
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        counterexamples+=pred!=(r['variant']['out'],r['variant']['table_after'])
    assert decisive>0 and counterexamples>0
    print(f'PASS 256 variants / 768 dispatches: dead lanes do not contribute low index bits; {decisive} distinguish retained bits')
    print(f'PASS all words/guards/controls exact, zero faults; {counterexamples} legacy simulator counterexamples retained')


if __name__=='__main__':main()
