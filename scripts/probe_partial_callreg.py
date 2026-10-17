#!/usr/bin/env python3
"""Priority B follow-up: partial-mask UNIFORM register call (no ret).

Tests whether a uniform `call r30` under a partial exec mask behaves like
the direct call (only active lanes enter the callee). r1 is the harness
lane gid; r30 holds the same buffer-relative callee address on every lane
(set before the mask). No ret: the callee stores link + MARK and stops.

Default: offline simulator validation only.  --hardware submits the probe.

Setup (variant):
  - r29 = r1 (save gid; call will clobber r1 with the link)
  - r20 = r29 + 0  (link store index: table[gid])
  - r21 = r29 + 32 (marker store index: table[32+gid])
  - r1 = SENTINEL (0xDEADBEEF) for all lanes
  - if_icmp r0l, ueq, (r29 & 1), 1  -> odd lanes active (r0l=0), even inactive
  - jnone over the call (skip if no lane active)
  - direct call to callee
  - post-call: stop
  - callee: store r1 at table[gid], store MARKER at table[32+gid], wait, stop

Expected (hypothesis A: mask is honored):
  - table[0:32]: link value on odd lanes, SENTINEL on even lanes
  - table[32:64]: MARKER on odd lanes, 0 on even lanes
Hypothesis B (mask ignored): all lanes link + MARKER.
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
SCRATCH = Path('/scratch/apple-m2-playground/partial-mask-callreg')

SENTINEL = 0xDEADBEEF
MARKER = 0xF00D0001
N = 32
WG = 32
REGS = 64


def build_variant_body():
    """Partial-mask UNIFORM register call (odd lanes active, all lanes with
    the same r30 target). No ret: the callee stores link + MARKER and stops.

    Returns (body, call_pc, callee_pc) with code offsets (site + len(prefix)).
    Register targets are code offsets (0x2000 + code offset, like links).
    """
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]

    setup = e('iadd r29, r1, 0')          # save gid (call clobbers r1)
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')       # link store index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')       # marker store index = 32 + gid
    setup += mov(1, SENTINEL)              # clobber r1 with sentinel
    # r30 must be set BEFORE the mask (masked lanes skip moves). mov_imm is
    # always 6 bytes and the mask block is fixed-size, so the callee address
    # is known before emitting.
    mask_len = len(mov(27, 1) + e('and r24, r29, r27') + e('if_icmp r0l, ueq, r24, r27, 1'))
    post_call = stop
    call_pc = site + len(setup) + 6 + mask_len + 6  # +r30(6) +mask +jnone(6)
    callee_pc = call_pc + 6 + len(post_call)
    setup += mov(30, 0x2000 + callee_pc)   # uniform target, all lanes
    # odd lanes active: (gid & 1) == 1; mask stays set (no pop).
    setup += mov(27, 1)
    setup += e('and r24, r29, r27')
    setup += e('if_icmp r0l, ueq, r24, r27, 1')
    assert site + len(setup) + 6 == call_pc
    island = e('call r30') + wait + wait
    assert len(island) == 6

    # Skip the call entirely when no lane is active (safety gate).
    setup += RS.jnone(6 + len(island))

    callee = st(1, 8, 20)                 # store r1 (link or sentinel) at table[gid]
    callee += mov(23, MARKER)
    callee += st(23, 8, 21)               # store MARKER at table[32+gid]
    callee += wait
    callee += stop

    body = setup + island + post_call + callee
    return body, call_pc, callee_pc


def build_control_body():
    """All-active uniform register call: same stores, no mask."""
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]

    setup = e('iadd r29, r1, 0')
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')
    setup += mov(1, SENTINEL)

    call_pc = site + len(setup) + 6  # +6 for the r30 mov below
    post_call = stop
    callee_pc = call_pc + 6 + len(post_call)
    setup += mov(30, 0x2000 + callee_pc)

    island = e('call r30') + wait + wait
    assert len(island) == 6

    callee = st(1, 8, 20)
    callee += mov(23, MARKER)
    callee += st(23, 8, 21)
    callee += wait
    callee += stop

    body = setup + island + post_call + callee
    return body, call_pc, callee_pc


def build_probe():
    cov.install()
    variant_body, call_pc, callee_pc = build_variant_body()
    control_body, ctrl_call_pc, ctrl_callee_pc = build_control_body()

    code = drm.build_main(variant_body)
    control = drm.build_main(control_body)

    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]

    # Control (all-active): every lane gets link + marker. Register calls
    # store link = base + call_pc + 2 (not +6 as for 6-byte direct calls).
    ctrl_link = 0x2000 + ctrl_call_pc + 2
    expected_ctrl = [ctrl_link] * N + [MARKER] * N + [0] * (128 - 2 * N)

    # Variant hypothesis A (mask honored): odd lanes link + marker,
    # even lanes never execute the callee stores, so they keep the initial 0.
    # (Inactive lanes cannot be observed holding SENTINEL because the store
    # itself is masked; a SENTINEL on even lanes would mean the callee ran
    # for all lanes but the call only set r1 for active lanes.)
    link_val = 0x2000 + call_pc + 2
    expected_a = ([link_val if i % 2 == 1 else 0 for i in range(N)]
                  + [MARKER if i % 2 == 1 else 0 for i in range(N)]
                  + [0] * (128 - 2 * N))
    # Hypothesis B (mask ignored): same as control with variant link.
    expected_b = [link_val] * N + [MARKER] * N + [0] * (128 - 2 * N)

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        ctrl_out, ctrl_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (ctrl_out, ctrl_tab) == (expected_out, expected_ctrl), \
            f"control oracle mismatch: tab[0:4]={ctrl_tab[0:4]}"
        # Uniform partial-mask register calls are now modelled (dragged whole
        # group, r1 only for active lanes): the variant must match exactly.
        v_out, v_tab = cov.simulate(code, N, WG, REGS, 0, table)
        assert (v_out, v_tab) == (expected_out, expected_a), \
            f"variant mismatch: tab[0:4]={[hex(x) for x in v_tab[0:4]]}"
        print("  Simulator reproduces the partial-mask callreg exactly.")
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    cov.gate(code, allow=('call',))

    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('register call unexpectedly accepted in default mode')
    except RuntimeError as exc:
        # Default mode rejects every register call (register form unmodelled
        # without AGX_EXPERIMENTAL_RET); the modelled check above ran with
        # the opt-in set.
        assert 'register form' in str(exc) or 'not modelled' in str(exc), f"unexpected error: {exc}"

    return dict(
        code=code,
        control=control,
        table=table,
        n=N,
        wg=WG,
        regs=REGS,
        expected=(expected_out, expected_ctrl),
        expected_var_a=(expected_out, expected_a),
        expected_var_b=(expected_out, expected_b),
        gate={
            'call_pc': call_pc,
            'callee_pc': callee_pc,
            'link_val': link_val,
            'sentinel': SENTINEL,
            'marker': MARKER,
        },
    )


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
            gpu_safety.record(f'partial-mask-callreg {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    name = 'partial-mask-callreg'
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

    rec['phase'] = 'pre-control'
    save()

    rec['control_before'] = run_one(runner, p['control'], p, 'control-before')
    if not matches(rec['control_before'], p['expected']):
        rec['halted'] = 'pre-control failed; no variant submitted'
        save()
        return rec

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

    rec['phase'] = 'recovery-control'
    save()
    rec['control_after'] = run_one(runner, p['control'], p, 'control-after')
    rec['recovery_control_passed'] = matches(rec['control_after'], p['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established'

    rec['phase'] = 'finished'

    if rec['variant'].get('ok') and 'table_after' in rec['variant']:
        tab = rec['variant']['table_after']
        link_val = p['gate']['link_val']
        sentinel = p['gate']['sentinel']
        marker = p['gate']['marker']
        link_lanes = [i for i in range(N) if i < len(tab) and tab[i] == link_val]
        sentinel_lanes = [i for i in range(N) if i < len(tab) and tab[i] == sentinel]
        marker_lanes = [i for i in range(N) if i < len(tab) - 32 and tab[32 + i] == marker]
        rec['analysis'] = {
            'link_lanes': link_lanes,
            'sentinel_lanes': sentinel_lanes,
            'marker_lanes': marker_lanes,
        }
        if set(link_lanes) == set(range(1, N, 2)) and set(marker_lanes) == set(range(1, N, 2)):
            rec['interpretation'] = 'mask_honored_active_lanes_only'
        elif len(link_lanes) == N and len(marker_lanes) == N:
            rec['interpretation'] = 'mask_ignored_all_lanes'
        else:
            rec['interpretation'] = f'unexpected_link{len(link_lanes)}_marker{len(marker_lanes)}'
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
    print(f"  call_pc={probe['gate']['call_pc']}")
    print(f"  callee_pc={probe['gate']['callee_pc']}")
    print(f"  link_val={probe['gate']['link_val']:#x}")
    print(f"  sentinel={probe['gate']['sentinel']:#x}")
    print(f"  marker={probe['gate']['marker']:#x}")
    print()

    if args.mode == 'offline':
        print('Simulator validation done. Use hardware mode to submit.')
        return

    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f"  Variant ok: {rec['variant'].get('ok')}")
    print(f"  Recovery control: {rec.get('recovery_control_passed')}")
    if 'analysis' in rec:
        a = rec['analysis']
        print(f"  Link lanes: {a['link_lanes']}")
        print(f"  Sentinel lanes: {a['sentinel_lanes']}")
        print(f"  Marker lanes: {a['marker_lanes']}")
        print(f"  Interpretation: {rec.get('interpretation')}")
    elif 'interpretation' in rec:
        print(f"  Interpretation: {rec['interpretation']}")
    print(f"  Saved to: {DATA / 'partial-mask-callreg.json.gz'}")


if __name__ == '__main__':
    main()
