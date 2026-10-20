#!/usr/bin/env python3
"""Test relative/xor/rotate shuffle sources after per-lane termination.

Use the measured paired-index layout, replacing only the native shuffle kind.
All source payloads and index halves are initialized before divergence.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_stopped_shuffle_index as B

P,E,CF=B.P,B.E,B.CF
DATA=B.L.ROOT/'results/2026-10-20-stopped-native-shuffle'
KINDS=('down','up','xor','rotate_up')
OFFSETS=(0,1,2,3,4,7,8,15,16,31)


def selected(kind,lane,offset):
    if kind=='down':source=lane+offset
    elif kind=='up':source=lane-offset
    elif kind=='xor':source=lane^offset
    elif kind=='rotate_up':source=(lane-offset)%32
    else:raise ValueError(kind)
    return source if 0<=source<32 else lane


def oracle(table,kind,offset,stop=False,fallback=False):
    result=table.copy();result[32:64]=[B.PRE]*32;ds=table[:32]
    for phase in range(2):
        for bank in range(2):
            base=(2+2*phase+bank)*32
            for lane,d in enumerate(ds):
                if not (d==0 if phase==0 else d==1 or not stop and d==0):continue
                source=selected(kind,lane,offset)
                result[base+lane]=lane if stop and fallback and phase and ds[source]==0 else source
    result[192:224]=[E.SENT if stop and d==0 else B.DONE for d in ds]
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],result


def build(maximum,rotate,kind,offset):
    assert maximum in (1,3) and kind in KINDS and offset in range(32)
    p=B.build(maximum,rotate,offset);e=P.RS.e
    for key in ('code','control'):
        code=p[key]
        for operand in (str(offset),'r15l'):
            old=e(f'simd_shuffle r28, r14, {operand}')
            new=e(f'simd_shuffle_{kind} r28, r14, {operand}')
            assert len(old)==len(new) and code.count(old)==2
            code=code.replace(old,new)
        p[key]=code;P.cov.gate(code)
    with E.measured_model():
        assert P.cov.simulate(p['control'],32,32,64,0,p['table'])==oracle(p['table'],kind,offset)
        assert P.cov.simulate(p['code'],32,32,64,0,p['table'])==oracle(p['table'],kind,offset,True)
    p['expected']=oracle(p['table'],kind,offset);p['data_dir']=DATA
    p['gate']=dict(maximum=maximum,rotate=rotate,kind=kind,offset=offset,stop_pc=p['gate']['stop_pc'],
                  actual_legacy_hypothesis_exact=True,wait_control_exact=True,index_seeded_all_lanes=True,
                  base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--depth',type=int,choices=(1,3),default=1)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--kind',choices=KINDS,default='down')
    ap.add_argument('--offset',type=int,choices=range(32),default=1)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.depth,a.rotate,a.kind,a.offset)
    print(json.dumps(dict(depth=a.depth,rotate=a.rotate,kind=a.kind,offset=a.offset,gates=True)),flush=True)
    if not a.hardware:return
    name=f'stopped-native-{a.kind}-{a.depth}-r{a.rotate}-o{a.offset}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['native_analysis']=dict(
            legacy_exact=got==oracle(p['table'],a.kind,a.offset,True),
            self_fallback_exact=got==oracle(p['table'],a.kind,a.offset,True,True),
            immediate_equals_register=v['table_after'][128:160]==v['table_after'][160:192])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('native_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('native_analysis',{}).get('self_fallback_exact'):raise SystemExit(3)


if __name__=='__main__':main()
