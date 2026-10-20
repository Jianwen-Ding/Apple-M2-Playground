#!/usr/bin/env python3
"""Independently verify empty-issued RET state and bounded fallthrough."""
import gzip
import json
import probe_empty_ret_state as B
from verify_ret_mask_state import common


def expected(table, known):
    depths=table[:32]
    if known:depths=[0 if d==1 else d for d in depths]
    result=table.copy()
    result[64:96]=[0xface0001]*32
    for phase in range(5):
        result[(3+phase)*32:(4+phase)*32]=[0 if d<=phase else 0xcdcdcdcd for d in depths]
    result[256:288]=[0xfa110001]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'empty-ret-{m}-r{r}-{kind}.json.gz' for m in range(1,5) for r in (0,1) for kind in ('actual','surrogate')}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate']
        p=B.build(g['maximum'],g['rotate'],g['known_surrogate']);common(rec,p,B)
        assert all(d>0 for d in p['table'][:32])
        for phase in ('control_before','variant','control_after'):
            want=expected(p['table'],phase=='variant' and g['known_surrogate'])
            assert (rec[phase]['out'],rec[phase]['table_after'])==want,(path.name,phase)
        model='swap-fall' if g['known_surrogate'] else 'legacy-fall'
        assert rec['empty_ret_analysis']['models'][model]
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==(rec['variant']['out'],rec['variant']['table_after'])
    print('PASS 16 variants / 48 dispatches: empty-issued RET falls through with unchanged pop thresholds through depth 4')
    print('PASS eight known-state fallthrough surrogates, all words/guards/controls exact, no faults')


if __name__=='__main__':main()
