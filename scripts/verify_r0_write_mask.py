#!/usr/bin/env python3
"""Independent checks that ordinary r0 writes defer execution synchronization."""
import gzip
import json
import probe_r0_write_mask as B
from verify_ret_mask_state import common


def expected(table):
    tab=table.copy();tab[32:64]=[0xf1100001]*32
    tab[64:96]=table[:32]
    tab[96:128]=[0 if d in (0,1) else 0xcdcdcdcd for d in table[:32]]
    tab[128:160]=[0xf1100002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab


def main():
    cases=[(op,m,r,False) for op in B.OPS[:3] for m in (1,3,31) for r in (0,1)]
    cases += [(op,m,0,True) for op in B.OPS for m in (1,2,3,31)]
    names={f'r0-write-{op}-m{m}-r{r}-'+('uniform' if u else 'mixed')+'.json.gz' for op,m,r,u in cases}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['op'],g['maximum'],g['rotate'],g['uniform'])
        common(r,p,B)
        pc=g['write_pc'];raw=bytes.fromhex(g['write_hex']);assert p['code'][pc:pc+len(raw)]==raw
        assert B.P.cov.ASMB.info(raw)[2]==g['write']
        want=expected(p['table'])
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==want,(path.name,phase)
        a=r['r0_write_analysis'];assert a['models']['deferred'] and not a['models']['immediate'] and not a['models']['ignored']
        assert a['checkpoint_writers']==[list(range(32)),[i for i,d in enumerate(p['table'][:32]) if d<=1]]
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred==(r['variant']['out'],r['variant']['table_after'])
    print('PASS ordinary mov-half/mov-full/add-half/immediate writes update low r0 while preserving the issuing mask')
    print('PASS subsequent pop1 synchronizes execution from the written counters; every low-r0 snapshot matches')
    print('PASS 34 variants / 102 dispatches: mixed/uniform depths to 31, exact guards/controls/replay, zero faults')


if __name__=='__main__':main()
