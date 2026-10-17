#!/usr/bin/env python3
"""Decisive pop-semantics probe: mask, then a single pop, then store.

Odd lanes active (r0l=0), even lanes masked (r0l=1). A single `pop_exec r0l, 2`
followed by a store. If even lanes store, pop reactivates (OLD/max model).
If only odd lanes store, pop is a no-op on underflow (NEW model). No calls,
no returns, no other masking — the purest possible test.
"""
import argparse
import gzip
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT.parent / 'AGX-Performance-Simulator'
sys.path.insert(0, str(SIM / 'scripts'))
import coverage as cov
import record_suite as RS
import run_drm_compute as drm
import run_bench as bench
import gpu_safety

DATA = ROOT / 'results/2026-10-17-call-ret'
SCRATCH = Path('/scratch/apple-m2-playground/pop-semantics')

MARKER = 0xB0B0001
N = 32
WG = 32
REGS = 64


def build_case(pop_n):
    cov.install()
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    setup = e('iadd r29, r1, 0')
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')
    setup += mov(27, 0)
    setup += e('iadd r21, r29, r27')  # set BEFORE mask so even lanes have r21 = gid
    setup += mov(27, 1)
    setup += e('and r24, r29, r27')
    setup += e('if_icmp r0l, ueq, r24, r27, 1')  # odd active (r0l=0), even masked (r0l=1)
    setup += e(f'pop_exec r0l, {pop_n}')
    setup += mov(23, MARKER)
    setup += st(23, 8, 21)
    setup += wait
    setup += stop
    code = drm.build_main(setup)
    return code


def build_probe():
    cov.install()
    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    codes = {}
    for n in (1, 2):
        codes[n] = build_case(n)
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        outs = {}
        for n, code in codes.items():
            o, t = cov.simulate(code, N, WG, REGS, 0, table)
            outs[n] = (o, t)
            have = [i for i in range(N) if t[i] == MARKER]
            print(f'  sim pop{n}: MARK lanes = {have[:8]}{"..." if len(have) > 8 else ""} (count {len(have)})')
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']
    cov.gate(codes[2], allow=())
    return dict(codes=codes, table=table, n=N, wg=WG, regs=REGS,
                expected_out=expected_out)


def run_bounded(argv, env, timeout=10, kill_timeout=2):
    import subprocess
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    r = {'command': argv, 'environment': env, 'pid': proc.pid}
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as ex:
        r['host_timeout'] = True
        r['process_at_timeout'] = {}
        for name in ('status', 'wchan', 'maps'):
            try:
                r['process_at_timeout'][name] = Path(f'/proc/{proc.pid}/{name}').read_text()
            except OSError as error:
                r['process_at_timeout'][name] = str(error)
        proc.kill()
        try:
            out, err = proc.communicate(timeout=kill_timeout)
        except subprocess.TimeoutExpired as drain:
            r['host_process_stuck'] = True
            out, err = drain.stdout or ex.stdout or b'', drain.stderr or ex.stderr or b''
            proc.stdout.close()
            proc.stderr.close()
    r.update(returncode=proc.poll(), stdout=out.decode(errors='replace'), stderr=err.decode(errors='replace'))
    return r


