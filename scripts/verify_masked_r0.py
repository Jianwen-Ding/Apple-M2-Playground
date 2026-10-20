#!/usr/bin/env python3
"""Independent full-buffer checks of immediate-shuffle masked r0 observations."""
import gzip
import json
import probe_masked_r0 as B
from verify_ret_mask_state import common


def expected(table,mode,control=False):
    result=table.copy();result[64:96]=[0xcafe0001]*32
    original=table[:32]
    changed=[2 if d==0 else 0 if d==1 else d for d in original]
    for phase in range(2):
        state=original if control or not phase or mode=='original' else changed
        for source_lane in range(32):
            for writer in range(32):
                if state[writer]!=0:continue
                at=96+phase*2048+source_lane*32+writer
                result[at]=original[source_lane] if control else state[source_lane]
                result[at+1024]=original[source_lane]
    result[4192:4224]=[0xcafe0002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'masked-r0-{d}-r{r}-{mode}.json.gz' for d in range(1,5) for r in (0,1) for mode in ('original','desired','ret')}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];p=B.build(g['maximum'],g['rotate'],g['mode'])
        common(rec,p,B)
        for phase in ('control_before','variant','control_after'):
            want=expected(p['table'],g['mode'],phase!='variant')
            assert (rec[phase]['out'],rec[phase]['table_after'])==want,(path.name,phase)
        assert rec['masked_r0_analysis']['exact'] and not rec['masked_r0_analysis']['different_words']
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==(rec['variant']['out'],rec['variant']['table_after'])
    print('PASS direct masked r0l observations: ret maps 0 -> 2, 1 -> 0, deeper unchanged through depth 4')
    print('PASS 24 variants / 72 dispatches: 32 immediate sources, two snapshots and payload controls, all words exact, zero faults')


if __name__=='__main__':main()
