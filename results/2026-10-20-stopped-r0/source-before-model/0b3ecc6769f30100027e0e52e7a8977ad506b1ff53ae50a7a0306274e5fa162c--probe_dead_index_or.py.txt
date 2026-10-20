#!/usr/bin/env python3
"""Does a terminated lane's seeded low index contaminate a register shuffle?

Odd/even survivors update index r15 after STOP/pop; stopped lanes retain known
seed bits. Compare an immediate index with the register form. All memory and
sources are initialized, bounded, and simulator-gated before optional hardware.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_stopped_shuffle_index as B

P,E,CF=B.P,B.E,B.CF
DATA=B.L.ROOT/'results/2026-10-20-dead-index-or'


def oracle(table,seed,index,stop,ignored=False,fallback=True):
    tab=table.copy();tab[32:64]=[B.PRE]*32;ds=table[:32]
    for writer,d in enumerate(ds):
        if d==0:tab[64+writer]=tab[96+writer]=seed
        if d==1 or not stop and d==0:
            for bank in range(2):
                source=index
                if bank and stop and not ignored:source=(index&~3)|((index|seed)&3)
                selected=writer if stop and fallback and ds[source]==0 else source
                tab[128+32*bank+writer]=selected
        if not stop or d!=0:tab[192+writer]=B.DONE
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def build(rotate,seed,index):
    assert rotate in (0,1) and seed in range(4) and index in range(32)
    p=B.build(1,rotate,seed);e=P.RS.e;pc=p['gate']['stop_pc']
    begin=pc+2+len(e('pop_exec r0l, 1'))
    old=e(f'simd_shuffle r28, r14, {seed}');new=e(f'simd_shuffle r28, r14, {index}')
    assert len(old)==len(new) and p['code'][begin:].count(old)==1
    for key in ('code','control'):
        code=p[key];p[key]=code[:begin]+P.RS.mov(15,index)+code[begin:].replace(old,new,1)
        P.cov.gate(p[key])
    with E.measured_model():
        assert P.cov.simulate(p['control'],32,32,64,0,p['table'])==oracle(p['table'],seed,index,False)
        assert P.cov.simulate(p['code'],32,32,64,0,p['table'])==oracle(p['table'],seed,index,True,False,False)
    p['expected']=oracle(p['table'],seed,index,False);p['data_dir']=DATA
    p['gate']=dict(rotate=rotate,seed=seed,index=index,stop_pc=pc,all_initial_indices_seeded=True,
                   actual_legacy_hypothesis_exact=True,wait_control_exact=True,
                   base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--seed',type=int,choices=range(4),default=3)
    ap.add_argument('--index',type=int,choices=range(32),default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.rotate,a.seed,a.index)
    print(json.dumps(dict(rotate=a.rotate,seed=a.seed,index=a.index,gates=True)),flush=True)
    if not a.hardware:return
    name=f'dead-index-or-r{a.rotate}-s{a.seed}-i{a.index}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['index_or_analysis']=dict(
            retained_dead_bits=got==oracle(p['table'],a.seed,a.index,True,False),
            ignored_dead_bits=got==oracle(p['table'],a.seed,a.index,True,True),
            immediate_equals_register=v['table_after'][128:160]==v['table_after'][160:192])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('index_or_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not (r.get('index_or_analysis',{}).get('retained_dead_bits') or r.get('index_or_analysis',{}).get('ignored_dead_bits')):raise SystemExit(3)


if __name__=='__main__':main()
