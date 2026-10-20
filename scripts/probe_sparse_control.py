#!/usr/bin/env python3
"""Scattered participation for lowest-active ret/call and call-link scope.

Keeps the established winner program bytes; changes only initialized input
active bits. Every uniform and direct-jump path is re-simulated with the exact
new table. Actual unsupported diagnostics remain explicit. Default offline.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random

import probe_ret_winner as R
import probe_call_link_scope as L

E,P,CF=R.E,R.P,R.CF
ROOT=E.ROOT
DATA=ROOT/'results/2026-10-20-sparse-control'


def mask_for(first,seed):
    rng=random.Random(seed*101+first)
    mask=(1<<first)|(rng.getrandbits(32)&(0xffffffff^((1<<(first+1))-1)))
    if first<31:mask|=1<<31
    if first<30:mask&=~(1<<(first+1))  # retain at least one hole above the first lane
    return mask


def ret_oracle(table,landing,jump=False):
    tab=table.copy();tab[64:96]=[R.PRE]*32
    tab[96:128]=[R.MARKS[landing][0] if jump or not table[32+i] else E.SENT for i in range(32)]
    tab[128:160]=[R.MARKS[landing][1]]*32
    tab[192:224]=[0]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def call_oracle(table,landing,link,jump=False,uniform=False,fall=False):
    out,tab=L.oracle(table,landing,link,jump=jump,fall=fall)
    if not (jump or uniform or fall):
        tab[224:256]=[link if table[32+i] else L.INITIAL_LINK for i in range(32)]
    return out,tab


def build(kind,first,winner,seed):
    base=R if kind=='ret' else L
    p=base.build(first,winner)
    mask=mask_for(first,seed)
    p['table'][32:64]=[(mask>>i)&1 for i in range(32)]
    for name,g in p['gate']['surrogates'].items():
        with E.measured_model():
            uniform=P.cov.simulate(bytes.fromhex(g['uniform_code']),32,32,64,0,p['table'])
            jump=P.cov.simulate(bytes.fromhex(g['jump_code']),32,32,64,0,p['table'])
        if kind=='ret':
            want_uniform=ret_oracle(p['table'],name)
            want_jump=ret_oracle(p['table'],name,jump=True)
        else:
            target=0x2000+P.drm.control_main()[1]+{'A':1024,'B':1536}[name]
            eligible=any(p['table'][32+i] and p['table'][i]==target for i in range(32))
            want_uniform=call_oracle(p['table'],name,p['gate']['link'],uniform=True,fall=not eligible)
            want_jump=call_oracle(p['table'],name,p['gate']['link'],jump=True)
        assert uniform==want_uniform and jump==want_jump,'exact sparse-table surrogate gate failed'
    with E.measured_model():
        try:predicted=P.cov.simulate(p['code'],32,32,64,0,p['table'])
        except RuntimeError as exc:
            phrase=('divergent active lanes with lane 0 inactive not modelled' if kind=='ret'
                    else 'divergent targets with lane 0 inactive not modelled')
            assert phrase in str(exc)
            actual=dict(unsupported_as_expected=True,diagnostic=str(exc))
        else:
            assert kind=='ret' and first==31 and predicted==ret_oracle(p['table'],winner)
            actual=dict(uniform_active_case_exact=True)
    p['expected']=(ret_oracle(p['table'],'A',jump=True) if kind=='ret' else
                   call_oracle(p['table'],'B',p['gate']['link'],jump=True))
    p['data_dir']=DATA
    p['gate'].update(sparse_kind=kind,sparse_seed=seed,sparse_mask=mask,sparse_surrogates_exact=True,
                     sparse_actual_gate=actual,
                     base_builder_sha256=p['gate']['builder_sha256'],
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kind',choices=('call','ret'),required=True)
    ap.add_argument('--first',type=int,default=1)
    ap.add_argument('--winner',choices=('A','B'),default='B')
    ap.add_argument('--seed',type=int,default=211)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.kind,a.first,a.winner,a.seed)
    print(json.dumps({'kind':a.kind,'first':a.first,'winner':a.winner,'mask':hex(p['gate']['sparse_mask']),'gates':True}),flush=True)
    if not a.hardware:return
    name=f'sparse-{a.kind}-k{a.first}-{a.winner}-s{a.seed}'
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        want=(ret_oracle(p['table'],a.winner) if a.kind=='ret' else
              call_oracle(p['table'],a.winner,p['gate']['link']))
        r['sparse_analysis']=dict(oracle_exact=(v.get('out'),v.get('table_after'))==want)
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps({'analysis':r.get('sparse_analysis'),'recovery':r.get('recovery_control_passed'),
                      'halted':r.get('halted'),'budget':r['after']['budget_used']}),flush=True)
    if r.get('halted'):raise SystemExit(2)


if __name__=='__main__':main()
