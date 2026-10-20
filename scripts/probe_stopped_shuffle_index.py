#!/usr/bin/env python3
"""Compare immediate/register shuffle indices with masked and stopped sources.

All index registers are seeded in every physical lane before divergence,
including lanes subsequently stopped. Candidate/control differ by STOP/wait.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_ret_levels as L
from run_drm_cpu_clock import load

P,E,CF=L.P,L.E,L.CF
DATA=L.ROOT/'results/2026-10-20-stopped-shuffle-index'
PRE=0xd1100001
DONE=0xd1100002


def oracle(table,index,stop=False,fallback=False):
    result=table.copy();result[32:64]=[PRE]*32
    ds=table[:32]
    for phase in range(2):
        for bank in range(2):
            base=(2+2*phase+bank)*32
            result[base:base+32]=[(i if stop and fallback and phase and ds[index]==0 else index)
                               if (d==0 if phase==0 else d==1 or not stop and d==0) else E.SENT for i,d in enumerate(ds)]
    result[192:224]=[E.SENT if stop and d==0 else DONE for d in ds]
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],result


def build(maximum,rotate,index):
    assert 1<=maximum<=4 and 0<=index<32
    P.cov.install();e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    table=L.depths(maximum,rotate)+[E.SENT]*(6*32+16)
    body=e('iadd r20, r1, 0')+e('iadd r14, r1, 0')+mov(15,index)
    for plane,reg in zip(range(1,7),range(21,27)):
        body+=mov(29,plane*32)+e(f'iadd r{reg}, r20, r29')
    body+=load(10,20,True)+e('wait 0')+mov(28,PRE)+store(28,8,21)+e('wait 0')
    for threshold in range(max(table[:32]),0,-1):body+=e(f'if_icmp r0l, ult, r10, {threshold}, 1')
    def gather(regs):
        b=b''
        for reg,operand in zip(regs,(str(index),'r15l')):
            b+=e(f'simd_shuffle r28, r14, {operand}')+store(28,8,reg)+e('wait 0')
        return b
    body+=gather((22,23));pc=P.drm.control_main()[1]+len(body)
    body+=e('stop')+e('pop_exec r0l, 1')+gather((24,25))
    body+=e('pop_exec r0l, 1')*4+mov(28,DONE)+store(28,8,26)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);control=code[:pc]+e('wait 0')+code[pc+2:]
    P.cov.gate(code);P.cov.gate(control)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==oracle(table,index)
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table,index,True)
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,
                expected=oracle(table,index),data_dir=DATA,
                gate=dict(maximum=maximum,rotate=rotate,index=index,stop_pc=pc,
                          index_seeded_all_lanes=True,wait_control_exact=True,actual_legacy_hypothesis_exact=True,
                          builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--depth',type=int,choices=range(1,5),default=1)
    ap.add_argument('--rotate',type=int,default=0)
    ap.add_argument('--index',type=int,choices=range(32),default=0)
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.depth,a.rotate,a.index)
    print(json.dumps(dict(depth=a.depth,rotate=a.rotate,index=a.index,gates=True)),flush=True)
    if not a.hardware:return
    name=f'stopped-shuffle-index-{a.depth}-r{a.rotate}-i{a.index}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        got=v['out'],v['table_after'];r['index_analysis']=dict(
            self_fallback_exact=got==oracle(p['table'],a.index,True,True),
            legacy_exact=got==oracle(p['table'],a.index,True),
            source_depth=p['table'][a.index],immediate_equals_register=v['table_after'][128:160]==v['table_after'][160:192])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('index_analysis'),recovery=r.get('recovery_control_passed'),
                         halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('index_analysis',{}).get('self_fallback_exact'):raise SystemExit(3)


if __name__=='__main__':main()
