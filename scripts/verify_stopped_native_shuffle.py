#!/usr/bin/env python3
"""Independently verify native relative/xor/rotate shuffles after partial stop."""
import gzip
import json
import probe_stopped_native_shuffle as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def source(kind,lane,offset):
    target={'down':lane+offset,'up':lane-offset,'xor':lane^offset,'rotate_up':(lane-offset)%32}[kind]
    return target if 0<=target<32 else lane


def expected(table,kind,offset,stop):
    tab=table.copy();tab[32:64]=[0xd1100001]*32;ds=table[:32]
    for lane,d in enumerate(ds):
        target=source(kind,lane,offset)
        if d==0:tab[64+lane]=tab[96+lane]=target
        if d==1 or not stop and d==0:
            value=lane if stop and ds[target]==0 else target
            tab[128+lane]=tab[160+lane]=value
        if not stop or d:tab[192+lane]=0xd1100002
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'stopped-native-{k}-{d}-r{r}-o{o}.json.gz' for k in B.KINDS for d in (1,3) for r in (0,1) for o in B.OFFSETS}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    mismatches={k:0 for k in B.KINDS}
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];p=B.build(g['maximum'],g['rotate'],g['kind'],g['offset'])
        common(rec,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        for phase in ('control_before','variant','control_after'):
            assert (rec[phase]['out'],rec[phase]['table_after'])==expected(p['table'],g['kind'],g['offset'],phase=='variant'),(path.name,phase)
        a=rec['native_analysis'];assert a['self_fallback_exact'] and a['immediate_equals_register']
        gap=any(d==1 and p['table'][source(g['kind'],lane,g['offset'])]==0 for lane,d in enumerate(p['table'][:32]))
        assert a['legacy_exact']==(not gap)
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==(rec['variant']['out'],rec['variant']['table_after'])
        mismatches[g['kind']]+=gap
    print('PASS 160 variants / 480 dispatches: down/up/xor/rotate-up, immediate/register forms, ten boundary offsets, two depths and rotations')
    print('PASS stopped sources self-fallback; living masked sources readable; exact words/guards/controls, zero faults')
    print('PASS all current model replays exact; original counterexamples by kind:',mismatches)


if __name__=='__main__':main()
