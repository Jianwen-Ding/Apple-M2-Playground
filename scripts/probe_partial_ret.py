#!/usr/bin/env python3
"""Priority B (part 2): partial-mask ret to one common landing.

Odd lanes are active via if_icmp on the harness gid; even lanes are inactive.
`ret r30` targets landing B for all lanes. Active lanes should jump to B
(pop_exec 2 + MARKER_B); inactive lanes skip the ret, pop back to active,
and store MARKER_FALL in the same per-lane slot.

Default: offline simulator/surrogate validation only. --hardware submits.

Expected hypothesis A (mask honored):
  table[32+gid] = MARKER_B on odd lanes, MARKER_FALL on even lanes.
Hypothesis B (ret ignores mask): MARKER_B on all lanes.
Any fault is recorded with recovery control; budget is checked first.
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
SCRATCH = Path('/scratch/apple-m2-playground/partial-mask-ret')

MARKER_PRE = 0xAAAA0001
MARKER_B = 0xBBBB0002
MARKER_FALL = 0xFFFF0001
N = 32
WG = 32
REGS = 64
LANDING_B_OFF = 1536


MASKS = {
    # name: (description, active lanes predicate description, setup fragment builder key)
    'odd': 'odd lanes (gid & 1 == 1)',
    'single0': 'lane 0 only (gid == 0)',
    'contig16': 'lanes 0-15 (gid < 16)',
    'lanes31': 'lanes 0-30 (gid < 31)',
}


def mask_setup(mask, e, mov):
    """Per-mask condition code; r29 holds the gid. Returns (bytes, active set)."""
    if mask == 'odd':
        b = mov(27, 1)
        b += e('and r24, r29, r27')
        b += e('if_icmp r0l, ueq, r24, r27, 1')
        return b, set(range(1, N, 2))
    if mask == 'single0':
        b = mov(27, 0)
        b += e('if_icmp r0l, seq, r29, r27, 1')
        return b, {0}
    if mask == 'contig16':
        b = mov(27, 16)
        b += e('if_icmp r0l, ult, r29, r27, 1')
        return b, set(range(16))
    if mask == 'lanes31':
        b = mov(27, 31)
        b += e('if_icmp r0l, ult, r29, r27, 1')
        return b, set(range(31))
    raise ValueError(mask)


def build_bodies(mask='odd'):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')

    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # pre-marker index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # marker index = 32 + gid
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)              # pre-marker for all lanes
    setup += wait
    setup += mov(30, 0x2000 + LANDING_B_OFF)  # uniform ret target
    setup += mov(1, 0xDEADBEEF)        # clobber r1 (not needed afterwards)
    cond, active = mask_setup(mask, e, mov)
    setup += cond

    site = drm.control_main()[1]
    # jnone over the ret island when no lane is active (safety gate)
    ret_island = e('ret r30') + wait + wait
    assert len(ret_island) == 6
    jnone = RS.jnone(6 + len(ret_island))
    ret_pc = site + len(setup) + len(jnone)

    # Inactive lanes fall through here: pop back to active, store FALL, stop.
    fall = e('pop_exec r0l, 1')
    fall += mov(23, MARKER_FALL)
    fall += st(23, 8, 21)
    fall += wait
    fall += stop

    body = setup + jnone + ret_island + fall
    # pad to landing B
    pad = LANDING_B_OFF - len(body)
    assert pad >= 0 and pad % 2 == 0, f"body too long: {len(body)}"
    body += stop * (pad // 2)
    assert len(body) == LANDING_B_OFF
    landing = e('pop_exec r0l, 2')
    landing += mov(23, MARKER_B)
    landing += st(23, 8, 21)
    landing += wait
    landing += stop
    body += landing
    code = drm.build_main(body)

    # Surrogate 1: replace ret island with 6-byte jump to landing B.
    # jmp_exec_any moves the whole group, so ALL lanes land at B and store
    # MARKER_B. This validates the B path (pop_exec 2 + store).
    # Note: jump offsets are relative to the CODE array (site + body offset).
    jump_off = (site + LANDING_B_OFF) - ret_pc
    jump = e(f'jmp_exec_any pc{jump_off:+}', f'jmp_exec_any pc{jump_off:+}')
    assert len(jump) == len(ret_island)
    surrogate_jump = code[:ret_pc] + jump + code[ret_pc + len(ret_island):]

    # Surrogate 2: replace ret island with waits (fall through).
    # Odd lanes stay active, pop to all-active, store FALL; even lanes are
    # inactive at the pop... actually pop_exec 1 makes r0l 1->0 for even
    # lanes too, so ALL lanes store FALL. This validates the fallthrough path.
    surrogate_wait = code[:ret_pc] + wait * 3 + code[ret_pc + len(ret_island):]

    # All-active control: same landing, no mask.
    ctrl_setup = e('iadd r29, r1, 0')
    ctrl_setup += mov(27, 0)
    ctrl_setup += e('iadd r20, r29, r27')
    ctrl_setup += mov(27, 32)
    ctrl_setup += e('iadd r21, r29, r27')
    ctrl_setup += mov(23, MARKER_PRE)
    ctrl_setup += st(23, 8, 20)
    ctrl_setup += wait
    ctrl_setup += mov(30, 0x2000 + LANDING_B_OFF)
    ctrl_code = drm.build_main(ctrl_setup + e('ret r30') + wait + wait
                               + stop * ((LANDING_B_OFF - len(ctrl_setup) - 6) // 2)
                               + landing)
    return code, surrogate_jump, surrogate_wait, ctrl_code, ret_pc


def build_probe(mask='odd'):
    cov.install()
    code, surrogate_jump, surrogate_wait, control, ret_pc = build_bodies(mask)
    _, active = mask_setup(mask, RS.e, RS.mov)
    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    # Jump surrogate: whole group lands at B -> all MARKER_B.
    expected_jump = [MARKER_PRE] * N + [MARKER_B] * N + [0] * (128 - 2 * N)
    # Wait surrogate: all lanes fall through; pop reactivates everyone.
    expected_wait = ([MARKER_PRE] * N + [MARKER_FALL] * N + [0] * (128 - 2 * N))
    # All-active control: all lanes MARKER_B.
    expected_ctrl = [MARKER_PRE] * N + [MARKER_B] * N + [0] * (128 - 2 * N)
    # Variant: active lanes B, inactive lanes 0 (no fallthrough, per finding).
    expected_var = ([MARKER_PRE] * N
                    + [MARKER_B if i in active else 0 for i in range(N)]
                    + [0] * (128 - 2 * N))

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        j_out, j_tab = cov.simulate(surrogate_jump, N, WG, REGS, 0, table)
        assert (j_out, j_tab) == (expected_out, expected_jump), \
            f"jump surrogate mismatch: tab[32:40]={[hex(x) for x in j_tab[32:40]]}"
        w_out, w_tab = cov.simulate(surrogate_wait, N, WG, REGS, 0, table)
        assert (w_out, w_tab) == (expected_out, expected_wait), \
            f"wait surrogate mismatch: tab[32:40]={[hex(x) for x in w_tab[32:40]]}"
        ctrl_out, ctrl_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (ctrl_out, ctrl_tab) == (expected_out, expected_ctrl), \
            "control oracle mismatch"
        # The variant itself must be rejected: partial-mask ret is unmodelled.
        try:
            cov.simulate(code, N, WG, REGS, 0, table)
        except RuntimeError as exc:
            assert 'only all-active' in str(exc), f"unexpected rejection: {exc}"
            print(f"  Simulator rejects partial-mask ret as expected: {exc}")
        else:
            raise AssertionError('partial-mask ret unexpectedly accepted by simulator')
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    cov.gate(code, allow=('ret',))
    # Default mode must also reject (unresolved ret).
    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('ret should be rejected in default mode')
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc), f"unexpected error: {exc}"

    print(f"  Jump surrogate: all MARKER_B validated.")
    print(f"  Wait surrogate: all MARKER_FALL validated.")
    print(f"  Mask '{mask}': active lanes = {sorted(active)}")
    return dict(
        code=code,
        surrogate=surrogate_jump,
        control=control,
        table=table,
        n=N,
        wg=WG,
        regs=REGS,
        mask=mask,
        active=sorted(active),
        expected=(expected_out, expected_ctrl),
        expected_sur=(expected_out, expected_jump),
        expected_var=(expected_out, expected_var),
        gate={'ret_pc': ret_pc, 'landing_b': LANDING_B_OFF,
              'marker_b': MARKER_B, 'marker_fall': MARKER_FALL,
              'mask': mask, 'active': sorted(active),
              'variant_rejected_partial_mask': True,
              'jump_surrogate_matches_oracle': True,
              'wait_surrogate_matches_oracle': True,
              'control_matches_oracle': True},
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
            gpu_safety.record(f'partial-mask-ret {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p, name=None):
    name = name or f"partial-mask-ret-{p.get('mask', 'odd')}"
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
        n=p['n'], wg=p['wg'], regs=p['regs'], gate=p['gate'],
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
        b_lanes = [i for i in range(N) if i < len(tab) - 32 and tab[32 + i] == MARKER_B]
        f_lanes = [i for i in range(N) if i < len(tab) - 32 and tab[32 + i] == MARKER_FALL]
        z_lanes = [i for i in range(N) if i < len(tab) - 32 and tab[32 + i] == 0]
        rec['analysis'] = {'marker_b_lanes': b_lanes, 'marker_fall_lanes': f_lanes,
                           'zero_lanes': z_lanes, 'expected_active': p.get('active')}
        exp = set(p.get('active', []))
        if set(b_lanes) == exp and not f_lanes and set(z_lanes) == set(range(N)) - exp:
            rec['interpretation'] = 'mask_honored_active_B_inactive_dropped'
        elif len(b_lanes) == N and not f_lanes:
            rec['interpretation'] = 'mask_ignored_all_B'
        elif set(b_lanes) == exp and set(f_lanes) == set(range(N)) - exp:
            rec['interpretation'] = 'mask_honored_active_B_inactive_FALL'
        else:
            rec['interpretation'] = f'unexpected_B{len(b_lanes)}_FALL{len(f_lanes)}_Z{len(z_lanes)}'
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    ap.add_argument('--mask', choices=sorted(MASKS) + ['all'],
                    default='all', help='which mask(s) to build/submit (default: all new + odd check)')
    args = ap.parse_args()
    masks = ['single0', 'contig16', 'lanes31'] if args.mask == 'all' else [args.mask]
    if args.mode == 'offline':
        print('=== Building and validating probes ===')
        for m in masks:
            print(f'--- mask {m} ({MASKS[m]}) ---')
            probe = build_probe(m)
            print(f"  ret_pc={probe['gate']['ret_pc']}")
            print(f"  landing_b={probe['gate']['landing_b']:#x}")
        # also revalidate the recorded odd mask without resubmitting it
        print('--- mask odd (recorded; revalidating offline only) ---')
        probe = build_probe('odd')
        print('Simulator/surrogate validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    for m in masks:
        gpu_safety.require_budget(1)
        print(f'--- mask {m} ({MASKS[m]}) ---')
        probe = build_probe(m)
        rec = hardware(probe, f'partial-mask-ret-{m}')
        print(f"  Variant ok: {rec['variant'].get('ok')}")
        print(f"  Recovery control: {rec.get('recovery_control_passed')}")
        if 'analysis' in rec:
            print(f"  B lanes: {rec['analysis']['marker_b_lanes']}")
            print(f"  FALL lanes: {rec['analysis']['marker_fall_lanes']}")
        print(f"  Interpretation: {rec.get('interpretation')}")
        print(f"  Saved to: {DATA / ('partial-mask-ret-' + m + '.json.gz')}")
        if rec.get('halted'):
            print(f"  HALTED: {rec['halted']}; stopping batch.")
            return


if __name__ == '__main__':
    main()
