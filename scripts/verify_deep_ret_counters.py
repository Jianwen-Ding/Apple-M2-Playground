#!/usr/bin/env python3
"""Independently verify every consecutive low counter through depth 31."""
import gzip
import json
import probe_deep_ret_counters as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,mode,control=False):
    tab=table.copy();tab[64:96]=[0xcafe0001]*32;initial=table[:32]
    changed=[2 if d==0 else 0 if d==1 else d for d in initial]
    for phase in range(2):
        state=initial if control or not phase or mode=='original' else changed
        for lane,d in enumerate(state):
            if d:continue
            for source in range(32):
                at=96+phase*2048+source*32+lane
                tab[at]=initial[source] if control else state[source]
                tab[at+1024]=initial[source]
    tab[4192:4224]=[0xcafe0002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    names={f'deep-ret-m{m}-r{r}-{mode}.json.gz' for m in B.MAXIMA for r in (0,1) for mode in ('original','ret')}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];p=B.build(g['maximum'],g['rotate'],g['mode'])
        common(rec,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        assert set(p['table'][:32])==set(range(g['maximum']+1))
        for phase in ('control_before','variant','control_after'):
            assert (rec[phase]['out'],rec[phase]['table_after'])==expected(p['table'],g['mode'],phase!='variant'),(path.name,phase)
        assert rec['deep_ret_analysis']['exact']
        state=p['table'][:32] if g['mode']=='original' else [2 if d==0 else 0 if d==1 else d for d in p['table'][:32]]
        assert rec['deep_ret_analysis']['post_values']==[[d] for d in state]
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(rec['variant']['out'],rec['variant']['table_after'])
    print('PASS direct nonempty RET map: 0 -> 2, 1 -> 0, all consecutive counters 2..31 unchanged')
    print('PASS 16 variants / 48 dispatches: maxima 5/7/15/31, both rotations, exact payload controls and every word/guard, zero faults')


if __name__=='__main__':main()
