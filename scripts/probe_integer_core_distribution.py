#!/usr/bin/env python3
"""Arithmetic trains with matched SR19/SR20 output planes and placement properties."""
import argparse
from collections import Counter
import fcntl
import gzip
import json
from pathlib import Path
import random
import shlex
import time
from types import SimpleNamespace
import probe_integer_timing_state as S

I,P,H,T=S.I,S.P,S.H,S.T
DATA=S.ROOT/'results/2026-10-20-integer-core-distribution'
SCRATCH=Path('/scratch/apple-m2-playground/integer-core-distribution')
VALID_CORES={cluster*16+core for cluster,count in enumerate((10,9,9,10)) for core in range(count)}


def literal(n,c,a,tag):
    out,arithmetic=I.scalar(n,c,a,1)
    return out,arithmetic[:-16]+[tag]*n+[I.B.SENT]*16


def check(out,table,n,c,a,wg,selector):
    assert isinstance(out,list) and isinstance(table,list),'missing complete native readback'
    want_out,want_arithmetic=I.scalar(n,c,a,1)
    assert out==want_out and len(table)==n*(c+1)+16,'output size or guards differ'
    assert table[:n*c]==want_arithmetic[:-16] and table[-16:]==[I.B.SENT]*16,'arithmetic or table guards differ'
    tags=table[n*c:-16]
    if selector==19:
        assert tags==[64]*n,'SR19 allocation tag differs'
        return dict(allocation_tag_exact=True)
    assert selector==20 and all(v in VALID_CORES for v in tags),'invalid/missing core tag'
    assert all(len(set(tags[j:j+wg]))==1 for j in range(0,n,wg)),'core identity differs within a workgroup'
    groups=Counter(tags[::wg]);assert sum(groups.values())==n//wg
    cluster=Counter()
    for core,count in groups.items():cluster[core>>4]+=count
    return dict(core_ids_valid=True,workgroups_uniform=True,cores_seen=len(groups),
        workgroups_per_core=dict(sorted(groups.items())),workgroups_per_cluster=dict(sorted(cluster.items())),
        minimum_workgroups_on_used_core=min(groups.values()),maximum_workgroups_on_used_core=max(groups.values()),
        final_dispatch_only=True)


def construct(n,c,a,selector):
    e,mov,store=P.RS.e,P.RS.mov,P.RS.agx_loop.store
    body=e('iadd r20, r1, 0')+b''.join(mov(10+j,100+7*j) for j in range(c))
    for j in range(a):body+=e(f'iadd r{10+j%c}, r{10+j%c}, 1')
    for j in range(c):body+=mov(28,j*n)+e('iadd r29, r20, r28')+store(10+j,8,29)+e('wait 0')
    pc=P.drm.control_main()[1]+len(body)
    body+=P.bench.get_sr(selector,30)+mov(28,c*n)+e('iadd r29, r20, r28')+store(30,8,29)+e('wait 0')+e('stop')
    code=P.drm.build_main(body);P.cov.gate(code)
    at=0;bounds=[]
    while at<len(code):
        info=P.cov.ASMB.info(code[at:at+16]);assert info and info[0] in ('get_sr','iadd','mov_imm','if_icmp','device_store','wait','stop','pop_exec')
        bounds.append(at);at+=info[1]
    assert at==len(code) and len(code)<65536 and code[pc:pc+4]==P.bench.get_sr(selector,30)
    return code,bounds,pc


def build(n,c,a,wg,k,selector):
    assert n in (32,131072) and c in (1,8) and a in (1024,4096)
    assert wg in (32,128) and n%wg==0 and k in (4,64) and selector in (19,20)
    P.cov.install();code,bounds,pc=construct(n,c,a,selector)
    twin,_,twin_pc=construct(n,c,a,39-selector)
    assert len(code)==len(twin) and pc==twin_pc
    difference=int.from_bytes(code,'little')^int.from_bytes(twin,'little')
    assert difference==(19^20)<<(8*pc+16),'twins differ outside the selector'
    control,_,_=construct(n,c,0,19);table=[I.B.SENT]*(n*(c+1)+16)
    expected=literal(n,c,0,64);assert P.cov.simulate(control,n,wg,64,0,table)==expected
    previous=table;model_expected=literal(n,c,a,64 if selector==19 else 0)
    for _ in range(3):
        actual=P.cov.simulate(code,n,wg,64,0,previous)
        assert actual==model_expected
        check(*actual,n,c,a,wg,selector);previous=actual[1]
    return dict(code=code,control=control,table=table,n=n,wg=wg,regs=64,expected=expected,
        gate=dict(base_gate=dict(lanes=n,chains=c,adds=a,wg=wg,selector=selector,increment=1,register_halves=64,
            code_bytes=len(code),boundaries=bounds,selector_pc=pc,twins_differ_only_in_selector=True,maximum_result=100+a),
            repeats=k,simulator_complete_scalar_exact=True,repeat_invariance_exact=True,
            core_plane_uses_properties_on_hardware=selector==20,intermediate_buffers_captured=False,
            builder_sha256=S.sha(Path(__file__)),arithmetic_builder_sha256=S.sha(Path(I.__file__)),
            sr_encoder_sha256=S.sha(Path(P.bench.get_sr.__code__.co_filename)),
            train_runner_sha256=S.sha(Path(T.__file__)),shared_runner_sha256=S.sha(Path(H.__file__)),
            native_source_sha256=S.sha(S.NATIVE),gap_us=1000))


