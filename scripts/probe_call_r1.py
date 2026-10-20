#!/usr/bin/env python3
"""Check call's explicit r1 source alias against its implicit link write.

Same target addresses, code length, call PC and initialized tables as the
winner probe. Replace the pre-call r1 sentinel with a six-byte register copy,
and change only the call operand to r1. Actual program must simulate exactly.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_call_winner as C

E,P,CF=C.E,C.P,C.CF
DATA=C.ROOT/'results/2026-10-20-call-r1'


def build(first,winner):
    p=C.build(first,winner)
    mov=P.RS.mov;enc=P.RS.e
    old=mov(1,0xf1f10000);new=enc('mov r1, r30')
    assert len(old)==len(new)==6 and p['code'].count(old)==1
    at=p['gate']['call_pc']
    assert p['code'][at:at+2]==enc('call r30') and len(enc('call r1'))==2
    code=p['code'].replace(old,new)
    code=code[:at]+enc('call r1')+code[at+2:]
    assert len(code)==len(p['code'])
    info=P.cov.ASMB.info(code[at:at+16])
    assert info[0]=='call' and info[1]==2 and info[2]=='call r1'
    for name,g in p['gate']['surrogates'].items():
        uniform=bytes.fromhex(g['uniform_code'])
        assert uniform.count(old)==1
        uniform=uniform.replace(old,new)
        target=0x2000+P.drm.control_main()[1]+{'A':C.A,'B':C.B}[name]
        eligible=any(p['table'][32+i] and p['table'][i]==target for i in range(32))
        with E.measured_model():
            assert P.cov.simulate(uniform,32,32,64,0,p['table'])==C.oracle(p['table'],name,p['gate']['link'],fall=not eligible)
        g['uniform_code']=uniform.hex()
    with E.measured_model():
        assert P.cov.simulate(code,32,32,64,0,p['table'])==C.oracle(p['table'],winner,p['gate']['link'],fall=True), 'measured call r1 fallthrough gate failed'
    P.cov.gate(code,allow=('call',))
    p['code']=code;p['data_dir']=DATA
    p['gate'].update(source_register=1,copy_old_hex=old.hex(),copy_new_hex=new.hex(),
                     call_decode=info,actual_alias_exact=True,
                     base_builder_sha256=p['gate']['builder_sha256'],
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=0)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--repeat',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.first,a.winner)
    print(json.dumps({'first':a.first,'winner':a.winner,'actual_call_r1_gate':True}),flush=True)
    if not a.hardware:return
    name=f'call-r1-k{a.first}-{a.winner}-r{a.repeat}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        r['alias_analysis']=dict(exact_measured_fallthrough=(v.get('out'),v.get('table_after'))==C.oracle(p['table'],a.winner,p['gate']['link'],fall=True),
                                  original_target_oracle=(v.get('out'),v.get('table_after'))==C.oracle(p['table'],a.winner,p['gate']['link']))
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('alias_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__=='__main__':main()
