#!/usr/bin/env python3
"""Independently check retained RET targets when stored r0 and execution differ."""
import gzip
import json
import probe_ret_stale_targets as B
from verify_ret_mask_state import common


def expected(table,control=False):
    tab=table.copy();tab[96:128]=table[32:64];tab[128:160]=table[:32];tab[160:192]=table[64:96]
    first=next(i for i,m in enumerate(table[64:96]) if m)
    target=table[32+first]
    targets=[0x2000+B.P.drm.control_main()[1]+offset for offset in (1024,1536,2048)]
    marker=(0xa5500001,0xb5500002,0xc5500003)[targets.index(target)]
    incoming=[table[i] if table[64+i] else 1 for i in range(32)]
    post=[2 if d==0 else 0 if d==1 else d for d in incoming]
    for lane in range(32):
        for phase in range(3):
            if control:
                writes=bool(table[64+lane]) or phase>0;value=0
            elif phase==0:
                writes=incoming[lane]==1 or incoming[lane]>=2 and bool(table[64+lane]);value=post[lane]
            else:
                writes=post[lane]<=phase;value=0
            if writes:
                tab[192+64*phase+lane]=marker;tab[224+64*phase+lane]=value
    tab[384:416]=[marker]*32;tab[416:448]=[0]*32
    return ([0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)],tab),incoming,post


def decode(code):
    pc=0;result=[]
    while pc<len(code):
        info=B.P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        result.append((pc,info[0],dict(info[3])));pc+=info[1]
    assert pc==len(code)
    return result


def main():
    names={f'ret-stale-target-k{k}-{shape}-{kind}-r{rot}.json.gz' for k,shape in B.MASKS for kind in B.KINDS for rot in range(3)}
    paths=sorted(B.DATA.glob('*.json.gz'));assert {p.name for p in paths}==names
    decisive={'zero':0,'after':0};both=0
    for path in paths:
        r=json.load(gzip.open(path));g=r['gate'];p=B.build(g['first'],g['shape'],g['kind'],g['rotate'])
        common(r,p,B,ac_online='0');assert len(p['table'])==464
        want,incoming,post=expected(p['table'])
        for phase in ('control_before','variant','control_after'):
            assert (r[phase]['out'],r[phase]['table_after'])==(want if phase=='variant' else expected(p['table'],True)[0]),(path.name,phase)
            assert r[phase]['table_after'][448:]==[0xcdcdcdcd]*16
        assert r['target_analysis']['exact'] and not r['target_analysis']['different_words']
        def pick(mask):return next((p['table'][32+i] for i,m in enumerate(mask) if m),None)
        actual=pick(p['table'][64:96])
        others=dict(zero=pick([d==0 for d in incoming]),after=pick([d==1 or d>=2 and bool(m) for d,m in zip(incoming,p['table'][64:96])]))
        assert g['target_models']==dict(issue=actual,**others)
        assert r['target_analysis']['model_matches']==dict(issue=True,**{k:v==actual for k,v in others.items()})
        for key,value in others.items():decisive[key]+=value!=actual
        both+=all(value!=actual for value in others.values())
        ops=decode(p['code']);assert [pc for pc,_,_ in ops]==g['boundaries']
        bounds=set(g['boundaries']);assert all(t-0x2000 in bounds for t in p['table'][32:64])
        assert len(p['code'])<4096 and len([1 for _,op,_ in ops if op=='ret'])==1
        ctrl=decode(p['control']);assert all(op!='ret' for _,op,_ in ctrl)
        assert all(op in ('if_icmp','pop_exec') or f.get('D')!=0 or op=='mov_imm' and f.get('imm16')==0 for _,op,f in ctrl)
        with B.E.measured_model():prediction=B.P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert prediction==want
    assert all(decisive.values()) and both>0
    print('PASS RET selects the lowest cached issuer before conditional stored-counter updates')
    print(f'PASS target distinctions: {decisive["zero"]} against zero-counter selection, {decisive["after"]} against updated participation; {both} reject both')
    print('PASS 90 programs / 270 dispatches: suffix/scattered/single-lane masks, three rotated destinations, all buffers/guards/controls exact, zero faults; all model replays exact')


if __name__=='__main__':main()
