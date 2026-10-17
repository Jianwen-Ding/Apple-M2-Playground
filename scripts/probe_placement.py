#!/usr/bin/env python3
"""Priority F (part 2): code placement via AGX_CODE_OFF / AGX_CALL_BASE.

Runs the established uniform direct call/return round trip
(probe_control_followup.roundtrip) with the code blob at USC offset 0x2100
instead of 0x2000. Links should shift by +0x100 (buffer-relative); relative
direct calls should behave identically.

Default: offline simulator validation only (AGX_CALL_BASE=0x2100). --hardware
submits with AGX_CODE_OFF=0x2100.
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
import run_bench as bench
import gpu_safety
import probe_control_followup as F

DATA = ROOT / 'results/2026-10-17-call-ret'
SCRATCH = Path('/scratch/apple-m2-playground/code-placement')

CODE_OFF = 0x2100


def build_probe():
    # Build with the stock base: the code bytes are base-independent (direct
    # call offsets are relative; ret reads the link at runtime). Only the
    # expected link VALUES shift with the base.
    F.P.cov.install()
    p = F.roundtrip(indirect=False, nested=False)
    # Expected links shift by CODE_OFF - 0x2000 relative to the stock probe.
    shift = CODE_OFF - 0x2000
    exp_out, exp_tab = p['expected']
    link0 = exp_tab[64]
    assert link0 == 0x2000 + p['gate']['call_pc'] + 6, f"unexpected base link {link0:#x}"
    exp_tab_shifted = [(v + shift) if v == link0 else v for v in exp_tab]
    return dict(p, expected=(exp_out, exp_tab_shifted), code_off=CODE_OFF,
                gate=dict(p['gate'], code_off=CODE_OFF, link_shift=shift))


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
    env = {'PATH': '/usr/bin', 'AGX_LOCAL_X': str(p['wg']), 'AGX_TABLE_OUT': str(d / 'table-out.bin'),
           'AGX_CODE_OFF': hex(p['code_off'])}
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
            gpu_safety.record(f'code-placement {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    name = 'code-placement-2100'
    path = DATA / f'{name}.json.gz'
    if path.exists():
        raise SystemExit(f'refusing to overwrite {path}')
    gpu_safety.require_budget(1)
    DATA.mkdir(parents=True, exist_ok=True)
    runner = bench.Runner(SCRATCH / name)
    rec = dict(
        name=name,
        utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        before={'budget_used': len(gpu_safety.used()), 'boot_id': gpu_safety.boot_id()},
        code=p['code'].hex(), control_code=p['control'].hex(),
        table_in=p['table'], n=p['n'], wg=p['wg'], regs=p['regs'],
        gate=p['gate'],
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        simulator_sha256=hashlib.sha256(cov.RUN.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256((bench.REPO / 'tests/drm_compute.c').read_bytes()).hexdigest(),
    )
    start = Path('/save/kernel.log').stat().st_size

    def save():
        rec['after'] = {'budget_used': len(gpu_safety.used()), 'boot_id': gpu_safety.boot_id()}
        rec['kernel_log_delta'] = Path('/save/kernel.log').read_bytes()[start:].decode(errors='replace')
        with gzip.GzipFile(filename=str(path), mode='wb', mtime=0) as f:
            f.write((json.dumps(rec, sort_keys=True) + '\n').encode())

    rec['phase'] = 'variant'
    save()
    # The program is its own control: the uniform round trip is established.
    # Run it twice; both must match the shifted oracle.
    rec['run1'] = run_one(runner, p['code'], p, 'run1')
    if not matches(rec['run1'], p['expected']):
        rec['halted'] = 'run1 failed; no second run submitted'
        save()
        return rec
    rec['phase'] = 'run2'
    save()
    rec['run2'] = run_one(runner, p['code'], p, 'run2')
    rec['recovery_control_passed'] = matches(rec['run2'], p['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'run2 failed; placement behavior not confirmed'
    else:
        exp_out, exp_tab = p['expected']
        got = rec['run1'].get('table_after', [])
        link_vals = {got[i] for i in range(64, 96)} if len(got) >= 96 else set()
        rec['interpretation'] = ('placement_independent_links_shifted'
                                 if link_vals == {CODE_OFF + p['gate']['call_pc'] + 6}
                                 else f'unexpected_links_{sorted(hex(v) for v in link_vals)[:4]}')
    rec['phase'] = 'finished'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    args = ap.parse_args()
    print('=== Building and validating probe ===')
    probe = build_probe()
    print(f"  call_pc={probe['gate']['call_pc']:#x} code_off={probe['gate']['code_off']:#x}")
    # Validate the shifted program in the simulator with the shifted base.
    old_base = os.environ.get('AGX_CALL_BASE')
    old_model = os.environ.get('AGX_EXPERIMENTAL_RET')
    os.environ['AGX_CALL_BASE'] = hex(CODE_OFF)
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        F.P.cov.install()
        out, tab = F.P.cov.simulate(probe['code'], probe['n'], probe['wg'],
                                     probe['regs'], 0, probe['table'])
        assert (out, tab) == probe['expected'], "shifted simulation mismatch"
        print("  Shifted-base simulation matches shifted oracle.")
    finally:
        if old_base is None:
            del os.environ['AGX_CALL_BASE']
        else:
            os.environ['AGX_CALL_BASE'] = old_base
        if old_model is None:
            del os.environ['AGX_EXPERIMENTAL_RET']
        else:
            os.environ['AGX_EXPERIMENTAL_RET'] = old_model
    if args.mode == 'offline':
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f"  Run1 ok: {rec['run1'].get('ok')}")
    print(f"  Run2 ok: {rec.get('recovery_control_passed')}")
    print(f"  Interpretation: {rec.get('interpretation')}")
    print(f"  Saved to: {DATA / 'code-placement-2100.json.gz'}")


if __name__ == '__main__':
    main()
