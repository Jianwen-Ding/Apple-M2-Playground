#!/usr/bin/env python3
"""Bounded unsafe probes; simulator-gated surrounding code, recorded faults and recovery controls.

Default: offline. --hardware submits one selected variant. A fault is recorded,
then a known-good control checks recovery; failed recovery ends the session.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import probe_ret_landing as P

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'results/2026-10-17-call-ret/followup'
SCRATCH = Path('/scratch/apple-m2-playground/control-followup')


def case(name):
    P.cov.install()
    P.RET_PC, P.VALUE, P.LANDINGS = 512, 1024, (1024, 1536, 2048, 2560)
    maps = ('ret-byte-buffer', 'ret-shift-pc', 'ret-shift-value', 'ret-byte-nopop')
    if name in ('ret-pop0', 'ret-pop1', 'ret-pop3', 'ret-r1-pop1') + maps:
        if name in maps:
            P.RET_PC = 768 if name == 'ret-shift-pc' else 512
            P.VALUE = 0x2500 if name == 'ret-shift-value' else 0x2400
            v, pc = P.VALUE, P.RET_PC
            P.LANDINGS = tuple(sorted({v - 0x2000, pc + v - 0x2000, 1536, v, pc + v,
                                       2*v - 0x2000, pc + 2*v - 0x2000, 2*v, pc + 2*v}))
        reenable = None if name == 'ret-byte-nopop' else (1 if name in maps else int(name[-1]))
        code, control = P.build(reenable=reenable)
        if name == 'ret-r1-pop1':
            code = code[:P.RET_PC] + P.RS.e('ret r1') + code[P.RET_PC + 2:]
        gate = P.gate(code, control)
        return dict(code=code, control=control, table=P.TABLE, n=32, wg=32, regs=64,
                    expected=P.expected(1), gate=gate, ret_pc=P.RET_PC, target=P.VALUE)
    raise ValueError(name)


def run_one(runner, code, p, label):
    """Retain full stdout/stderr, timestamps and even partial failed readbacks."""
    d = runner.out / label
    d.mkdir()
    (d / 'code.bin').write_bytes(code + bytes(16))
    (d / 'table.bin').write_bytes(struct.pack(f"<{len(p['table'])}I", *p['table']))
    argv = [str(runner.exe), '/dev/dri/renderD128', str(d / 'code.bin'), str(p['n']), str(d / 'out.bin'), '1',
            str(p['regs']), str(d / 'table.bin')]
    env = {'PATH': '/usr/bin', 'AGX_LOCAL_X': str(p['wg']), 'AGX_TABLE_OUT': str(d / 'table-out.bin')}
    before = len(P.gpu_safety.used())
    try:
        run = subprocess.run(argv, env=env, capture_output=True, timeout=10)
        r = dict(returncode=run.returncode, stdout=run.stdout.decode(errors='replace'), stderr=run.stderr.decode(errors='replace'))
    except subprocess.TimeoutExpired as ex:
        r = dict(returncode=None, host_timeout=True, stdout=(ex.stdout or b'').decode(errors='replace'),
                 stderr=(ex.stderr or b'').decode(errors='replace'))
    lines = [json.loads(s) for s in r['stdout'].splitlines() if s.startswith('{')]
    smp = [s for s in lines if 'rep' in s]
    r['ok'] = r['returncode'] == 0 and len(smp) == 1 and all(smp[0]['fw_ts'])
    r['samples'] = smp
    for file, key in (('out.bin', 'out'), ('table-out.bin', 'table_after')):
        f = d / file
        if f.exists():
            b = f.read_bytes()
            r[key] = list(struct.unpack(f'<{len(b)//4}I', b))
    if r['ok']:
        r['fw_ns'] = smp[0]['fw_ts'][1] - smp[0]['fw_ts'][0]
    elif smp or r.get('host_timeout'):
        if len(P.gpu_safety.used()) == before:
            P.gpu_safety.record(f'control-followup {runner.out.name}/{label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(name, p):
    path = DATA / f'{name}.json.gz'
    if path.exists():
        raise SystemExit(f'refusing to overwrite {path}')
    P.gpu_safety.require_budget(1)
    DATA.mkdir(parents=True, exist_ok=True)
    runner = P.bench.Runner(SCRATCH / name)
    rec = dict(name=name, utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), before=P.snapshot(),
               code=p['code'].hex(), control_code=p['control'].hex(), table_in=p['table'], n=p['n'], wg=p['wg'],
               regs=p['regs'], gate=p['gate'], script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               simulator_sha256=hashlib.sha256(P.cov.RUN.read_bytes()).hexdigest())
    start = Path('/save/kernel.log').stat().st_size

    def save():
        rec['after'] = P.snapshot()
        rec['kernel_log_delta'] = Path('/save/kernel.log').read_bytes()[start:].decode(errors='replace')
        with gzip.GzipFile(filename=str(path), mode='wb', mtime=0) as f:
            f.write((json.dumps(rec, sort_keys=True) + '\n').encode())

    rec['control_before'] = run_one(runner, p['control'], p, 'control-before')
    if not matches(rec['control_before'], p['expected']):
        rec['halted'] = 'pre-control failed; no variant submitted'
        save()
        return rec
    rec['variant'] = run_one(runner, p['code'], p, 'variant')
    save()
    if not rec['variant']['ok']:
        time.sleep(2)
    rec['control_after'] = run_one(runner, p['control'], p, 'control-after')
    rec['recovery_control_passed'] = matches(rec['control_after'], p['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established, no more submissions'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case')
    ap.add_argument('--hardware', action='store_true')
    a = ap.parse_args()
    p = case(a.case)
    print(json.dumps({'case': a.case, 'gate': p['gate']}), flush=True)
    if a.hardware:
        r = hardware(a.case, p)
        v = r.get('variant', {})
        print(json.dumps({'case': a.case, 'variant_ok': v.get('ok'), 'fw_ns': v.get('fw_ns'),
                          'markers': sorted(set(v.get('table_after', [])[32:64])),
                          'recovery_control_passed': r.get('recovery_control_passed'),
                          'halted': r.get('halted'), 'budget_used': r['after']['budget_used']}), flush=True)
        if r.get('halted'):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
