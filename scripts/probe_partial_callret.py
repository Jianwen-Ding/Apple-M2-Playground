#!/usr/bin/env python3
"""Priority B (part 3): combined partial-mask call + return round trip.

Odd lanes are active via if_icmp on the gid. `call` transfers to a callee
that stores the link + CALLEE marker and returns via `ret r1`. The caller
post-call pops twice, storing CONT1 (after one pop) and CONT2 (after two
pops) in separate per-lane slots.

Default: offline simulator/surrogate validation only. --hardware submits.

Slot map (per-lane, indexed by gid):
  table[gid]      link (stored in callee)
  table[32+gid]   CALLEE marker (stored in callee)
  table[64+gid]   CONT1 (caller post-call, after first pop)
  table[96+gid]   CONT2 (caller post-call, after second pop)

Divergence hypothesis: CONT1 = even lanes only, CONT2 = all lanes.
Lockstep hypothesis: CONT1 = none, CONT2 = odd lanes only.
Hardware is the oracle; both outcomes are informative.
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
SCRATCH = Path('/scratch/apple-m2-playground/partial-mask-callret')

MARKER_PRE = 0xAAAA0001
MARKER_CALLEE = 0xF00D0001
MARKER_CONT1 = 0xC0FFEE01
MARKER_CONT2 = 0xC0FFEE02
N = 32
WG = 32
REGS = 64


def build_bodies():
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')

    setup = e('iadd r29, r1, 0')       # save gid (call clobbers r1)
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # link index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # callee-marker index = 32 + gid
    setup += mov(27, 64)
    setup += e('iadd r22, r29, r27')    # cont1 index = 64 + gid
    setup += mov(27, 96)
    setup += e('iadd r24, r29, r27')    # cont2 index = 96 + gid (r23 unusable as store index)
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)              # pre-marker for all lanes
    setup += wait
    setup += mov(1, 0xDEADBEEF)        # clobber r1 with sentinel
    # odd lanes active (r25 scratch; r24 holds the cont2 index)
    setup += mov(27, 1)
    setup += e('and r25, r29, r27')
    setup += e('if_icmp r0l, ueq, r25, r27, 1')

    site = drm.control_main()[1]
    call_island = b'CALL6'  # placeholder for 6-byte call
    jnone = RS.jnone(6 + 6)  # skip the call when no lane is active
    call_pc = site + len(setup) + len(jnone)

    # Caller post-call: two pops with a store after each.
    post = e('pop_exec r0l, 1')
    post += mov(23, MARKER_CONT1)
    post += st(23, 8, 22)
    post += wait
    post += e('pop_exec r0l, 1')
    post += mov(23, MARKER_CONT2)
    post += st(23, 8, 24)
    post += wait
    post += stop

    callee_pc = call_pc + 6 + len(post)
    call_off = callee_pc - call_pc
    call_instr = (0xC010 | ((call_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
    assert len(call_instr) == 6

    # Callee: store link + CALLEE marker, then return via the link.
    callee = st(1, 8, 20)               # link (or sentinel if call skipped it)
    callee += mov(23, MARKER_CALLEE)
    callee += st(23, 8, 21)
    callee += wait
    callee += e('ret r1') + wait + wait

    body = setup + jnone + call_instr + post
    # callee must start at callee_pc; pad with stops (never executed: post ends in stop)
    assert len(body) <= callee_pc - site, f"body overran callee: {len(body)} > {callee_pc - site}"
    body += stop * ((callee_pc - site - len(body)) // 2)
    assert site + len(body) == callee_pc
    body += callee
    code = drm.build_main(body)

    # Wait surrogate: call island -> waits. All lanes fall through to post
    # with the odd/even mask still set; first pop reactivates everyone.
    surrogate_wait = code[:call_pc] + wait * 3 + code[call_pc + 6:]

    # All-active control: same round trip, no mask.
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
    csetup += mov(1, 0xDEADBEEF)
    c_site = drm.control_main()[1]
    c_call_pc = c_site + len(csetup)
    c_callee_pc = c_call_pc + 6 + len(post)
    c_off = c_callee_pc - c_call_pc
    c_call = (0xC010 | ((c_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
    cbody = csetup + c_call + post
    cbody += stop * ((c_callee_pc - c_site - len(cbody)) // 2)
    cbody += callee
    control = drm.build_main(cbody)
    return code, surrogate_wait, control, call_pc, callee_pc, post, callee


def build_probe():
    cov.install()
    code, surrogate_wait, control, call_pc, callee_pc, post, callee = build_bodies()
    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]

    # All-active control: link + CALLEE everywhere; CONT1 nowhere (first pop
    # leaves r0l=1 for all returning lanes); CONT2 everywhere.
    ctrl_link = 0x2000 + (drm.control_main()[1] + len(code) * 0)  # placeholder, fixed below
    # recompute exactly like build_bodies' control prefix
    e, mov = RS.e, RS.mov
    csetup_len = (len(e('iadd r29, r1, 0')) + len(mov(27, 0)) + len(e('iadd r20, r29, r27'))
                  + len(mov(27, 32)) + len(e('iadd r21, r29, r27')) + len(mov(27, 64))
                  + len(e('iadd r22, r29, r27')) + len(mov(27, 96)) + len(e('iadd r24, r29, r27'))
                  + len(mov(23, MARKER_PRE)) + len(RS.agx_loop.store(23, 8, 20)) + len(e('wait 0'))
                  + len(mov(1, 0xDEADBEEF)))
    c_site = drm.control_main()[1]
    ctrl_link = 0x2000 + c_site + csetup_len + 6
    expected_ctrl = ([ctrl_link] * N + [MARKER_CALLEE] * N + [0] * N + [MARKER_CONT2] * N)

    # Wait surrogate (masked, no call): first pop reactivates everyone, so
    # CONT1 lands on all lanes, then CONT2 on all lanes. Pre-marker everywhere.
    expected_wait = ([MARKER_PRE] * N + [0] * N + [MARKER_CONT1] * N + [MARKER_CONT2] * N)

    # Variant, divergence hypothesis: link + CALLEE on odd lanes only;
    # CONT1 on even lanes only; CONT2 on all lanes. The pre-marker survives
    # on even lanes in the link slot (no link store overwrites it there).
    link_val = 0x2000 + call_pc + 6
    expected_div = ([link_val if i % 2 == 1 else MARKER_PRE for i in range(N)]
                    + [MARKER_CALLEE if i % 2 == 1 else 0 for i in range(N)]
                    + [MARKER_CONT1 if i % 2 == 0 else 0 for i in range(N)]
                    + [MARKER_CONT2] * N)
    # Variant, lockstep hypothesis: link + CALLEE on odd lanes; CONT1 nowhere;
    # CONT2 on odd lanes only.
    expected_lock = ([link_val if i % 2 == 1 else MARKER_PRE for i in range(N)]
                     + [MARKER_CALLEE if i % 2 == 1 else 0 for i in range(N)]
                     + [0] * N
                     + [MARKER_CONT2 if i % 2 == 1 else 0 for i in range(N)])

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        c_out, c_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (c_out, c_tab) == (expected_out, expected_ctrl), \
            f"control mismatch: link0={c_tab[0]:#x} cont1={c_tab[64]:#x} cont2={c_tab[96]:#x}"
        w_out, w_tab = cov.simulate(surrogate_wait, N, WG, REGS, 0, table)
        assert (w_out, w_tab) == (expected_out, expected_wait), \
            f"wait-surrogate mismatch: cont1={w_tab[64:68]} cont2={w_tab[96:100]}"
        try:
            cov.simulate(code, N, WG, REGS, 0, table)
        except RuntimeError as exc:
            assert 'only all-active' in str(exc), f"unexpected rejection: {exc}"
            print(f"  Simulator rejects masked round trip as expected: {exc}")
        else:
            raise AssertionError('masked call+ret unexpectedly accepted by simulator')
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    cov.gate(code, allow=('call', 'ret'))
    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('ret should be rejected in default mode')
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc), f"unexpected error: {exc}"

    print("  Control (all-active round trip) validated.")
    print("  Wait surrogate (masked post-call) validated.")
    return dict(
        code=code, control=control, table=table, n=N, wg=WG, regs=REGS,
        expected=(expected_out, expected_ctrl),
        expected_div=(expected_out, expected_div),
        expected_lock=(expected_out, expected_lock),
        gate={'call_pc': call_pc, 'callee_pc': callee_pc, 'link': link_val,
              'variant_rejected_masked_ret': True,
              'control_matches_oracle': True,
              'wait_surrogate_matches_oracle': True},
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
            gpu_safety.record(f'partial-mask-callret {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    name = 'partial-mask-callret'
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
        link = [i for i in range(N) if tab[i] == p['gate']['link']]
        callee = [i for i in range(N) if tab[32 + i] == MARKER_CALLEE]
        cont1 = [i for i in range(N) if tab[64 + i] == MARKER_CONT1]
        cont2 = [i for i in range(N) if tab[96 + i] == MARKER_CONT2]
        rec['analysis'] = {'link_lanes': link, 'callee_lanes': callee,
                           'cont1_lanes': cont1, 'cont2_lanes': cont2}
        if (rec['variant']['out'], rec['variant']['table_after']) == p['expected_div']:
            rec['interpretation'] = 'divergence_true_lanes_split_then_rejoin'
        elif (rec['variant']['out'], rec['variant']['table_after']) == p['expected_lock']:
            rec['interpretation'] = 'lockstep_active_only_throughout'
        else:
            rec['interpretation'] = (f"unmatched_link{len(link)}_callee{len(callee)}"
                                     f"_cont1{len(cont1)}_cont2{len(cont2)}")
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    args = ap.parse_args()
    print('=== Building and validating probe ===')
    probe = build_probe()
    print(f"  call_pc={probe['gate']['call_pc']:#x} callee={probe['gate']['callee_pc']:#x}")
    if args.mode == 'offline':
        print('Simulator/surrogate validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f"  Variant ok: {rec['variant'].get('ok')}")
    print(f"  Recovery control: {rec.get('recovery_control_passed')}")
    if 'analysis' in rec:
        a = rec['analysis']
        print(f"  link: {a['link_lanes']}")
        print(f"  callee: {a['callee_lanes']}")
        print(f"  cont1: {a['cont1_lanes']}")
        print(f"  cont2: {a['cont2_lanes']}")
    print(f"  Interpretation: {rec.get('interpretation')}")
    print(f"  Saved to: {DATA / 'partial-mask-callret.json.gz'}")


if __name__ == '__main__':
    main()
