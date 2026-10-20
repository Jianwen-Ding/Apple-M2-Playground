#!/usr/bin/env python3
"""Separate post-overflow register writes from address calculation and shuffles.

All output indices and register seeds are prepared while every lane issues.
No address arithmetic or value masking occurs between the tested first
operation and its first store. Direct stores repeat after wait and full drain.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import probe_masked_r0 as B
from overflow_hypothesis import counter_sync_hypothesis, SOURCE_SHA256 as HYPOTHESIS_SHA256

P,E,CF=B.P,B.E,B.CF
DATA=E.ROOT/'results/2026-10-20-overflow-register-visibility'
SEED=0x1234
VALUE=0xbeef
DONE=0xf7700001
OPS={'imm':'mov_imm r28, 48879','copy':'mov r28, r11','add':'iadd r28, r11, 0',
     'and':'and r28, r11, r29','shuffle':'simd_shuffle r28, r11, 0',
     'down':'simd_shuffle_down r28, r11, 0','up':'simd_shuffle_up r28, r11, 0',
     'xor':'simd_shuffle_xor r28, r11, 0','rotate':'simd_shuffle_rotate_up r28, r11, 0'}
DELAYS=('none','wait','sync','mov1','mov2','mov4','mov5','mov6','mov7','mov8')
LAYOUTS=('balanced','low8','lowonly','highonly','lowmany','highmany','all','all-except0')


def table_for(maximum,n,layout='balanced'):
    ds=([0,1,2,3,15,16,30,31] if maximum==31 else [0,1,2,3,32767,32768,65532,65533,65534,65535])*4
    ds=ds[:32]
    if layout!='balanced':
        assert maximum==65535
        if layout=='low8':ds=[0,1,2,3,65532,65533,65534,65535]*4
        elif layout=='all':ds=[65535]*32
        elif layout=='all-except0':ds=[0]+[65535]*31
        else:
            ds=[0]+[1]*31
            for i in {'lowonly':(1,),'highonly':(31,),'lowmany':range(1,16),'highmany':range(17,32)}[layout]:ds[i]=65535
    mask=[int(d==0 or (d+n)&65535==0) for d in ds]
    return ds+[VALUE]*32+mask+[E.SENT]*(272-96)


def oracle(table):
    tab=table.copy();tab[96:128]=[SEED]*32
    for lane,m in enumerate(table[64:96]):
        if m:tab[128+lane]=tab[160+lane]=VALUE
        tab[192+lane]=VALUE if m else SEED
    tab[224:256]=[DONE]*32
    return [E.SENT]*48+[0xa5a50000+i for i in range(16)],tab


def construct(table,n,cached,op,delay,control=False):
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    body=e('iadd r20, r1, 0')+B.load(10,20,True)
    for base,reg in ((32,11),(64,14)):
        body+=mov(12,base)+e('iadd r13, r20, r12')+B.load(reg,13,True)
    body+=e('wait 0')+mov(29,65535)
    for base,reg in zip((96,128,160,192,224),range(21,26)):
        body+=mov(12,base)+e(f'iadd r{reg}, r20, r12')
    body+=mov(28,SEED)+store(28,8,21)+e('wait 0')
    if control:body+=e('if_icmp r0l, ueq, r14, 1, 1')+e('wait 0')
    else:
        body+=e('mov r0l, r10l')
        if not cached:body+=e('pop_exec r0l, 0')
        body+=e('wait 0')+e(f'if_fcmp r0l, eq, 0.0, 0.0, {n}',f'push_exec r0l, {n}')
    if delay=='wait':body+=e('wait 0')
    elif delay=='sync':body+=e('pop_exec r0l, 0')
    elif delay.startswith('mov'):body+=mov(26,0xabcdef01)*int(delay[3:])
    op_pc=P.drm.control_main()[1]+len(body)
    body+=(mov(28,VALUE) if op=='imm' else e(OPS[op]))+store(28,8,22)+e('wait 0')+store(28,8,23)+e('wait 0')
    drain=(max(table[:32])+n+2)//3+2
    body+=(e('pop_exec r0l, 1') if control else e('pop_exec r0l, 3')*drain)
    body+=store(28,8,24)+e('wait 0')+mov(27,DONE)+store(27,8,25)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code);assert len(code)<1024*1024
    bounds=[];pc=0
    while pc<len(code):
        info=P.cov.ASMB.info(code[pc:pc+16]);assert info and info[1]>0
        bounds.append(pc);pc+=info[1]
    assert pc==len(code) and op_pc in bounds
    return code,op_pc,drain,bounds


def build(maximum,n,cached,op,delay,layout='balanced'):
    assert maximum in (31,65535) and n in (1,2,3) and op in OPS and delay in DELAYS and layout in LAYOUTS
    P.cov.install();table=table_for(maximum,n,layout);code,pc,drain,bounds=construct(table,n,cached,op,delay)
    ctrl,_,_,_=construct(table,n,cached,op,delay,True)
    with E.measured_model(), counter_sync_hypothesis():
        assert P.cov.simulate(ctrl,32,32,64,0,table)==oracle(table),'independent IF control failed'
        assert P.cov.simulate(code,32,32,64,0,table)==oracle(table),'actual visibility hypothesis failed'
    return dict(code=code,control=ctrl,table=table,n=32,wg=32,regs=64,expected=oracle(table),data_dir=DATA,
        gate=dict(maximum=maximum,push_n=n,cached=cached,op=op,delay=delay,layout=layout,op_pc=pc,drain_pop3_count=drain,
                  boundaries=bounds,all_output_indices_initialized_before_divergence=True,
                  actual_counter_sync_hypothesis_exact=True,overflow_hypothesis='counter-sync',no_r0_write_push_control_exact=True,
                  overflow_hypothesis_sha256=HYPOTHESIS_SHA256,
                  builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--maximum',type=int,choices=(31,65535),default=65535)
    ap.add_argument('--n',type=int,choices=(1,2,3),default=1);ap.add_argument('--cached',action='store_true')
    ap.add_argument('--op',choices=OPS,default='shuffle');ap.add_argument('--delay',choices=DELAYS,default='none')
    ap.add_argument('--layout',choices=LAYOUTS,default='balanced')
    ap.add_argument('--hardware',action='store_true');a=ap.parse_args();p=build(a.maximum,a.n,a.cached,a.op,a.delay,a.layout)
    print(json.dumps(dict(gates=True,maximum=a.maximum,push_n=a.n,cached=a.cached,op=a.op,delay=a.delay,bytes=len(p['code']))),flush=True)
    if not a.hardware:return
    name=f'overflow-visibility-m{a.maximum}-n{a.n}-'+('cached' if a.cached else 'synced')+f'-{a.op}-{a.delay}'+('' if a.layout=='balanced' else '-'+a.layout)
    r=CF.hardware(name,p);v=r.get('variant',{})
    if v.get('ok'):
        want=oracle(p['table'])
        r['visibility_analysis']=dict(exact=(v['out'],v['table_after'])==want,
            first=v['table_after'][128:160],after_wait=v['table_after'][160:192],after_drain=v['table_after'][192:224],
            differences=[dict(word=i,actual=x,expected=y) for i,(x,y) in enumerate(zip(v['table_after'],want[1])) if x!=y])
    with gzip.GzipFile(filename=str(DATA/f'{name}.json.gz'),mode='wb',mtime=0) as f:f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(analysis=r.get('visibility_analysis'),recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted'):raise SystemExit(2)
    if not r.get('visibility_analysis',{}).get('exact'):raise SystemExit(3)


if __name__=='__main__':main()
