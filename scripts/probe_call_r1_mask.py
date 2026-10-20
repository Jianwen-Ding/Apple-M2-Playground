#!/usr/bin/env python3
"""Checkpoint participation immediately after call r1, before reconvergence.

A 16-byte marker sequence is inserted before fallback's pop, removing the
same amount of stop padding before callee A. Call PC, link, total size and
both callee addresses stay fixed. The marker reuses the untouched entry plane.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_call_r1_link as L

R,C,P,E,CF=L.R,L.C,L.P,L.E,L.CF
DATA=L.DATA
PREPOP=0xc1000001


def observed_oracle(table,link,writes_link=True):
    out,tab=L.fall_oracle(table,link,writes_link)
    tab[96:128]=[PREPOP if table[32+i] else E.SENT for i in range(32)]
    return out,tab


def insert_checkpoint(code,at,landing):
    marker=P.RS.mov(28,PREPOP)+P.RS.agx_loop.store(28,8,22)+P.RS.e('wait 0')
    assert len(marker)==16 and code[landing-16:landing]==P.RS.e('stop')*8
    result=code[:at]+marker+code[at:landing-16]+code[landing:]
    assert len(result)==len(code)
    return result


def build(first,winner):
    p=L.build(first,winner)
    pc=p['gate']['call_pc'];at=pc+6;landing=P.drm.control_main()[1]+C.A
    code=insert_checkpoint(p['code'],at,landing)
    control=code[:pc]+P.RS.e('wait 0')+code[pc+2:]
    expected=observed_oracle(p['table'],p['gate']['link'],False)
    assert P.cov.simulate(control,32,32,64,0,p['table'])==expected,'prepop no-call gate failed'
    for name,g in p['gate']['surrogates'].items():
        uniform=insert_checkpoint(bytes.fromhex(g['uniform_code']),at,landing)
        jump=insert_checkpoint(bytes.fromhex(g['jump_code']),at,landing)
        target=0x2000+P.drm.control_main()[1]+{'A':C.A,'B':C.B}[name]
        eligible=any(p['table'][32+i] and p['table'][i]==target for i in range(32))
        want=C.oracle(p['table'],name,p['gate']['link']) if eligible else L.fall_oracle(p['table'],p['gate']['link'],False)
        with E.measured_model():
            assert P.cov.simulate(uniform,32,32,64,0,p['table'])==want
            assert P.cov.simulate(jump,32,32,64,0,p['table'])==C.oracle(p['table'],name,p['gate']['link'])
        g['uniform_code'],g['jump_code']=uniform.hex(),jump.hex()
    link_fall=insert_checkpoint(bytes.fromhex(p['gate']['link_fall_surrogate_code']),at,landing)
    with E.measured_model():
        assert P.cov.simulate(link_fall,32,32,64,0,p['table'])==observed_oracle(p['table'],p['gate']['link'])
        assert P.cov.simulate(code,32,32,64,0,p['table'])==observed_oracle(p['table'],p['gate']['link'])
    decoded=[];offset=0
    while offset<len(code):
        info=P.cov.ASMB.info(code[offset:offset+16]);assert info and info[1]>0
        decoded.append([offset,info[0],info[1]]);offset+=info[1]
    assert offset==len(code) and any(row[0]==landing for row in decoded)
    assert any(row[0]==P.drm.control_main()[1]+C.B for row in decoded)
    p.update(code=code,control=control,expected=expected)
    p['gate'].update(prepop_checkpoint=True,prepop_pc=at,decoded=decoded,
                     fallback_stop=p['gate']['fallback_stop']+16,
                     link_fall_surrogate_code=link_fall.hex(),
                     parent_snapshot_builder_sha256=p['gate']['builder_sha256'],
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=0)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--repeat',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.first,a.winner)
    print(json.dumps({'first':a.first,'winner':a.winner,'prepop_gates':True}),flush=True)
    if not a.hardware:return
    name=f'call-r1-mask-k{a.first}-{a.winner}-r{a.repeat}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        r['alias_analysis']=dict(exact=(v.get('out'),v.get('table_after'))==observed_oracle(p['table'],p['gate']['link']),
                                  prepop_lanes=[i for i in range(32) if v['table_after'][96+i]==PREPOP])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('alias_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__=='__main__':main()
