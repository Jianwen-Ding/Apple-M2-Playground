#!/usr/bin/env python3
"""Independently verify retained unsigned low-r0 boundary/RET/pop snapshots."""
import gzip
import json
import probe_wide_r0 as B
from verify_ret_mask_state import common


def expected(table, mode, control=False):
    original=table[:32]
    after=[2 if d==0 else 0 if d==1 else d for d in original] if mode=='ret' else original
    states=[original,after,[max(0,d-1) for d in after]]
    result=table.copy();result[64:96]=[0xf4400001]*32
    for phase in range(3):
        writers=[i for i,d in enumerate(original if phase<2 else [max(0,d-1) for d in original]) if d==0] if control else [i for i,d in enumerate(states[phase]) if d==0]
        for bank in range(2):
            values=original if control or bank==1 else states[phase]
            for source,value in enumerate(values):
                for writer in writers:result[96+2048*phase+1024*bank+32*source+writer]=value
    result[6240:6272]=[0xf4400002]*32
    return [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],result,states


def decoded(code):
    pc=0;ops=[]
    while pc<len(code):
        info=B.P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        ops.append((pc,info[0],dict(info[3])));pc+=info[1]
    assert pc==len(code)
    return ops


def main():
    names={f'wide-r0-m{m}-r{r}-{kind}.json.gz' for m in B.STAGES for r in (0,1) for kind in ('original','ret')}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['maximum'],g['rotate'],g['mode'])
        common(r,p,B,ac_online='0')
        original=p['table'][:32]
        assert {0,1,2,3,*B.STAGES[g['maximum']]}<=set(original)
        assert min(original)==0 and max(original)==g['maximum']<=65535
        assert p['table'][32:64]==[2 if d==0 else 0 if d==1 else d for d in original]
        assert len(p['table'])==6320
        for phase in ('control_before','variant','control_after'):
            out,tab,_=expected(p['table'],g['mode'],phase!='variant')
            assert (r[phase]['out'],r[phase]['table_after'])==(out,tab),(path.name,phase)
            assert tab[6272:]==[0xcdcdcdcd]*48
        _,_,states=expected(p['table'],g['mode'])
        assert r['wide_analysis']['exact'] and not r['wide_analysis']['different_words']
        assert r['wide_analysis']['counter_values']==[[[x] for x in ds] for ds in states]
        assert g['drain_pop3_count']==(max(original)+2)//3+2
        ops=decoded(p['code']);bounds=[pc for pc,_,_ in ops]
        assert bounds==g['boundaries'] and len(p['code'])==g['code_bytes']<1024*1024
        assert g['target']-0x2000 in bounds
        assert sum(op=='ret' for _,op,_ in ops)==(g['mode']=='ret')
        assert sum(op=='pop_exec' and f['n']==3 for _,op,f in ops)==g['drain_pop3_count']
        ctrl=decoded(p['control'])
        assert all(op!='ret' and not(op=='pop_exec' and f['n']==0) for _,op,f in ctrl)
        assert all(not(op=='mov_imm' and f.get('D')==0 and f.get('imm16',0)!=0) for _,op,f in ctrl)
        assert not any(op=='bitop' and f.get('D')==0 for _,op,f in ctrl)
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==(r['variant']['out'],r['variant']['table_after'])
    print('PASS sampled unsigned 16-bit boundaries through 0xffff: pop0 preserves numeric values, RET preserves depths >=2, pop1 decrements with zero saturation')
    print('PASS 36 variants / 108 dispatches: complete buffers, guards and independent payload controls exact, zero faults; all model replays exact')
    print('PASS both rotations; 0xffff remains a living readable source and later rejoins after the bounded drain; this does not test increment overflow')


if __name__=='__main__':main()
