#!/usr/bin/env python3
"""Bounded consecutive repetitions of established ordinary arithmetic shaders.

One harness process, no second GPU worker. Each dispatch resets its registers
to the same small positive seeds; the table is output-only. Full final buffers
and exact single-dispatch controls are checked. Per-dispatch timestamps remain
available, but intermediate table buffers are not captured by this harness.
"""
import argparse
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time
import probe_integer_chain_cost as B

P,H=B.P,B.H
DATA=B.ROOT/'results/2026-10-20-integer-chain-train'
SCRATCH=Path('/scratch/apple-m2-playground/integer-chain-train')
GPU_LOCK=Path('/scratch/apple-m2-playground/ordinary-timing-gpu.lock')


def build(n,chains,adds,wg,repeats):
    assert repeats in (4,16,64)
    p=B.build(n,chains,adds,wg)
    result=B.oracle(n,chains,adds)
    # Two more invocations start with the preceding table result. There are no
    # table loads; initialized register seeds make every invocation independent.
    previous=result[1]
    for _ in range(2):
        actual=P.cov.simulate(p['code'],n,wg,64,0,previous)
        assert actual==result,'repeat-invariance gate failed';previous=actual[1]
    p['gate']=dict(base_gate=p['gate'],repeats=repeats,repeat_invariance_exact=True,
        final_buffer_oracle_exact=True,intermediate_buffers_captured=False,
        base_builder_sha256=hashlib.sha256(Path(B.__file__).read_bytes()).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return p


def train(runner,p,repeats):
    directory=runner.out/'train';directory.mkdir()
    (directory/'code.bin').write_bytes(p['code']+bytes(16))
    (directory/'table.bin').write_bytes(struct.pack(f'<{len(p["table"])}I',*p['table']))
    argv=[str(runner.exe),'/dev/dri/renderD128',str(directory/'code.bin'),str(p['n']),str(directory/'out.bin'),str(repeats),str(p['regs']),str(directory/'table.bin')]
    env={'PATH':'/usr/bin','AGX_LOCAL_X':str(p['wg']),'AGX_TABLE_OUT':str(directory/'table-out.bin')}
    before=len(P.gpu_safety.used());r=H.run_bounded(argv,env)
    events=[]
    for line in r['stdout'].splitlines():
        if line.startswith('{'):
            try:events.append(json.loads(line))
            except json.JSONDecodeError:r.setdefault('incomplete_json_lines',[]).append(line)
    samples=[x for x in events if 'rep' in x];r['samples']=samples
    r['completion']=[x for x in events if x.get('completed')]
    r['ok']=(r['returncode']==0 and not r.get('host_timeout') and not r.get('incomplete_json_lines')
        and len(samples)==repeats and [s['rep'] for s in samples]==list(range(repeats))
        and all(s['wait']==s['errno']==0 and 0<s['fw_ts'][0]<s['fw_ts'][1] for s in samples)
        and len(r['completion'])==1 and r['completion'][0]['repeats']==repeats)
    for file,key in (('out.bin','out'),('table-out.bin','table_after')):
        path=directory/file
        if path.exists():
            content=path.read_bytes();whole=len(content)//4*4
            r[key]=list(struct.unpack(f'<{whole//4}I',content[:whole]))
            if whole!=len(content):r[key+'_partial_tail_hex']=content[whole:].hex();r['ok']=False
    if not r['ok'] and (samples or r.get('host_timeout')) and len(P.gpu_safety.used())==before:
        P.gpu_safety.record('ordinary arithmetic repetition train '+runner.out.name)
    return r


def hardware(p,trial):
    with GPU_LOCK.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('another ordinary timing train owns the GPU lock; no submission')
        return _hardware(p,trial)


def _hardware(p,trial):
    base=p['gate']['base_gate'];repeats=p['gate']['repeats']
    prefix=p.get('train_prefix','integer-train')
    name=f'{prefix}-n{p["n"]}-w{p["wg"]}-c{base["chains"]}-a{base["adds"]}-k{repeats}-t{trial}'
    data=p.get('train_data_dir',DATA)
    path=data/f'{name}.json.gz';assert not path.exists(),'refusing to overwrite evidence'
    P.gpu_safety.require_budget(1);data.mkdir(parents=True,exist_ok=True)
    runner=P.bench.Runner(p.get('train_scratch',SCRATCH)/name)
    r=dict(name=name,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),before=P.snapshot(),
        code=p['code'].hex(),control_code=p['control'].hex(),table_in=p['table'],n=p['n'],wg=p['wg'],regs=p['regs'],gate=p['gate'],
        simulator_sha256=hashlib.sha256(P.cov.RUN.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256((P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest())
    log=Path('/save/kernel.log');start=log.stat().st_size
    def save():
        r['after']=P.snapshot();r['kernel_log_delta']=log.read_bytes()[start:].decode(errors='replace')
        with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as f:f.write((json.dumps(r,sort_keys=True)+'\n').encode())
    r['phase']='pre-control';save()
    r['control_before']=H.run_one(runner,p['control'],p,'control-before')
    if not H.matches(r['control_before'],p['expected']):r['halted']='pre-control failed';save();return r
    r['phase']='train';save();r['train']=train(runner,p,repeats);save()
    if r['train'].get('host_process_stuck'):r['halted']='probe remains blocked; no recovery submission';save();return r
    if not r['train']['ok']:time.sleep(2)
    r['phase']='recovery-control';save()
    r['control_after']=H.run_one(runner,p['control'],p,'control-after')
    r['recovery_control_passed']=H.matches(r['control_after'],p['expected'])
    if not r['recovery_control_passed']:r['halted']='recovery failed; no further submissions'
    if r['train']['ok']:
        expected=p.get('final_expected')
        if expected is None:expected=B.oracle(p['n'],base['chains'],base['adds'])
        r['final_arithmetic_exact']=(r['train']['out'],r['train']['table_after'])==expected
        ns=[s['fw_ts'][1]-s['fw_ts'][0] for s in r['train']['samples']]
        r['timing']=dict(ns=ns,first_ns=ns[0],last_ns=ns[-1],minimum_ns=min(ns),maximum_ns=max(ns),
            first_quarter_median_ns=statistics.median(ns[:len(ns)//4]),last_quarter_median_ns=statistics.median(ns[-len(ns)//4:]))
    r['phase']='finished';save();return r


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lanes',type=int,choices=(32,32768,131072),default=32)
    ap.add_argument('--chains',type=int,choices=(1,2,4,8),default=1)
    ap.add_argument('--adds',type=int,choices=(64,256,1024,2048,4096),default=64)
    ap.add_argument('--wg',type=int,choices=(32,128,256),default=32)
    ap.add_argument('--repeats',type=int,choices=(4,16,64),default=4)
    ap.add_argument('--trial',type=int,default=0);ap.add_argument('--hardware',action='store_true')
    a=ap.parse_args();p=build(a.lanes,a.chains,a.adds,a.wg,a.repeats)
    print(json.dumps(dict(gates=True,lanes=a.lanes,chains=a.chains,adds=a.adds,repeats=a.repeats)),flush=True)
    if not a.hardware:return
    r=hardware(p,a.trial);timing=r.get('timing',{})
    print(json.dumps(dict(exact=r.get('final_arithmetic_exact'),samples=len(r.get('train',{}).get('samples',[])),
        first=timing.get('first_ns'),first_quarter=timing.get('first_quarter_median_ns'),last_quarter=timing.get('last_quarter_median_ns'),
        recovery=r.get('recovery_control_passed'),halted=r.get('halted'),budget=r['after']['budget_used'])),flush=True)
    if r.get('halted') or not r.get('final_arithmetic_exact'):raise SystemExit(2)


if __name__=='__main__':main()
