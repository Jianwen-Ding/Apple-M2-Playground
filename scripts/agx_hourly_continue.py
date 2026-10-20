#!/usr/bin/env python3
"""Local hourly same-thread continuation via the installed Codex queue CLI.

This is a host timer, not the ChatGPT Scheduled service. Runtime state lives
in scratch. A read-only goal-status check respects pauses, limits and stops;
one file lock prevents duplicate timer processes. No model/GPU worker is run.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

DEFAULT_STATE=Path('/scratch/apple-m2-playground/hourly-continuation')
PROMPT=("Hourly continuation requested by the owner: Continue the active AGX ISA goal in /save/workspace. "
        "Read AGENTS.md and durable handoff/evidence; preserve current work. Document functionality/performance "
        "and keep AGX-Performance-Simulator aligned. Gate complete programs in simulation with independent "
        "oracles before hardware; use bounded watchdogs and exact recovery controls. Investigate, preserve and "
        "push fault/hang diagnostics; commit/push completed work. Do not start parallel GPU workers. Respect "
        "later stop/pause instructions, limits and unsafe states. Failed recovery or a blocked probe means "
        "host-only diagnostics. Continue useful work while the goal remains active.")


def save(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def goal_status(task):
    with sqlite3.connect('file:'+task['goal_database']+'?mode=ro',uri=True,timeout=5) as db:
        row=db.execute('SELECT status FROM thread_goals WHERE thread_id=?',(task['thread_id'],)).fetchone()
    return row[0] if row else 'missing'


def enqueue(task,dry_run=False):
    status=goal_status(task)
    result=dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),goal_status=status,dry_run=dry_run)
    if not task.get('enabled') or status!='active':return dict(result,action='skipped')
    argv=[task['codex'],'queue','--thread',task['thread_id'],'--message',task['prompt']]
    if dry_run:return dict(result,action='would_queue',thread_id=task['thread_id'],interval_seconds=task['interval_seconds'])
    try:
        completed=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30,cwd='/save/workspace')
        return dict(result,action='queued' if completed.returncode==0 else 'queue_failed',returncode=completed.returncode,
                    stdout=completed.stdout[-4000:],stderr=completed.stderr[-4000:])
    except (OSError,subprocess.TimeoutExpired) as error:return dict(result,action='queue_failed',error=str(error))


def run(directory):
    with (directory/'worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        save(directory/'worker.json',dict(pid=os.getpid(),started=time.time()))
        while True:
            task=json.loads((directory/'task.json').read_text())
            if not task['enabled']:return
            remaining=task['next_run']-time.time()
            if remaining>0:time.sleep(min(remaining,30));continue
            result=enqueue(task);print(json.dumps(result),flush=True)
            # Re-read after the bounded enqueue so an intervening stop stays stopped.
            current=json.loads((directory/'task.json').read_text())
            current['last_result']=result
            current['next_run']=task['next_run']+task['interval_seconds']
            if current['next_run']<=time.time():current['next_run']=time.time()+task['interval_seconds']
            save(directory/'task.json',current)
            if result['goal_status']=='complete':return


def worker_alive(directory):
    lockpath=directory/'worker.lock'
    if not lockpath.exists():return False
    with lockpath.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
    return False


def status(directory):
    task=json.loads((directory/'task.json').read_text())
    return dict(enabled=task['enabled'],worker_running=worker_alive(directory),thread_id=task['thread_id'],
                interval_seconds=task['interval_seconds'],goal_status=goal_status(task),
                next_run_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(task['next_run'])),last_result=task.get('last_result'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=('install','run','status','stop','check'))
    ap.add_argument('--state-dir',type=Path,default=DEFAULT_STATE)
    ap.add_argument('--thread')
    args=ap.parse_args();directory=args.state_dir
    if args.command=='install':
        assert args.thread,'--thread is required for install'
        directory.mkdir(parents=True,exist_ok=True)
        if worker_alive(directory):
            assert json.loads((directory/'task.json').read_text())['thread_id']==args.thread,'existing timer belongs to another thread'
            print(json.dumps(status(directory)));return
        now=time.time();codex=shutil.which('codex');assert codex,'Codex CLI unavailable'
        codex_home=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
        task=dict(version=1,title='Continue AGX ISA research',enabled=True,thread_id=args.thread,
                  interval_seconds=3600,created=now,next_run=now+3600,codex=codex,
                  goal_database=str(codex_home/'goals_1.sqlite'),prompt=PROMPT)
        assert goal_status(task)=='active','only an active existing goal can be scheduled'
        assert len(PROMPT.encode())<=1000
        save(directory/'task.json',task)
        with (directory/'worker.log').open('a') as log:
            subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run','--state-dir',str(directory.resolve())],
                             stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        for _ in range(20):
            if worker_alive(directory):break
            time.sleep(.05)
        assert worker_alive(directory),'timer process failed to start'
        print(json.dumps(status(directory)));return
    if args.command=='run':run(directory)
    elif args.command=='status':print(json.dumps(status(directory)))
    elif args.command=='check':print(json.dumps(enqueue(json.loads((directory/'task.json').read_text()),True)))
    else:
        task=json.loads((directory/'task.json').read_text());task['enabled']=False;save(directory/'task.json',task)
        print(json.dumps(dict(enabled=False,worker_exits_within_seconds=30)))


if __name__=='__main__':main()