def run_one(runner, code, p, label):
    d = runner.out / label
    d.mkdir()
    (d / 'code.bin').write_bytes(code + bytes(16))
    (d / 'table.bin').write_bytes(struct.pack(f"<{len(p['table'])}I", *p['table']))
    argv = [str(runner.exe), '/dev/dri/renderD128', str(d / 'code.bin'), str(p['n']), str(d / 'out.bin'), '1',
            str(p['regs']), str(d / 'table.bin')]
    env = {'PATH': '/usr/bin', 'AGX_LOCAL_X': str(p['wg']), 'AGX_TABLE_OUT': str(d / 'table-out.bin')}
    before = len(gpu_safety.used())
    r = run_bounded(argv, env)
    lines = []
    for line in r['stdout'].splitlines():
        if line.startswith('{'):
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                r.setdefault('incomplete_json_lines', []).append(line)
    smp = [s for s in lines if 'rep' in s]
    r['ok'] = (not r.get('host_timeout') and not r.get('incomplete_json_lines')
               and r['returncode'] == 0 and len(smp) == 1 and len(smp[0].get('fw_ts', [])) == 2
               and all(smp[0]['fw_ts']))
    r['samples'] = smp
    for file, key in (('out.bin', 'out'), ('table-out.bin', 'table_after')):
        f = d / file
        if f.exists():
            b = f.read_bytes()
            whole = len(b) // 4 * 4
            r[key] = list(struct.unpack(f'<{whole//4}I', b[:whole]))
            if whole != len(b):
                r[key + '_partial_tail_hex'] = b[whole:].hex()
                r['ok'] = False
    if r['ok']:
        r['fw_ns'] = smp[0]['fw_ts'][1] - smp[0]['fw_ts'][0]
    elif smp or r.get('host_timeout'):
        if len(gpu_safety.used()) == before:
            gpu_safety.record(f'pop-semantics {label}')
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    args = ap.parse_args()
    print('=== Building and validating probe ===')
    p = build_probe()
    if args.mode == 'offline':
        print('Simulator predictions above. Use hardware mode to run on GPU.')
        return
    gpu_safety.require_budget(1)
    DATA.mkdir(parents=True, exist_ok=True)
    runner = bench.Runner(SCRATCH / 'pop-semantics')
    rec = dict(name='pop-semantics', utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               before={'budget_used': len(gpu_safety.used()), 'boot_id': gpu_safety.boot_id()},
               gate={'masks': 'odd active', 'pops': [1, 2]})
    start = Path('/save/kernel.log').stat().st_size

    def save():
        rec['after'] = {'budget_used': len(gpu_safety.used()), 'boot_id': gpu_safety.boot_id()}
        rec['kernel_log_delta'] = Path('/save/kernel.log').read_bytes()[start:].decode(errors='replace')
        with gzip.GzipFile(filename=str(DATA / 'pop-semantics.json.gz'), mode='wb', mtime=0) as f:
            f.write((json.dumps(rec, sort_keys=True) + '\n').encode())

    rec['phase'] = 'pop1-control'
    save()
    c1 = run_one(runner, p['codes'][1], p, 'pop1')
    rec['pop1'] = {k: (v if k != 'samples' else len(v)) for k, v in c1.items() if k in ('ok', 'fw_ns', 'table_after')}
    if not (c1['ok'] and c1.get('table_after')):
        rec['halted'] = 'pop1 control failed; no pop2 run'
        save()
        return
    rec['phase'] = 'pop2-variant'
    save()
    v2 = run_one(runner, p['codes'][2], p, 'pop2')
    rec['pop2'] = {k: (v2[k] if k != 'table_after' else v2.get(k)) for k in ('ok', 'fw_ns', 'table_after') if k in v2}
    save()
    if v2.get('host_process_stuck'):
        rec['halted'] = 'stuck; no recovery attempt'
        save()
        return
    if not v2['ok']:
        time.sleep(2)
    rec['phase'] = 'recovery-control'
    save()
    c1b = run_one(runner, p['codes'][1], p, 'pop1-after')
    rec['recovery_control_passed'] = bool(c1b['ok'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed'
    else:
        t = v2.get('table_after', [])
        odd = sorted(i for i in range(32) if t[i] == MARKER)
        even = sorted(i for i in range(32) if False)
        rec['analysis'] = {'pop2_mark_lanes': odd}
        if set(odd) == set(range(1, 32, 2)):
            rec['interpretation'] = 'pop2_noop_on_underflow_odd_only'
        elif set(odd) == set(range(32)):
            rec['interpretation'] = 'pop2_reactivates_all'
        else:
            rec['interpretation'] = f"unexpected_{len(odd)}_lanes"
    rec['phase'] = 'finished'
    save()
    print(f"  pop1 ok: {c1['ok']}, pop2 ok: {v2.get('ok')}, recovery: {rec.get('recovery_control_passed')}")
    print(f"  Interpretation: {rec.get('interpretation')}")
    print('  Saved to:', DATA / 'pop-semantics.json.gz')


if __name__ == '__main__':
    main()
