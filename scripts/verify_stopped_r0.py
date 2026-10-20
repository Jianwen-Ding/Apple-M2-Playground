#!/usr/bin/env python3
"""Verify stopped-source shuffle fallback, preserving initial rejected hypotheses."""
import gzip
import json
import probe_stopped_r0 as B
from verify_ret_mask_state import common
from verify_probe_sources import require_source


def expected(table,payload,stop):
    result=table.copy();result[64:96]=[0xcafe0001]*32;depths=table[:32]
    for phase in range(2):
        for writer,d in enumerate(depths):
            visible=d==0 if phase==0 else d==1 or not stop and d==0
            if not visible:continue
            for source in range(32):
                selected=writer if phase and stop and depths[source]==0 else source
                low=depths[selected] if phase==0 else max(depths[selected]-1,0)
                data=selected if payload=='lane' else depths[selected]
                at=96+phase*2048+source*32+writer
                result[at]=low;result[at+1024]=data
    result[4192:4224]=[0xcdcdcdcd if stop and d==0 else 0xcafe0002 for d in depths]
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result


def main():
    names={f'stopped-r0-{d}-r{r}-lane.json.gz' for d in range(1,5) for r in (0,1)}|{'stopped-r0-3-r0.json.gz'}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        rec=json.load(gzip.open(path));g=rec['gate'];payload=g.get('payload','depth')
        p=B.build(g['maximum'],g['rotate'],payload);common(rec,p,B)
        require_source(B.B.__file__,g['base_builder_sha256'])
        pc=g['stop_pc'];assert p['code'][:pc]==p['control'][:pc] and p['code'][pc+2:]==p['control'][pc+2:]
        assert p['code'][pc:pc+2]==bytes.fromhex('8800') and p['control'][pc:pc+2]==bytes.fromhex('3800')
        for phase in ('control_before','variant','control_after'):
            assert (rec[phase]['out'],rec[phase]['table_after'])==expected(p['table'],payload,phase=='variant'),(path.name,phase)
        with B.E.measured_model():pred=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert pred!=(rec['variant']['out'],rec['variant']['table_after'])
    print('PASS stopped-source immediate shuffle returns own value, while masked live sources remain readable')
    print('PASS nine variants / 27 dispatches, all words/guards/recovery exact, zero faults; nine simulator counterexamples retained')
    print('PASS stopped lanes stay absent after five pops; their stored r0 value is not observable through this fallback')


if __name__=='__main__':main()
