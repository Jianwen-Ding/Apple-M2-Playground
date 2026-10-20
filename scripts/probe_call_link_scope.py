#!/usr/bin/env python3
"""Snapshot r1 after call partitions reconverge, keeping the winner program fixed.

Only changes the two callee snapshots from r0l to r1. All candidate uniform
call and jump paths are re-gated exactly. Default offline; watchdog on hardware.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_call_winner as C

P,CF,E = C.P,C.CF,C.E
DATA = C.DATA
OLD = 'iadd r28, r0l, 0'
NEW = 'iadd r28, r1, 0'
INITIAL_LINK = 0xf1f10000


def patch(code):
    old,new = P.RS.e(OLD),P.RS.e(NEW)
    assert len(old) == len(new) and code.count(old) == 2
    changed = code.replace(old,new)
    assert len(changed) == len(code)
    return changed


def oracle(table,landing,link,jump=False,fall=False):
    out,tab = C.oracle(table,landing,link,fall=fall)
    if not fall:
        target = 0x2000+P.drm.control_main()[1]+{'A':C.A,'B':C.B}[landing]
        tab[224:256] = [link if jump or table[32+i] and table[i] == target else INITIAL_LINK for i in range(32)]
    return out,tab


def hardware_oracle(table,landing,link):
    """Measured link write before filtering, unlike the filtered surrogates."""
    out,tab=oracle(table,landing,link)
    tab[224:256]=[link if table[32+i] else INITIAL_LINK for i in range(32)]
    return out,tab


def build(first,winner):
    p = C.build(first,winner)
    p['code'],p['control'] = patch(p['code']),patch(p['control'])
    p['expected'] = oracle(p['table'],'B',p['gate']['link'],jump=True)
    for name,g in p['gate']['surrogates'].items():
        g['uniform_code'] = patch(bytes.fromhex(g['uniform_code'])).hex()
        g['jump_code'] = patch(bytes.fromhex(g['jump_code'])).hex()
        target = 0x2000+P.drm.control_main()[1]+{'A':C.A,'B':C.B}[name]
        eligible = any(p['table'][32+i] and p['table'][i] == target for i in range(32))
        with E.measured_model():
            assert P.cov.simulate(bytes.fromhex(g['uniform_code']),32,32,64,0,p['table']) == oracle(p['table'],name,p['gate']['link'],fall=not eligible)
            assert P.cov.simulate(bytes.fromhex(g['jump_code']),32,32,64,0,p['table']) == oracle(p['table'],name,p['gate']['link'],jump=True)
    with E.measured_model():
        predicted = P.cov.simulate(p['code'],32,32,64,0,p['table'])
        assert predicted == hardware_oracle(p['table'],winner,p['gate']['link']), 'measured link-write gate failed'
    p['gate'].update(plane7='post-pop-r1',old_snapshot=OLD,new_snapshot=NEW,
                     base_builder_sha256=p['gate']['builder_sha256'],
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=1)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--repeat',type=int,default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.first,a.winner)
    print(json.dumps({'first':a.first,'winner':a.winner,'post_pop_link_gated':True}),flush=True)
    if not a.hardware:return
    name=f'call-link-k{a.first}-{a.winner}-r{a.repeat}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        r['link_analysis']=dict(matches_measured_oracle=(v.get('out'),v.get('table_after'))==hardware_oracle(p['table'],a.winner,p['gate']['link']),
                                matches_partition_oracle=(v.get('out'),v.get('table_after'))==oracle(p['table'],a.winner,p['gate']['link']),
                                link_lanes=[i for i in range(32) if v['table_after'][224+i]==p['gate']['link']],
                                initial_lanes=[i for i in range(32) if v['table_after'][224+i]==INITIAL_LINK])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('link_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__=='__main__':main()
