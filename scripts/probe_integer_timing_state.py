#!/usr/bin/env python3
"""Identical arithmetic shaders with controlled, bounded host submission gaps."""
import argparse
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
from types import SimpleNamespace
import probe_integer_immediate_cost as I

T,P,H=I.T,I.P,I.T.H
ROOT=I.B.ROOT
DATA=ROOT/'results/2026-10-20-integer-timing-state'
SCRATCH=Path('/scratch/apple-m2-playground/integer-timing-state')
NATIVE=ROOT/'experiments/arithmetic/drm_integer_timing.c'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def native():
    SCRATCH.mkdir(parents=True,exist_ok=True)
    exe=SCRATCH/('drm_integer_timing-'+sha(NATIVE))
    if not exe.exists():subprocess.run(['cc','-std=c11','-O2',str(NATIVE),'-I',str(P.bench.REPO/'tests'),'-o',str(exe)],check=True)
    return exe


def build(n,chains,adds,wg,repeats,gap):
    assert gap in (0,250,1000)
    p=I.build(n,chains,adds,wg,repeats,1)
    p['gate']['timing_state']=dict(gap_us=gap,builder_sha256=sha(Path(__file__)),
        arithmetic_builder_sha256=sha(Path(I.__file__)),train_runner_sha256=sha(Path(T.__file__)),
        native_source_sha256=sha(NATIVE),origin_harness_sha256=sha(P.bench.REPO/'tests/drm_compute.c'))
    return p


def run(p,trial,exe):
    with T.GPU_LOCK.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('another timing worker holds GPU lock; no submission')
        return _run(p,trial,exe)


def _run(p,trial,exe):
    b=p['gate']['base_gate'];k=p['gate']['repeats'];gap=p['gate']['timing_state']['gap_us']
    name=f'integer-state-n{p["n"]}-w{p["wg"]}-c{b["chains"]}-a{b["adds"]}-g{gap}-k{k}-t{trial}'
    DATA.mkdir(parents=True,exist_ok=True);path=DATA/(name+'.json.gz')
    assert not path.exists(),'refusing to overwrite evidence'
    P.gpu_safety.require_budget(1)
    directory=SCRATCH/name;directory.mkdir()
    wrapper=directory/'launch';wrapper.write_text('#!/bin/sh\nexport AGX_REPEAT_GAP_US='+str(gap)+'\nexec '+shlex.quote(str(exe))+' "$@"\n');wrapper.chmod(0o755)
    runner=SimpleNamespace(out=directory,exe=wrapper)
    r=dict(name=name,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),before=P.snapshot(),
        code=p['code'].hex(),control_code=p['control'].hex(),table_in=p['table'],n=p['n'],wg=p['wg'],regs=p['regs'],gate=p['gate'],
        native_binary_sha256=sha(exe),wrapper_text=wrapper.read_text(),wrapper_sha256=sha(wrapper),simulator_sha256=sha(P.cov.RUN))
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
    r['final_arithmetic_exact']=(r['train'].get('out'),r['train'].get('table_after'))==p['final_expected']
    r['phase']='finished';save()
    print(json.dumps(dict(name=name,exact=r['final_arithmetic_exact'],recovery=True,budget=r['after']['budget_used'])),flush=True)
    if not r['train']['ok'] or not r['final_arithmetic_exact']:raise RuntimeError('candidate failed; stop batch')
    return r


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--hardware',action='store_true')
    ap.add_argument('--lanes',type=int,default=32);ap.add_argument('--chains',type=int,default=1)
    ap.add_argument('--adds',type=int,default=64);ap.add_argument('--wg',type=int,default=32)
    ap.add_argument('--repeats',type=int,default=4);ap.add_argument('--gap',type=int,choices=(0,250,1000),default=0)
    ap.add_argument('--trial',type=int,default=0);a=ap.parse_args()
    p=build(a.lanes,a.chains,a.adds,a.wg,a.repeats,a.gap)
    print(json.dumps(dict(gates=True,source=sha(NATIVE),gap_us=a.gap)),flush=True)
    if a.hardware:run(p,a.trial,native())


if __name__=='__main__':main()