def run(p,trial,exe):
    with T.GPU_LOCK.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('another timing worker holds GPU lock; no submission')
        return _run(p,trial,exe)


def _run(p,trial,exe):
    b=p['gate']['base_gate'];k=p['gate']['repeats'];selector=b['selector'];c=b['chains'];a=b['adds']
    name=f'integer-core-s{selector}-n{p["n"]}-w{p["wg"]}-c{c}-a{a}-k{k}-t{trial}'
    DATA.mkdir(parents=True,exist_ok=True);path=DATA/(name+'.json.gz');assert not path.exists(),'refusing evidence overwrite'
    P.gpu_safety.require_budget(1);directory=SCRATCH/name;directory.mkdir(parents=True)
    wrapper=directory/'launch';wrapper.write_text('#!/bin/sh\nexport AGX_REPEAT_GAP_US=1000\nexec '+shlex.quote(str(exe))+' "$@"\n');wrapper.chmod(0o755)
    runner=SimpleNamespace(out=directory,exe=wrapper)
    r=dict(name=name,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),before=P.snapshot(),
        code=p['code'].hex(),control_code=p['control'].hex(),table_in=p['table'],n=p['n'],wg=p['wg'],regs=p['regs'],gate=p['gate'],
        native_binary_sha256=S.sha(exe),simulator_sha256=S.sha(P.cov.RUN),wrapper_text=wrapper.read_text(),wrapper_sha256=S.sha(wrapper))
    log=Path('/save/kernel.log');start=log.stat().st_size
    def save():
        r['after']=P.snapshot();r['kernel_log_delta']=log.read_bytes()[start:].decode(errors='replace')
        with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as f:f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    def stop(reason):r['halted']=reason;save();raise RuntimeError(reason)
    r['phase']='pre-control';save();r['control_before']=H.run_one(runner,p['control'],p,'control-before')
    if not H.matches(r['control_before'],p['expected']):stop('pre-control failed; no candidate submission')
    r['phase']='train';save();r['train']=T.train(runner,p,k);save()
    if r['train'].get('host_process_stuck'):stop('probe remains blocked; no recovery submission')
    if not r['train']['ok']:time.sleep(2)
    r['phase']='recovery-control';save();r['control_after']=H.run_one(runner,p['control'],p,'control-after')
    r['recovery_control_passed']=H.matches(r['control_after'],p['expected'])
    if not r['recovery_control_passed']:stop('recovery failed; no further submissions')
    if not r['train']['ok']:stop('candidate did not complete; stop batch')
    try:r['final_buffer_checks']=check(r['train'].get('out'),r['train'].get('table_after'),p['n'],c,a,p['wg'],selector)
    except AssertionError as error:stop('final-buffer check failed: '+str(error))
    r['arithmetic_and_guards_exact']=True;r['phase']='finished';save()
    print(json.dumps(dict(name=name,checked=True,recovery=True,cores=r['final_buffer_checks'].get('cores_seen'),
        max_wgs=r['final_buffer_checks'].get('maximum_workgroups_on_used_core'),budget=r['after']['budget_used'])),flush=True)
    return r


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--matrix',action='store_true');ap.add_argument('--hardware',action='store_true')
    args=ap.parse_args()
    if args.matrix:
        if args.hardware:
            for c in (1,8):
                for sr in (19,20):
                    r=json.load(gzip.open(DATA/f'integer-core-s{sr}-n32-w32-c{c}-a4096-k4-t0.json.gz'))
                    assert r['phase']=='finished' and r['arithmetic_and_guards_exact'] and r['recovery_control_passed'] and not r.get('halted')
        programs={}
        for c in (1,8):
            for a in (1024,4096):
                for sr in (19,20):
                    programs[c,a,sr]=build(131072,c,a,128,64,sr);print('GATED',c,a,sr,flush=True)
        if not args.hardware:return
        exe=S.native();print('ALL GATES PASSED; serial matrix',flush=True)
        for trial in range(3):
            keys=list(programs);random.Random(20261020+trial).shuffle(keys)
            for key in keys:run(programs[key],trial,exe)
    else:
        for c in (1,8):
            for sr in (19,20):
                p=build(32,c,4096,32,4,sr);print('PILOT GATED',c,sr,flush=True)
                if args.hardware:run(p,0,S.native())


if __name__=='__main__':main()
