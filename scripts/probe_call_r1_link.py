#!/usr/bin/env python3
"""Distinguish call r1 no-op from implicit-link overwrite at fallthrough.

Only fills stop padding after the bounded fallback with an r1 snapshot. The
same-length shader keeps both candidate callees and continuation valid. A
wait-instead-of-call control checks the r1 copy and entire fallthrough trace.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_call_r1 as R

P,CF,E,C=R.P,R.CF,R.E,R.C
DATA=R.DATA


def fall_oracle(table,link,writes_link):
    out,tab=C.oracle(table,'A',link,fall=True)
    tab[224:256]=[link if writes_link and table[32+i] else table[i] for i in range(32)]
    return out,tab


def add_snapshot(code,stop_pc):
    e=P.RS.e
    snapshot=e('mov r28, r1')+P.RS.agx_loop.store(28,8,26)+e('wait 0')+e('stop')
    assert len(snapshot)%2==0 and code[stop_pc:stop_pc+len(snapshot)]==e('stop')*(len(snapshot)//2)
    return code[:stop_pc]+snapshot+code[stop_pc+len(snapshot):]


def build(first,winner):
    p=R.build(first,winner)
    pc=p['gate']['call_pc']
    fallback_stop=next(row[0] for row in p['gate']['decoded'] if row[0]>pc and row[1]=='stop')
    code=add_snapshot(p['code'],fallback_stop)
    control=code[:pc]+P.RS.e('wait 0')+code[pc+2:]
    expected=fall_oracle(p['table'],p['gate']['link'],writes_link=False)
    assert P.cov.simulate(control,32,32,64,0,p['table'])==expected,'no-call fallthrough oracle failed'
    # Closest known-op model of the observed alias hypothesis: write r1 in
    # the issue-active mask, then fall through. The six-byte call/wait/wait
    # island is replaced without moving any later boundary or target.
    assert len(P.RS.mov(1,p['gate']['link']))==6
    link_fall=code[:pc]+P.RS.mov(1,p['gate']['link'])+code[pc+6:]
    with E.measured_model():
        assert P.cov.simulate(link_fall,32,32,64,0,p['table'])==fall_oracle(p['table'],p['gate']['link'],True)
    for name,g in p['gate']['surrogates'].items():
        uniform=add_snapshot(bytes.fromhex(g['uniform_code']),fallback_stop)
        jump=add_snapshot(bytes.fromhex(g['jump_code']),fallback_stop)
        target=0x2000+P.drm.control_main()[1]+{'A':C.A,'B':C.B}[name]
        eligible=any(p['table'][32+i] and p['table'][i]==target for i in range(32))
        want=(C.oracle(p['table'],name,p['gate']['link']) if eligible else
              fall_oracle(p['table'],p['gate']['link'],writes_link=False))
        with E.measured_model():
            assert P.cov.simulate(uniform,32,32,64,0,p['table'])==want
            assert P.cov.simulate(jump,32,32,64,0,p['table'])==C.oracle(p['table'],name,p['gate']['link'])
        g['uniform_code'],g['jump_code']=uniform.hex(),jump.hex()
    with E.measured_model():
        assert P.cov.simulate(code,32,32,64,0,p['table'])==fall_oracle(p['table'],p['gate']['link'],True), 'measured alias link/fallthrough gate failed'
    p.update(code=code,control=control,expected=expected)
    p['gate'].update(fallback_stop=fallback_stop,fallback_r1_snapshot=True,
                     link_fall_surrogate_code=link_fall.hex(),link_fall_surrogate_exact=True,
                     parent_builder_sha256=p['gate']['builder_sha256'],
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=0)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--repeat',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.first,a.winner)
    print(json.dumps({'first':a.first,'winner':a.winner,'fallback_snapshot_gated':True}),flush=True)
    if not a.hardware:return
    name=f'call-r1-link-k{a.first}-{a.winner}-r{a.repeat}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=(v.get('out'),v.get('table_after'))
        r['alias_analysis']=dict(matches_noop=got==fall_oracle(p['table'],p['gate']['link'],False),
                                  matches_link_fallthrough=got==fall_oracle(p['table'],p['gate']['link'],True),
                                  post_r1=v['table_after'][224:256])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('alias_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__=='__main__':main()
