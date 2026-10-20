#!/usr/bin/env python3
"""Independently check conditional RET counter/execution updates after ALU writes."""
import gzip
import json
import probe_ret_stale_exec as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,control=False):
    tab=table.copy();tab[32:64]=[0xf2200001]*32
    for lane,original in enumerate(table[:32]):
        counter=2 if control or original==0 else 0 if original==1 else original
        for phase in range(4):
            active=(phase>=2 if control else original!=0) if phase==0 else max(counter-phase,0)==0
            if control and phase==0:active=False
            if active:tab[(2+phase)*32+lane]=counter if phase==0 else 0
    tab[192:224]=[0xf2200002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    cases=[(op,m,r,False) for op in B.B.OPS[:3] for m in (1,3,31) for r in (0,1)]
    cases += [(op,m,0,True) for op in B.B.OPS for m in (1,2,3,31)]
    names={f'ret-stale-{op}-m{m}-r{r}-'+('uniform' if u else 'mixed')+'.json.gz' for op,m,r,u in cases}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['op'],g['maximum'],g['rotate'],g['uniform'])
        common(r,p,B);require_source(B.B.__file__,g['base_builder_sha256'])
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==expected(p['table'],phase!='variant'),(path.name,phase)
        assert not r['stale_ret_analysis']['models']['issue']
        # The first record predates the counter-stale hypothesis. Preserve its
        # all-false initial classification and check the readback independently.
        if 'counter-stale' in r['stale_ret_analysis']['models']:assert r['stale_ret_analysis']['models']['counter-stale']
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred!=(r['variant']['out'],r['variant']['table_after'])
    print('PASS nonempty RET conditionally updates counter 0/1 and their execution bits; deeper stale execution is preserved')
    print('PASS uniform nonzero counters still transfer, with no zero-counter issuer required')
    print('PASS 34 variants / 102 dispatches: exact words/guards/no-RET controls, zero faults; 34 simulator counterexamples retained')


if __name__=='__main__':main()
