#!/usr/bin/env python3
"""Distinguish stopped index-bit contributions in native relative shuffles."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_dead_index_or as D
import probe_stopped_native_shuffle as N

P,E,CF=D.P,D.E,D.CF
DATA=D.B.L.ROOT/'results/2026-10-20-native-dead-index-or'


def source(kind,lane,offset,q=None):
    target=N.selected(kind,lane,offset)
    outside=(kind=='down' and lane+offset>=32) or (kind=='up' and lane-offset<0)
    if q is None or outside:return target
    low=((lane+q)&3) if kind=='down' else ((lane^q)&3) if kind=='xor' else ((lane-q)&3)
    return target//4*4+low


def oracle(table,kind,seed,index,stop=False,ignored=True,fallback=True):
    tab=table.copy();tab[32:64]=[D.B.PRE]*32;ds=table[:32]
    for phase in range(2):
        offset=seed if phase==0 else index
        for bank in range(2):
            q=(index|seed)&3 if phase and bank and stop and not ignored else None
            for lane,d in enumerate(ds):
                if not (d==0 if phase==0 else d==1 or not stop and d==0):continue
                selected=source(kind,lane,offset,q)
                value=lane if phase and stop and fallback and ds[selected]==0 else selected
                tab[(2+2*phase+bank)*32+lane]=value
    tab[192:224]=[E.SENT if stop and d==0 else D.B.DONE for d in ds]
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def build(rotate,seed,index,kind):
    assert kind in N.KINDS
    p=D.build(rotate,seed,index);e=P.RS.e
    for key in ('code','control'):
        code=p[key]
        for operand in sorted({str(seed),str(index),'r15l'}):
            old=e(f'simd_shuffle r28, r14, {operand}');new=e(f'simd_shuffle_{kind} r28, r14, {operand}')
            assert len(old)==len(new) and old in code
            code=code.replace(old,new)
        p[key]=code;P.cov.gate(code)
    with E.measured_model():
        assert P.cov.simulate(p['control'],32,32,64,0,p['table'])==oracle(p['table'],kind,seed,index)
        assert P.cov.simulate(p['code'],32,32,64,0,p['table'])==oracle(p['table'],kind,seed,index,True,True,True)
    p['expected']=oracle(p['table'],kind,seed,index);p['data_dir']=DATA
    p['gate']=dict(rotate=rotate,seed=seed,index=index,kind=kind,stop_pc=p['gate']['stop_pc'],
                   actual_measured_model_exact=True,wait_control_exact=True,
                   base_builder_sha256=hashlib.sha256(Path(D.__file__).read_bytes()).hexdigest(),
                   native_builder_sha256=hashlib.sha256(Path(N.__file__).read_bytes()).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--seed',type=int,choices=range(4),default=1)
    ap.add_argument('--index',type=int,choices=range(32),default=2)
    ap.add_argument('--kind',choices=N.KINDS,default='down')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.rotate,a.seed,a.index,a.kind)
    print(json.dumps(dict(rotate=a.rotate,seed=a.seed,index=a.index,kind=a.kind,gates=True)),flush=True)
    if not a.hardware:return
    name=f'native-dead-or-{a.kind}-r{a.rotate}-s{a.seed}-i{a.index}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['native_or_analysis']=dict(
            ignored_dead_bits=got==oracle(p['table'],a.kind,a.seed,a.index,True,True),
            retained_dead_bits=got==oracle(p['table'],a.kind,a.seed,a.index,True,False),
            immediate_equals_register=v['table_after'][128:160]==v['table_after'][160:192])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('native_or_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not (r.get('native_or_analysis',{}).get('ignored_dead_bits') or r.get('native_or_analysis',{}).get('retained_dead_bits')):raise SystemExit(3)


if __name__=='__main__':main()
