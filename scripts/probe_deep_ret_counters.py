#!/usr/bin/env python3
"""Direct low-r0 observations for consecutive incoming return counters to 31.

Extend the measured immediate-shuffle diagnostic only at its final drain;
original target PCs and gather addresses remain unchanged. Default is offline.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_masked_r0 as B

P,E,CF=B.P,B.E,B.CF
DATA=B.L.ROOT/'results/2026-10-20-deep-ret-counters'
MAXIMA=(5,7,15,31)


def construct(table,mode,payload_only=False):
    code,pc=B.construct(table,mode,payload_only);e=P.RS.e
    tail=P.RS.mov(28,B.DONE)+P.RS.agx_loop.store(28,8,22)+e('wait 0')+e('stop')
    old=e('pop_exec r0l, 1')*4+tail
    new=e('pop_exec r0l, 1')*(max(table[:32])+2)+tail
    assert code.count(old)==1
    code=code.replace(old,new);P.cov.gate(code,allow=('ret',) if mode=='ret' else ())
    boundaries=[];at=0
    while at<len(code):
        info=P.cov.ASMB.info(code[at:at+16]);assert info and info[1]>0
        boundaries.append(at);at+=info[1]
    assert at==len(code) and P.drm.control_main()[1]+B.LANDING in boundaries
    return code,pc,boundaries


def build(maximum,rotate,mode):
    assert maximum in MAXIMA and rotate in (0,1) and mode in ('original','ret')
    table=B.table_for(maximum,rotate)
    code,pc,bounds=construct(table,mode);control,_,_=construct(table,'original',True)
    with E.measured_model():
        assert P.cov.simulate(control,32,32,64,0,table)==B.oracle(table,'original',True)
        for kind in ('original','ret'):
            variant,_,_=construct(table,kind)
            assert P.cov.simulate(variant,32,32,64,0,table)==B.oracle(table,kind),kind
    return dict(code=code,control=control,table=table,n=32,wg=32,regs=64,
        expected=B.oracle(table,'original',True),data_dir=DATA,
        gate=dict(maximum=maximum,rotate=rotate,mode=mode,transfer_pc=pc,boundaries=bounds,
                  target=0x2000+P.drm.control_main()[1]+B.LANDING,actual_deeper_counter_hypothesis_exact=True,
                  payload_control_exact=True,original_path_exact=True,
                  base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--maximum',type=int,choices=MAXIMA,default=5)
    ap.add_argument('--rotate',type=int,choices=(0,1),default=0)
    ap.add_argument('--mode',choices=('original','ret'),default='original')
    ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.maximum,a.rotate,a.mode)
    print(json.dumps(dict(maximum=a.maximum,rotate=a.rotate,mode=a.mode,gates=True)),flush=True)
    if not a.hardware:return
    name=f'deep-ret-m{a.maximum}-r{a.rotate}-{a.mode}';r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        r['deep_ret_analysis']=dict(exact=(v['out'],v['table_after'])==B.oracle(p['table'],a.mode),
            post_values=[sorted(set(v['table_after'][B.BASE+B.PHASE_WORDS+j*32:B.BASE+B.PHASE_WORDS+(j+1)*32])-{E.SENT}) for j in range(32)])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:
        f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('deep_ret_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('deep_ret_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
