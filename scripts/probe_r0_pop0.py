#!/usr/bin/env python3
"""Test zero-count execution synchronization after an ordinary r0 write.

The recovery control constructs counters with known IFs and uses wait instead
of the zero-count pop. All snapshots precede a bounded known drain.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_r0_write_mask as B

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-r0-pop0'


def oracle(table,sync=True):
    tab=table.copy();tab[32:64]=[B.PRE]*32;tab[64:96]=table[:32]
    tab[96:128]=[0 if d==0 else E.SENT for d in table[:32]] if sync else table[:32]
    tab[128:160]=[B.DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def build(op,maximum,rotate=0,uniform=False):
    p=B.build(op,maximum,rotate,uniform);e=P.RS.e
    one=e('pop_exec r0l, 1');zero=e('pop_exec r0l, 0');wait=e('wait 0')*(len(one)//2)
    assert len(one)==len(zero)==len(wait)
    for key,replacement in (('code',zero),('control',wait)):
        assert one in p[key];p[key]=p[key].replace(one,replacement,1);P.cov.gate(p[key])
    with E.measured_model():
        assert P.cov.simulate(p['control'],32,32,64,0,p['table'])==oracle(p['table']),'no-pop0 control failed'
        assert P.cov.simulate(p['code'],32,32,64,0,p['table'])==oracle(p['table']),'zero-pop synchronization hypothesis failed'
    p['expected']=oracle(p['table']);p['data_dir']=DATA
    p['gate'].update(zero_pop_hex=zero.hex(),no_zero_pop_in_control=True,
                     complete_zero_sync_hypothesis_exact=True,control_exact=True,
                     base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                     builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--op',choices=B.OPS,default='mov-half')
    ap.add_argument('--maximum',type=int,choices=range(1,32),default=3)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--uniform',action='store_true')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.op,a.maximum,a.rotate,a.uniform)
    print(json.dumps(dict(op=a.op,maximum=a.maximum,rotate=a.rotate,uniform=a.uniform,gates=True)),flush=True)
    if not a.hardware:return
    name=f'r0-pop0-{a.op}-m{a.maximum}-r{a.rotate}-'+('uniform' if a.uniform else 'mixed')
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['zero_pop_analysis']=dict(sync_exact=got==oracle(p['table']),skip_exact=got==oracle(p['table'],False),
           checkpoint_writers=[[i for i,x in enumerate(v['table_after'][plane*32:(plane+1)*32]) if x!=E.SENT] for plane in (2,3)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('zero_pop_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not (r.get('zero_pop_analysis',{}).get('sync_exact') or r.get('zero_pop_analysis',{}).get('skip_exact')):raise SystemExit(3)


if __name__=='__main__':main()
