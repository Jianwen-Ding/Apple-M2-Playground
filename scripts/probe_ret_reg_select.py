#!/usr/bin/env python3
"""Priority A: explicit return-register selection.

Determines whether `ret rX` uses the explicit operand register rX or an
implicit link register (r1). Sets r1 and r30 to different buffer-relative
addresses pointing to distinct landing blocks with unique markers.

Default: offline simulator validation only.  --hardware submits the probe.

Probe: r1 -> landing A (0xBBBB0001), r30 -> landing B (0xCCCC0001), `ret r30`
  - If hardware lands at B: explicit operand (r30) is used
  - If hardware lands at A: implicit r1 is used
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
SCRATCH = Path('/scratch/apple-m2-playground/ret-reg-select')

# Layout constants (code array byte offsets)
LANDING_A_OFFSET = 1024
LANDING_B_OFFSET = 1536
MARKER_PRE = 0xAAAA0001   # pre-return marker
MARKER_A = 0xBBBB0001     # landing A marker (implicit r1 hypothesis)
MARKER_B = 0xCCCC0001     # landing B marker (explicit r30 hypothesis)
N = 32
WG = 32
REGS = 64


def build_probe():
    """Build variant (ret r30) and control programs for the register-selection probe.

    Returns dict with code, control, table, expected, gate, etc.
    """
    cov.install()
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')

    # Setup: compute store addresses from r1 (set by harness prologue)
    setup = e('iadd r20, r1, 0')           # r20 = base for stores
    setup += mov(21, 32)
    setup += e('iadd r21, r20, r21')        # r21 = base + 32 (marker store addr)

    # Store pre-return marker
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)
    setup += wait

    # Set r1 and r30 to different landing addresses
    # Register values are buffer-relative: 0x2000 + code_array_byte_offset
    setup += mov(1, 0x2000 + LANDING_A_OFFSET)   # r1 -> landing A
    setup += mov(30, 0x2000 + LANDING_B_OFFSET)  # r30 -> landing B

    site = drm.control_main()[1]
    ret_pc = site + len(setup)

    # ret r30 instruction (2 bytes) + 2 waits = 6-byte island
    ret_instr = e('ret r30')
    after_ret = wait + wait

    # Landing A block: pop_exec, marker A, store, wait, stop
    landing_a = e('pop_exec r0l, 2')
    landing_a += mov(23, MARKER_A)
    landing_a += st(23, 8, 21)
    landing_a += wait
    landing_a += stop

    # Landing B block: pop_exec, marker B, store, wait, stop
    landing_b = e('pop_exec r0l, 2')
    landing_b += mov(23, MARKER_B)
    landing_b += st(23, 8, 21)
    landing_b += wait
    landing_b += stop

    # Assemble the full user code with padding
    body = setup + ret_instr + after_ret

    # Pad to LANDING_A_OFFSET with stops
    pad_a_len = LANDING_A_OFFSET - len(body)
    assert pad_a_len >= 0 and pad_a_len % 2 == 0, f"setup too long: {len(body)} > {LANDING_A_OFFSET}"
    body += stop * (pad_a_len // 2)
    body += landing_a

    # Pad to LANDING_B_OFFSET with stops
    pad_b_len = LANDING_B_OFFSET - len(body)
    assert pad_b_len >= 0 and pad_b_len % 2 == 0, f"landing A too long: {len(body)} > {LANDING_B_OFFSET}"
    body += stop * (pad_b_len // 2)
    body += landing_b

    code = drm.build_main(body)

    # Build control: standalone program that stores both markers directly.
    # Validates setup code and expected output without using ret/pop_exec.
    expected_marker = MARKER_B  # explicit r30 hypothesis
    ctrl_setup = e('iadd r20, r1, 0') + mov(21, 32) + e('iadd r21, r20, r21')
    ctrl_setup += mov(23, MARKER_PRE) + st(23, 8, 20) + wait
    ctrl_setup += mov(23, expected_marker) + st(23, 8, 21) + wait + stop
    control = drm.build_main(ctrl_setup)

    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    expected_tab = [MARKER_PRE] * N + [expected_marker] * N + [0] * N * 2

    # Simulator gate with AGX_EXPERIMENTAL_RET=buffer-pop2
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        ctrl_out, ctrl_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (ctrl_out, ctrl_tab) == (expected_out, expected_tab), \
            f"control oracle mismatch"

        var_out, var_tab = cov.simulate(code, N, WG, REGS, 0, table)
        assert (var_out, var_tab) == (expected_out, expected_tab), \
            f"variant oracle mismatch (ret r30 should land at B in simulator)"
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    # Gate: validate surrounding code (ret is the unknown)
    cov.gate(code, allow=('ret',))

    # Also test that default mode rejects ret
    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('ret should be rejected in default mode')
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc)

    return dict(
        code=code,
        control=control,
        table=table,
        n=N,
        wg=WG,
        regs=REGS,
        expected=(expected_out, expected_tab),
        gate={
            'ret_pc': ret_pc,
            'r1_target': 0x2000 + LANDING_A_OFFSET,
            'r30_target': 0x2000 + LANDING_B_OFFSET,
            'variant_rejected_default': True,
            'simulator_accepts_buffer_pop2': True,
            'control_matches_oracle': True,
            'variant_matches_oracle': True,
        },
    )


def run_bounded(argv, env, timeout=10, kill_timeout=2):
    """Bound both dispatch wait and post-SIGKILL pipe drain."""
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
    """Run a single dispatch and capture full diagnostics."""
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
            gpu_safety.record(f'ret-reg-select {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    """Submit the probe to hardware with full diagnostics."""
    name = 'ret-r30-vs-r1'
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
        code=p['code'].hex(),
        control_code=p['control'].hex(),
        table_in=p['table'],
        n=p['n'],
        wg=p['wg'],
        regs=p['regs'],
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

    # Phase 1: save code/inputs before anything runs
    rec['phase'] = 'pre-control'
    save()

    # Phase 2: run known-good control
    rec['control_before'] = run_one(runner, p['control'], p, 'control-before')
    if not matches(rec['control_before'], p['expected']):
        rec['halted'] = 'pre-control failed; no variant submitted'
        save()
        return rec

    # Phase 3: run the variant (ret r30 probe)
    rec['phase'] = 'variant'
    save()
    rec['variant'] = run_one(runner, p['code'], p, 'variant')
    save()

    if rec['variant'].get('host_process_stuck'):
        rec['halted'] = 'probe process still blocked after SIGKILL; no more submissions'
        save()
        return rec

    if not rec['variant']['ok']:
        time.sleep(2)

    # Phase 4: recovery control
    rec['phase'] = 'recovery-control'
    save()
    rec['control_after'] = run_one(runner, p['control'], p, 'control-after')
    rec['recovery_control_passed'] = matches(rec['control_after'], p['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established'

    rec['phase'] = 'finished'

    # Analyze which marker was stored
    if rec['variant'].get('ok') and 'table_after' in rec['variant']:
        tab = rec['variant']['table_after']
        if len(tab) > 63:
            landing_markers = set(tab[32:64])
            if MARKER_B in landing_markers and MARKER_A not in landing_markers:
                rec['interpretation'] = 'explicit_operand_r30'
            elif MARKER_A in landing_markers and MARKER_B not in landing_markers:
                rec['interpretation'] = 'implicit_r1'
            elif MARKER_A in landing_markers and MARKER_B in landing_markers:
                rec['interpretation'] = 'both_markers_unexpected'
            else:
                rec['interpretation'] = 'no_landing_marker'
        else:
            rec['interpretation'] = 'table_too_short'
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'

    save()
    return rec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?',
                   help='offline: simulator only; hardware: submit probe')
    args = p.parse_args()

    print('=== Building and validating probe ===')
    probe = build_probe()
    print(f'  ret_pc={probe["gate"]["ret_pc"]}')
    print(f'  r1 -> {probe["gate"]["r1_target"]:#x} (landing A, MARKER_A)')
    print(f'  r30 -> {probe["gate"]["r30_target"]:#x} (landing B, MARKER_B)')
    print(f'  Simulator (buffer-pop2): ret r30 lands at B (explicit operand) ✓')
    print(f'  Default mode rejects ret ✓')
    print(f'  Control oracle matches ✓')
    print(f'  Code size: {len(probe["code"])} bytes')
    print()

    if args.mode == 'offline':
        print('All simulator checks pass. Use --hardware to submit.')
        return

    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f'  Interpretation: {rec.get("interpretation", "unknown")}')
    print(f'  Variant ok: {rec["variant"].get("ok")}')
    print(f'  Recovery control: {rec.get("recovery_control_passed")}')
    if rec['variant'].get('ok') and 'table_after' in rec['variant']:
        tab = rec['variant']['table_after']
        print(f'  tab[0:4] = {[hex(x) for x in tab[0:4]]}')
        print(f'  tab[32:36] = {[hex(x) for x in tab[32:36]]}')
    print(f'  Saved to: {DATA / "ret-r30-vs-r1.json.gz"}')


if __name__ == '__main__':
    main()