#!/usr/bin/env python3
"""Read r0l at a return landing before any pop, retaining all target addresses.

Move the existing 16-byte post-pop r1 snapshot to the front of each landing,
changing its source to r0l. Code length and every transfer/landing PC stay
fixed. Known jump controls validate the read and independent post-pop traces.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import probe_three_targets as R

P,E,CF=R.P,R.E,R.CF
DATA=R.ROOT/'results/2026-10-20-ret-prepop'


def relocate(code):
    old=P.RS.e('mov r28, r1')+P.RS.agx_loop.store(28,8,26)+P.RS.e('wait 0')
    new=P.RS.e('mov r28, r0l')+P.RS.agx_loop.store(28,8,26)+P.RS.e('wait 0')
    assert len(old)==len(new)==16
    site=P.drm.control_main()[1]
    starts=[site+v for v in R.OFFSETS.values()]
    for start,end in zip(starts,starts[1:]+[len(code)]):
        block=code[start:end]
        assert block.startswith(P.RS.e('pop_exec r0l, 1')) and block.count(old)==1
        changed=new+block.replace(old,b'',1)
        assert len(changed)==len(block)
        code=code[:start]+changed+code[end:]
    return code


def hypothesis(table,target,link,jump=False):
    out,tab=R.oracle('ret',table,target,link,'jump' if jump else 'actual')
    tab[224:256]=[0 if jump and table[32+i] else E.SENT for i in range(32)]
    return out,tab


def build(first,winner,seed):
    p=R.build('ret',first,winner,seed)
    p['code'],p['control']=relocate(p['code']),relocate(p['control'])
    p['expected']=hypothesis(p['table'],'A',p['gate']['link'],jump=True)
    for name,g in p['gate']['surrogates'].items():
        uniform=relocate(bytes.fromhex(g['uniform_code']));jump=relocate(bytes.fromhex(g['jump_code']))
        with E.measured_model():
            assert P.cov.simulate(uniform,32,32,64,0,p['table'])==hypothesis(p['table'],name,p['gate']['link'])
            assert P.cov.simulate(jump,32,32,64,0,p['table'])==hypothesis(p['table'],name,p['gate']['link'],jump=True)
        g['uniform_code'],g['jump_code']=uniform.hex(),jump.hex()
    with E.measured_model():
        assert P.cov.simulate(p['code'],32,32,64,0,p['table'])==hypothesis(p['table'],winner,p['gate']['link'])
    decoded=[];pc=0
    while pc<len(p['code']):
        info=P.cov.ASMB.info(p['code'][pc:pc+16]);assert info and info[1]>0
        decoded.append([pc,info[0],info[1]]);pc+=info[1]
    assert pc==len(p['code']) and all(any(row[0]==addr-0x2000 for row in decoded) for addr in p['gate']['targets'].values())
    p['data_dir']=DATA
    p['gate'].update(prepop_r0_snapshot=True,decoded=decoded,
                     hypothesis='no lane active at return landing before pop',
                     base_builder_sha256=p['gate']['builder_sha256'],
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--first',type=int,default=1)
    ap.add_argument('--winner',choices=tuple(R.OFFSETS),default='C')
    ap.add_argument('--seed',type=int,default=103)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.first,a.winner,a.seed)
    print(json.dumps({'first':a.first,'winner':a.winner,'prepop_hypothesis_gated':True}),flush=True)
    if not a.hardware:return
    name=f'ret-prepop-k{a.first}-{a.winner}-s{a.seed}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        reference=hypothesis(p['table'],a.winner,p['gate']['link'])
        got=v['table_after'];pre=got[224:256]
        r['prepop_analysis']=dict(writers=[i for i,x in enumerate(pre) if x!=E.SENT],
                                  values={str(i):x for i,x in enumerate(pre) if x!=E.SENT},
                                  other_words_exact=(v['out']==reference[0] and got[:224]==reference[1][:224] and got[256:]==reference[1][256:]))
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('prepop_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('prepop_analysis',{}).get('other_words_exact'):raise SystemExit(3)


if __name__=='__main__':main()
