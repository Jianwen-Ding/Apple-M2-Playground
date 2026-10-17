#!/usr/bin/env python3
"""Priority B: partial-mask direct call (no ret).

Tests what happens when a direct call is made under a partial exec mask.
Records which lanes receive a link (r1) and which lanes execute the callee.

Default: offline simulator validation.  --hardware submits the probe.

Setup:
  - Load per-lane data from table (lane IDs 0..31)
  - Compute odd-lane mask: (lane_id & 1) != 0
  - Set r1 = sentinel (0xDEADBEEF) for all lanes
  - Execute direct call under partial mask (odd lanes active)
  - Callee: store r1 (link) at table[0:32], store marker at table[32:64], stop

Expected:
  - If call sets r1 only for active lanes: odd lanes have link, even lanes have sentinel
  - If call sets r1 for all lanes: all lanes have link
  - If callee executes only for active lanes: only odd lanes have marker
  - If callee executes for all lanes: all lanes have marker
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
SCRATCH = Path('/scratch/apple-m2-playground/partial-mask-call')

SENTINEL = 0xDEADBEEF
MARKER = 0xF00D0001
N = 32
WG = 32
REGS = 64


def build_probe(all_active=False):
    """Build variant (partial mask) or control (all-active) program.

    Args:
        all_active: If True, skip the partial mask setup (control case).

    Returns dict with code, control, table, expected, gate, etc.
    """
    cov.install()
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')

    # Load per-lane data from table (lane IDs 0..31 stored at table words 0..31)
    setup = mov(27, 0)  # offset = 0
    setup += e('imadd r5, r1, r27, 0')  # r5 = r1 + 0 = table base
    setup += e('device_load 0, i32, xyzw, r6_r7_r8_r9, u8_u9, r5, unsigned')
    setup += wait  # wait for load

    # r20 = r1 (save table base for callee stores)
    setup += e('iadd r20, r1, 0')

    # Pre-load r1 with sentinel
    setup += mov(1, SENTINEL)

    if not all_active:
        # Set up partial mask: odd lanes active
        # r6 = lane_id (loaded from table)
        # r27 = r6 & 1 (lane_id % 2)
        setup += mov(28, 1)
        setup += e('and r27, r6, r28')
        # if_icmp r0l, ult, r24, r27, 1 where r24 = 0
        # Odd lanes: r27=1, 0<1=true -> active
        # Even lanes: r27=0, 0<0=false -> inactive
        setup += mov(24, 0)
        setup += e('if_icmp r0l, ult, r24, r27, 1')

    site = drm.control_main()[1]
    call_pc = site + len(setup)

    # Direct call to callee (6 bytes)
    # Callee is after the caller's post-call code
    post_call = stop  # caller never reaches here if callee doesn't return
    callee_pc = call_pc + 6 + len(post_call)
    call_off = callee_pc - call_pc
    call_instr = (0xC010 | ((call_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')

    # Callee: store r1 (link) at table[0:32], store marker at table[32:64], stop
    callee = st(1, 8, 20)  # store r1 at table[0:32] (index=r20=lane_id)
    callee += mov(23, MARKER)
    callee += st(23, 8, 21)  # store marker at table[32:64] (r21 = r20+32... wait, need to set r21)

    # Actually, r21 needs to be set. Let me use a different approach.
    # The callee needs r21 = r20 + 32 for the marker store.
    # But r20 = r1 (table base). r21 = r1 + 32.
    # The callee can compute r21 from r20.
    callee = mov(21, 32) + e('iadd r21, r20, r21')  # r21 = r20 + 32
    callee += st(1, 8, 20)  # store r1 at table[0:32]
    callee += mov(23, MARKER)
    callee += st(23, 8, 21)  # store marker at table[32:64]
    callee += wait
    callee += stop

    body = setup + call_instr + post_call + callee
    code = drm.build_main(body)

    # Build control: all-active version (no partial mask)
    # Build separately to avoid recursion
    ctrl_setup = mov(27, 0)
    ctrl_setup += e('imadd r5, r1, r27, 0')
    ctrl_setup += e('device_load 0, i32, xyzw, r6_r7_r8_r9, u8_u9, r5, unsigned')
    ctrl_setup += wait
    ctrl_setup += e('iadd r20, r1, 0')
    ctrl_setup += mov(1, SENTINEL)
    # No partial mask - all lanes active
    ctrl_site = drm.control_main()[1]
    ctrl_call_pc = ctrl_site + len(ctrl_setup)
    ctrl_callee_pc = ctrl_call_pc + 6 + len(stop)
    ctrl_call_off = ctrl_callee_pc - ctrl_call_pc
    ctrl_call_instr = (0xC010 | ((ctrl_call_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
    ctrl_callee = mov(21, 32) + e('iadd r21, r20, r21')
    ctrl_callee += st(1, 8, 20)
    ctrl_callee += mov(23, MARKER)
    ctrl_callee += st(23, 8, 21)
    ctrl_callee += wait + stop
    ctrl_body = ctrl_setup + ctrl_call_instr + stop + ctrl_callee
    control = drm.build_main(ctrl_body)

    # Table: pre-fill with lane IDs for the load, rest zero
    table = list(range(N)) + [0] * (128 - N)

    # Expected output: default harness output
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]

    # Expected table for control (all-active):
    # - table[0:32]: link value (0x2000 + ctrl_call_pc + 6) for all lanes
    # - table[32:64]: MARKER for all lanes
    ctrl_link_val = 0x2000 + ctrl_call_pc + 6
    expected_tab_ctrl = [ctrl_link_val] * N + [MARKER] * N + [0] * (128 - 2 * N)

    # Expected table for variant (partial mask, odd lanes active):
    # Hypothesis A: call sets r1 only for active lanes
    #   - Odd lanes: link value; Even lanes: SENTINEL
    #   - Callee executes only for active lanes: odd lanes have MARKER, even lanes 0
    # Hypothesis B: call sets r1 for all lanes
    #   - All lanes: link value
    #   - Callee executes for all lanes: all lanes have MARKER
    link_val = 0x2000 + call_pc + 6
    expected_tab_var_a = []
    for i in range(N):
        expected_tab_var_a.append(link_val if i % 2 == 1 else SENTINEL)
    for i in range(N):
        expected_tab_var_a.append(MARKER if i % 2 == 1 else 0)
    expected_tab_var_a += [0] * (128 - 2 * N)

    expected_tab_var_b = [link_val] * N + [MARKER] * N + [0] * (128 - 2 * N)

    # Simulator gate
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        # Test control (all-active)
        ctrl_out, ctrl_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (ctrl_out, ctrl_tab) == (expected_out, expected_tab_ctrl), \
            f"control oracle mismatch"

        # Test variant (partial mask)
        var_out, var_tab = cov.simulate(code, N, WG, REGS, 0, table)
        # The simulator should show what happens with partial mask
        print(f'  Simulator variant tab[0:8] = {[hex(x) for x in var_tab[0:8]]}')
        print(f'  Simulator variant tab[32:40] = {[hex(x) for x in var_tab[32:40]]}')
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    # Gate: validate surrounding code (call is known, but partial-mask behavior is the unknown)
    cov.gate(code, allow=('call',))

    label = 'partial-mask-call' if not all_active else 'partial-mask-call-ctrl'
    return dict(
        code=code,
        control=control,
        table=table,
        n=N,
        wg=WG,
        regs=REGS,
        expected=(expected_out, expected_tab_ctrl),  # control expected
        expected_var_a=(expected_out, expected_tab_var_a),
        expected_var_b=(expected_out, expected_tab_var_b),
        gate={
            'call_pc': call_pc,
            'callee_pc': callee_pc,
            'link_val': 0x2000 + call_pc + 6,
            'sentinel': SENTINEL,
            'marker': MARKER,
            'all_active': all_active,
        },
        label=label,
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
            gpu_safety.record(f'partial-mask-call {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    """Submit the probe to hardware with full diagnostics."""
    name = 'partial-mask-call'
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

    # Run all-active control first
    ctrl_p = build_probe(all_active=True)
    rec['control_before'] = run_one(runner, ctrl_p['control'], ctrl_p, 'control-before')
    if not matches(rec['control_before'], ctrl_p['expected']):
        rec['halted'] = 'pre-control failed; no variant submitted'
        save()
        return rec

    # Run the variant (partial mask)
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

    # Recovery control
    rec['phase'] = 'recovery-control'
    save()
    rec['control_after'] = run_one(runner, ctrl_p['control'], ctrl_p, 'control-after')
    rec['recovery_control_passed'] = matches(rec['control_after'], ctrl_p['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established'

    rec['phase'] = 'finished'

    # Analyze results
    if rec['variant'].get('ok') and 'table_after' in rec['variant']:
        tab = rec['variant']['table_after']
        link_val = p['gate']['link_val']
        sentinel = p['gate']['sentinel']
        marker = p['gate']['marker']

        # Check link values (table[0:32])
        link_lanes = [i for i in range(N) if i < len(tab) and tab[i] == link_val]
        sentinel_lanes = [i for i in range(N) if i < len(tab) and tab[i] == sentinel]
        other_link_lanes = [i for i in range(N) if i < len(tab) and tab[i] not in (link_val, sentinel)]

        # Check marker values (table[32:64])
        marker_lanes = [i for i in range(N) if i < len(tab) - 32 and tab[32 + i] == marker]
        zero_lanes = [i for i in range(N) if i < len(tab) - 32 and tab[32 + i] == 0]

        rec['analysis'] = {
            'link_lanes': link_lanes,
            'sentinel_lanes': sentinel_lanes,
            'other_link_lanes': other_link_lanes,
            'marker_lanes': marker_lanes,
            'zero_marker_lanes': zero_lanes,
        }

        # Determine interpretation
        if len(link_lanes) == N:
            rec['link_interpretation'] = 'call_sets_r1_all_lanes'
        elif set(link_lanes) == set(range(1, N, 2)):  # odd lanes
            rec['link_interpretation'] = 'call_sets_r1_active_lanes_only'
        else:
            rec['link_interpretation'] = f'unexpected_pattern_{len(link_lanes)}_lanes'

        if len(marker_lanes) == N:
            rec['callee_interpretation'] = 'callee_executes_all_lanes'
        elif set(marker_lanes) == set(range(1, N, 2)):  # odd lanes
            rec['callee_interpretation'] = 'callee_executes_active_lanes_only'
        else:
            rec['callee_interpretation'] = f'unexpected_pattern_{len(marker_lanes)}_lanes'

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
    probe = build_probe(all_active=False)
    ctrl = build_probe(all_active=True)
    print(f'  call_pc={probe["gate"]["call_pc"]}')
    print(f'  callee_pc={probe["gate"]["callee_pc"]}')
    print(f'  link_val={probe["gate"]["link_val"]:#x}')
    print(f'  sentinel={probe["gate"]["sentinel"]:#x}')
    print(f'  marker={probe["gate"]["marker"]:#x}')
    print()

    if args.mode == 'offline':
        print('Simulator validation passed. Use --hardware to submit.')
        return

    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f'  Variant ok: {rec["variant"].get("ok")}')
    print(f'  Recovery control: {rec.get("recovery_control_passed")}')
    if 'analysis' in rec:
        a = rec['analysis']
        print(f'  Link lanes: {a["link_lanes"]}')
        print(f'  Sentinel lanes: {a["sentinel_lanes"]}')
        print(f'  Marker lanes: {a["marker_lanes"]}')
        print(f'  Link interpretation: {rec.get("link_interpretation")}')
        print(f'  Callee interpretation: {rec.get("callee_interpretation")}')
    elif 'interpretation' in rec:
        print(f'  Interpretation: {rec["interpretation"]}')
    print(f'  Saved to: {DATA / "partial-mask-call.json.gz"}')


if __name__ == '__main__':
    main()