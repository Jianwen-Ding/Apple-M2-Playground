#!/usr/bin/env python3
"""Priority C: empty-mask call / callreg / ret — skipped vs issued.

With no lanes active (if_icmp false for all lanes), issue a direct call, a
register call, or a ret (one unknown per dispatch) instead of skipping it
with jmp_exec_none. All register operands hold valid in-program addresses.
Fallthrough and callee/landing blocks both end in stop; the first of the
three cases runs first, and the batch halts on any halt condition.

Slot map (per-lane, indexed by gid):
  table[gid]      link (call cases; pre-marker survives on lanes that never store)
  table[32+gid]   callee/landing marker (C1 / R1)
  table[64+gid]   second landing marker (R2, ret case only)
  table[96+gid]   FALL (fallthrough path)

Default: offline simulator/surrogate validation only. --hardware submits the batch.
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
SCRATCH = Path('/scratch/apple-m2-playground/empty-mask')

MARKER_PRE = 0xAAAA0001
MARKER_CALLEE = 0xC4110001
MARKER_R1 = 0x8E700001
MARKER_R2 = 0x8E700002
MARKER_FALL = 0xFA110001
N = 32
WG = 32
REGS = 64
TARGET_OFF = 1536

CASES = ('call', 'callreg', 'ret')


def build_bodies(case):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')

    site = drm.control_main()[1]
    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # link / pre-marker index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # marker index = 32 + gid
    setup += mov(27, 64)
    setup += e('iadd r22, r29, r27')    # second-marker index = 64 + gid
    setup += mov(27, 96)
    setup += e('iadd r24, r29, r27')    # fallthrough index = 96 + gid (r23 unusable)
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)              # pre-marker for all lanes
    setup += wait
    if case in ('call', 'callreg'):
        setup += mov(1, 0xDEADBEEF)    # clobber r1 (call overwrites with link)
        if case == 'callreg':
            # r30 must hold a valid target on EVERY lane, including lanes the
            # mask is about to deactivate: masked lanes skip moves. Register
            # targets are code offsets (0x2000 + code offset, like call links).
            setup += mov(30, 0x2000 + site + TARGET_OFF)
    else:
        setup += mov(1, 0xDEADBEEF)
        setup += mov(30, 0x2000 + site + TARGET_OFF)  # uniform ret target (code offset)
    # empty mask: gid < 0 is false for every lane
    setup += mov(27, 0)
    setup += e('if_icmp r0l, ult, r29, r27, 1')

    if case == 'call':
        post_len = 0  # computed below after island known
        island = b'CALL6'
    elif case == 'callreg':
        island = e('call r30') + wait + wait
        assert len(island) == 6
    else:
        island = e('ret r30') + wait + wait
        assert len(island) == 6

    # Fallthrough: pop, store FALL, stop. Reached by lanes that skip the island.
    fall = e('pop_exec r0l, 1')
    fall += mov(23, MARKER_FALL)
    fall += st(23, 8, 24)
    fall += wait
    fall += stop

    if case in ('call', 'callreg'):
        # Callee block at TARGET_OFF: pop (reactivate), store link, store C1.
        target = e('pop_exec r0l, 1')
        target += st(1, 8, 20)
        target += mov(23, MARKER_CALLEE)
        target += st(23, 8, 21)
        target += wait
        target += stop
    else:
        # Landing block at TARGET_OFF: two pops cover depth 1 or 2.
        target = e('pop_exec r0l, 1')
        target += mov(23, MARKER_R1)
        target += st(23, 8, 21)
        target += e('pop_exec r0l, 1')
        target += mov(23, MARKER_R2)
        target += st(23, 8, 22)
        target += wait
        target += stop

    if case == 'call':
        # call_pc must be known to encode the relative offset; the island is
        # 6 bytes starting right after setup (no jnone: we ISSUE under empty mask).
        call_pc = site + len(setup)
        post_pc = call_pc + 6
        callee_pc = site + TARGET_OFF
        call_off = callee_pc - call_pc
        island = (0xC010 | ((call_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
        island_pc = call_pc
    elif case == 'callreg':
        # r30 was set in setup (before the mask) so every lane holds it.
        call_pc = site + len(setup)
        island_pc = call_pc
    else:
        island_pc = site + len(setup)

    body = setup + island + fall
    pad = TARGET_OFF - len(body)
    assert pad >= 0 and pad % 2 == 0, f"body too long for {case}: {len(body)}"
    body += stop * (pad // 2)
    assert len(body) == TARGET_OFF
    body += target
    code = drm.build_main(body)

    # Skip surrogate (simulation only): empty mask + jnone over the island.
    # No lane runs the island; all pop and store FALL. Validates the path.
    jnone = RS.jnone(6 + len(island))
    skip_body = setup + jnone + island + fall
    skip_body += stop * ((TARGET_OFF - len(skip_body)) // 2) + target
    skip_code = drm.build_main(skip_body)

    # All-active control: same layout, condition true for every lane.
    csetup = e('iadd r29, r1, 0')
    csetup += mov(27, 0)
    csetup += e('iadd r20, r29, r27')
    csetup += mov(27, 32)
    csetup += e('iadd r21, r29, r27')
    csetup += mov(27, 64)
    csetup += e('iadd r22, r29, r27')
    csetup += mov(27, 96)
    csetup += e('iadd r24, r29, r27')
    csetup += mov(23, MARKER_PRE)
    csetup += st(23, 8, 20)
    csetup += wait
    c_site = drm.control_main()[1]
    if case in ('call', 'callreg'):
        csetup += mov(1, 0xDEADBEEF)
        if case == 'callreg':
            # Set before the mask so every lane holds it; code offset like links.
            csetup += mov(30, 0x2000 + c_site + TARGET_OFF)
    else:
        csetup += mov(1, 0xDEADBEEF)
        csetup += mov(30, 0x2000 + c_site + TARGET_OFF)
    csetup += mov(27, 32 if case == 'callreg' else 33)
    # all-active condition: gid < 32/33 — every lane 0..31 passes.
    csetup += e('if_icmp r0l, ult, r29, r27, 1')
    if case == 'call':
        c_call_pc = c_site + len(csetup)
        c_callee_pc = c_site + TARGET_OFF
        c_off = c_callee_pc - c_call_pc
        c_island = (0xC010 | ((c_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
        # fallthrough for control: same fall block (dead code, never reached)
        cfall = e('pop_exec r0l, 1') + mov(23, MARKER_FALL) + st(23, 8, 24) + wait + stop
        cbody = csetup + c_island + cfall
        cbody += stop * ((TARGET_OFF - len(cbody)) // 2)
        assert len(cbody) == TARGET_OFF
        ctarget = (e('pop_exec r0l, 1') + st(1, 8, 20) + mov(23, MARKER_CALLEE)
                   + st(23, 8, 21) + wait + stop)
        cbody += ctarget
        control = drm.build_main(cbody)
        ctrl_link = 0x2000 + c_call_pc + 6
    elif case == 'callreg':
        csetup2 = csetup + e('call r30') + wait + wait
        cfall = e('pop_exec r0l, 1') + mov(23, MARKER_FALL) + st(23, 8, 24) + wait + stop
        # place callee at TARGET_OFF
        pre_len = len(csetup2) + len(cfall)
        cfall2 = cfall + stop * ((TARGET_OFF - pre_len) // 2)
        ctarget = (e('pop_exec r0l, 1') + st(1, 8, 20) + mov(23, MARKER_CALLEE)
                   + st(23, 8, 21) + wait + stop)
        control = drm.build_main(csetup2 + cfall2 + ctarget)
        c_call_pc = c_site + len(csetup)
        ctrl_link = 0x2000 + c_call_pc + 2
    else:
        c_island = e('ret r30') + wait + wait
        cfall = e('pop_exec r0l, 1') + mov(23, MARKER_FALL) + st(23, 8, 24) + wait + stop
        cbody = csetup + c_island + cfall
        cbody += stop * ((TARGET_OFF - len(cbody)) // 2)
        assert len(cbody) == TARGET_OFF
        ctarget = (e('pop_exec r0l, 1') + mov(23, MARKER_R1) + st(23, 8, 21)
                   + e('pop_exec r0l, 1') + mov(23, MARKER_R2) + st(23, 8, 22) + wait + stop)
        cbody += ctarget
        control = drm.build_main(cbody)
        ctrl_link = None
    return code, skip_code, control, island_pc, ctrl_link


def build_probe(case):
    cov.install()
    code, skip_code, control, island_pc, ctrl_link = build_bodies(case)
    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    # Skip surrogate: nobody runs the island; all lanes pop and store FALL.
    expected_skip = ([MARKER_PRE] * N + [0] * N + [0] * N + [MARKER_FALL] * N)
    if case in ('call', 'callreg'):
        expected_ctrl = ([ctrl_link] * N + [MARKER_CALLEE] * N + [0] * N + [0] * N)
    else:
        # Full-mask ret leaves depth 2: first pop leaves lanes masked (R1
        # skipped), second pop reactivates (R2 stored). Pre-marker survives
        # in the link slot (no link store in the ret cases).
        expected_ctrl = ([MARKER_PRE] * N + [0] * N + [MARKER_R2] * N + [0] * N)

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        s_out, s_tab = cov.simulate(skip_code, N, WG, REGS, 0, table)
        assert (s_out, s_tab) == (expected_out, expected_skip), \
            f"{case} skip-surrogate mismatch: fall={s_tab[96:100]}"
        c_out, c_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (c_out, c_tab) == (expected_out, expected_ctrl), \
            f"{case} control mismatch: tab0={c_tab[0]:#x} tab32={c_tab[32]:#x}"
        # Variant: empty mask falls through (no transfer, no link write).
        # The simulator now models this; assert the fallthrough oracle, which
        # matches every hardware run bit-for-bit.
        expected_fall = ([MARKER_PRE] * N + [0] * N + [0] * N + [MARKER_FALL] * N)
        try:
            v_out, v_tab = cov.simulate(code, N, WG, REGS, 0, table)
            assert (v_out, v_tab) == (expected_out, expected_fall), \
                f"{case}: variant mismatch link0={v_tab[0]:#x} m32={v_tab[32]:#x} f96={v_tab[96]:#x}"
            print(f"  {case}: simulator reproduces the empty-mask fallthrough exactly.")
            prediction = (v_out, v_tab)
        except RuntimeError as exc:
            raise AssertionError(f"{case}: simulator unexpectedly rejects empty-mask variant: {exc}")
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    allow = ('call',) if case in ('call', 'callreg') else ('ret',)
    cov.gate(code, allow=allow)
    if case == 'ret':
        try:
            cov.simulate(code, N, WG, REGS, 0, table)
            raise AssertionError('ret should be rejected in default mode')
        except RuntimeError as exc:
            assert 'ret semantics unresolved' in str(exc), f"unexpected error: {exc}"
    print(f"  {case}: control + skip-surrogate validated.")
    return dict(
        code=code, control=control, table=table, n=N, wg=WG, regs=REGS,
        expected=(expected_out, expected_ctrl),
        prediction=prediction if isinstance(prediction, str) else 'simulated',
        gate={'case': case, 'island_pc': island_pc, 'ctrl_link': ctrl_link,
              'control_matches_oracle': True, 'skip_surrogate_matches_oracle': True},
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
            gpu_safety.record(f'empty-mask {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p, name):
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
        table_in=p['table'], n=p['n'], wg=p['wg'], regs=p['regs'], gate=p['gate'],
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
        n_link = sum(1 for i in range(N) if tab[i] == (p['gate']['ctrl_link'] or -1))
        n_sent = sum(1 for i in range(N) if tab[i] == 0xDEADBEEF)
        n_pre = sum(1 for i in range(N) if tab[i] == MARKER_PRE)
        n_c = sum(1 for i in range(N) if tab[32 + i] == MARKER_CALLEE)
        n_r1 = sum(1 for i in range(N) if tab[32 + i] == MARKER_R1)
        n_r2 = sum(1 for i in range(N) if tab[64 + i] == MARKER_R2)
        n_f = sum(1 for i in range(N) if tab[96 + i] == MARKER_FALL)
        rec['analysis'] = {'link_lanes': n_link, 'sentinel_lanes': n_sent,
                           'pre_lanes': n_pre, 'callee_lanes': n_c,
                           'r1_lanes': n_r1, 'r2_lanes': n_r2, 'fall_lanes': n_f}
        if n_f == N and not (n_c or n_r1 or n_r2):
            rec['interpretation'] = 'falls_through_no_transfer'
        elif (n_c == N or n_r1 == N) and n_f == 0:
            rec['interpretation'] = 'transfers_despite_empty_mask'
        elif not (n_c or n_r1 or n_r2 or n_f):
            rec['interpretation'] = 'group_ends_no_stores'
        else:
            rec['interpretation'] = (f'mixed_link{n_link}_sent{n_sent}_c{n_c}'
                                     f'_r1{n_r1}_r2{n_r2}_f{n_f}')
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    ap.add_argument('--case', choices=list(CASES) + ['all'], default='all')
    args = ap.parse_args()
    cases = list(CASES) if args.case == 'all' else [args.case]
    if args.mode == 'offline':
        print('=== Building and validating probes ===')
        for c in cases:
            print(f'--- case {c} ---')
            probe = build_probe(c)
            print(f"  island_pc={probe['gate']['island_pc']:#x}")
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    for c in cases:
        gpu_safety.require_budget(1)
        print(f'--- case {c} ---')
        probe = build_probe(c)
        rec = hardware(probe, f'empty-mask-{c}')
        print(f"  Variant ok: {rec['variant'].get('ok')}")
        print(f"  Recovery control: {rec.get('recovery_control_passed')}")
        if 'analysis' in rec:
            print(f"  Analysis: {rec['analysis']}")
        print(f"  Interpretation: {rec.get('interpretation')}")
        print(f"  Saved to: {DATA / ('empty-mask-' + c + '.json.gz')}")
        if rec.get('halted'):
            print(f"  HALTED: {rec['halted']}; stopping batch.")
            return


if __name__ == '__main__':
    main()
