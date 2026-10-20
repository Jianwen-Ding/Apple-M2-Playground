#!/usr/bin/env python3
"""Independently verify low-index OR liveness in four native shuffle forms."""
import gzip
import json
import probe_native_dead_index_or as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def selected(kind,lane,offset,low=None):
    raw={'down':lane+offset,'up':lane-offset,'xor':lane^offset,'rotate_up':(lane-offset)%32}[kind]
    if raw<0 or raw>=32:return lane
    if low is None:return raw
    within={'down':(lane+low)&3,'up':(lane-low)&3,'xor':(lane^low)&3,'rotate_up':(lane-low)&3}[kind]
    return raw//4*4+within


def expected(table,kind,seed,index,stop,retained=False,fallback=True):
    tab=table.copy();tab[32:64]=[0xd1100001]*32;ds=table[:32]
    for lane,d in enumerate(ds):
        if d==0:
            before=selected(kind,lane,seed);tab[64+lane]=tab[96+lane]=before
        if d==1 or not stop and d==0:
            for bank in range(2):
                low=(seed|index)&3 if bank and stop and retained else None
                target=selected(kind,lane,index,low)
                value=lane if stop and fallback and ds[target]==0 else target
                tab[128+32*bank+lane]=value
        if not stop or d:tab[192+lane]=0xd1100002
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'native-dead-or-{k}-r{r}-s{s}-i{i}.json.gz' for k in B.N.KINDS for r in (0,1) for s in range(4) for i in B.N.OFFSETS}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    decisive={k:0 for k in B.N.KINDS};gaps=decisive.copy()
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['rotate'],g['seed'],g['index'],g['kind'])
        common(r,p,B);require_source(B.D.__file__,g['base_builder_sha256']);require_source(B.N.__file__,g['native_builder_sha256'])
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==expected(p['table'],g['kind'],g['seed'],g['index'],phase=='variant'),(path.name,phase)
        a=r['native_or_analysis'];assert a['ignored_dead_bits'] and a['immediate_equals_register']
        retained=expected(p['table'],g['kind'],g['seed'],g['index'],True,True)
        got=r['variant']['out'],r['variant']['table_after']
        different=got!=retained;assert a['retained_dead_bits']==(not different);decisive[g['kind']]+=different
        old=expected(p['table'],g['kind'],g['seed'],g['index'],True,True,False)
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==old;gaps[g['kind']]+=prediction!=got
    assert all(n>0 for n in decisive.values()) and all(n>0 for n in gaps.values())
    print('PASS 320 variants / 960 dispatches: four native forms, all low seeds, ten boundary offsets, both alternating stop masks')
    print('PASS stopped index bits excluded; all words/guards/controls exact, zero faults')
    print('PASS decisive index-OR cases by kind:',decisive)
    print('PASS original simulator counterexamples by kind:',gaps)


if __name__=='__main__':main()
