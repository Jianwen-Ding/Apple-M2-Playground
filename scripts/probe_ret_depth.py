#!/usr/bin/env python3
"""Ret depth on partial masks + lane-0-masked divergent ret.

Case P (partial-uniform): odd lanes active (mask persists into the ret),
uniform ret target B. Inactive (even) lanes fall through to a pop + FALL +
stop path. Landing B has pop1/M1/pop1/M2/stop: M1-only means depth 1,
M2-only means depth 2.

Case L (lane0out): lane 0 -> A, lanes 1..31 -> B, with lane 0 masked out
(mask persists). Lane 0 falls through to FALL. Both landings carry the
pop1/M/pop1/M structure, so one dispatch reads out both the winning target
and the arrival depth.

Slot map (per-lane, indexed by gid; table has 192 words):
  table[gid]        pre-marker
  table[32+gid]     A1 (landing A, after first pop)
  table[64+gid]     A2 (landing A, after second pop)
  table[96+gid]     B1 (landing B, after first pop)
  table[128+gid]    B2 (landing B, after second pop)
  table[160+gid]    FALL (fallthrough path)

Default: offline simulator/surrogate validation only. --hardware submits.
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
SCRATCH = Path('/scratch/apple-m2-playground/ret-depth')

MARKER_PRE = 0xAAAA0001
MARKER_A1 = 0xA1A10001
MARKER_A2 = 0xA1A10002
MARKER_B1 = 0xB1B10001
MARKER_B2 = 0xB1B10002
MARKER_FALL = 0xFA110001
N = 32
WG = 32
REGS = 64
TA_BODY = 1024
TB_BODY = 1536
TABLE_WORDS = 192


def build_bodies(case):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]
    addr_a = 0x2000 + site + TA_BODY
    addr_b = 0x2000 + site + TB_BODY

    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # pre-marker index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # A1 index
    setup += mov(27, 64)
    setup += e('iadd r22, r29, r27')    # A2 index
    setup += mov(27, 96)
    setup += e('iadd r24, r29, r27')    # B1 index
    setup += mov(27, 128)
    setup += e('iadd r25, r29, r27')    # B2 index
    setup += mov(27, 160)
    setup += e('iadd r28, r29, r27')    # FALL index (r23 unusable as index)
    # NOTE: all indices are computed BEFORE the mask below. Masked lanes
    # skip moves, so any index computed under a mask stays 0 on inactive
    # lanes and their stores would all hit table[0].
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)
    setup += wait
    if case == 'partial-uniform':
        # r30 uniform target B for every lane (set before the mask).
        setup += mov(30, addr_b)
        # odd lanes active; mask STAYS SET (bare if, no pop) into the ret.
        # Parity scratch is r23 (value reg; r24 holds the B1 index).
        setup += mov(27, 1)
        setup += e('and r23, r29, r27')
        setup += mov(26, 1)
        setup += e('if_icmp r0l, seq, r23, r26, 1')
    else:
        # lane0out: r30 per lane first (all lanes active), then mask lane 0.
        setup += mov(30, addr_b)        # default B
        setup += mov(27, 0)
        setup += RS.if_else('if_icmp r0l, seq, r29, r27, 1', None,
                            mov(30, addr_a), b'')
        # NOTE: if_else pops, restoring full mask; now mask lane 0 out.
        # (Indices were already computed above, before any mask change.)
        setup += mov(27, 0)
        setup += e('if_icmp r0l, ugt, r29, r27, 1')  # active iff gid != 0

    ret_pc = site + len(setup)
    island = e('ret r30') + wait + wait
    assert len(island) == 6
    # Safety: skip the island when no lane is active.
    skip = RS.jnone(6 + len(island))

    # Fallthrough: lanes that skip the island pop back and store FALL.
    fall = e('pop_exec r0l, 1')
    fall += mov(23, MARKER_FALL)
    fall += st(23, 8, 28)
    fall += wait
    fall += stop

    la = e('pop_exec r0l, 1') + mov(23, MARKER_A1) + st(23, 8, 21) + wait
    la += e('pop_exec r0l, 1') + mov(23, MARKER_A2) + st(23, 8, 22) + wait + stop
    lb = e('pop_exec r0l, 1') + mov(23, MARKER_B1) + st(23, 8, 24) + wait
    lb += e('pop_exec r0l, 1') + mov(23, MARKER_B2) + st(23, 8, 25) + wait + stop

    body = setup + skip + island + fall
    body += stop * ((TA_BODY - len(body)) // 2)
    assert len(body) == TA_BODY, len(body)
    body += la
    body += stop * ((TB_BODY - len(body)) // 2)
    assert len(body) == TB_BODY, len(body)
    body += lb
    code = drm.build_main(body)
    return code, ret_pc


def build_probe(case):
    cov.install()
    code, ret_pc = build_bodies(case)
    table = [0] * TABLE_WORDS
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    site = drm.control_main()[1]
    # Jump surrogates validate the landing + fallthrough paths (whole group
    # lands; masked lanes are dragged along, then pops reactivate everyone).
    for tgt, marks in ((TA_BODY, (MARKER_A1, MARKER_A2)), (TB_BODY, (MARKER_B1, MARKER_B2))):
        e = RS.e
        jump = e(f'jmp_exec_any pc{site + tgt - ret_pc:+}', f'jmp_exec_any pc{site + tgt - ret_pc:+}')
        assert len(jump) == 6
        sur = code[:ret_pc] + jump + code[ret_pc + 6:]
        os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
        try:
            s_out, s_tab = cov.simulate(sur, N, WG, REGS, 0, table)
        finally:
            del os.environ['AGX_EXPERIMENTAL_RET']
        exp = ([MARKER_PRE] * N + [0] * N * 5)
        base = 32 if tgt == TA_BODY else 96
        exp[base:base + N] = [marks[0]] * N
        exp[base + 32:base + 64] = [marks[1]] * N
        assert (s_out, s_tab) == (expected_out, exp), f"{case} jump surrogate mismatch"
    print(f"  {case}: jump surrogates validated.")
    # Uniform partial-mask ret is now modelled (active lanes depth 2,
    # dragged lanes keep depth 1, pop underflow is a no-op): the variant
    # must simulate exactly.
    if case == 'partial-uniform':
        b1 = set(range(0, N, 2))   # even (dragged) lanes store B1
    else:
        b1 = {0}                    # lane 0 (dragged) stores B1
    expected_var = ([MARKER_PRE] * N + [0] * N + [0] * N
                    + [MARKER_B1 if i in b1 else 0 for i in range(N)]
                    + [MARKER_B2] * N + [0] * N)
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        v_out, v_tab = cov.simulate(code, N, WG, REGS, 0, table)
        assert (v_out, v_tab) == (expected_out, expected_var), \
            f"{case} variant mismatch: b1={[i for i in range(N) if v_tab[96+i] == MARKER_B1]}"
        print(f"  Simulator reproduces the {case} variant exactly.")
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']
    cov.gate(code, allow=('ret',))
    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('ret should be rejected in default mode')
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc)
    return dict(code=code, table=table, n=N, wg=WG, regs=REGS, mode=case,
                gate={'ret_pc': ret_pc, 'case': case,
                      'variant_matches_oracle': True, 'surrogates_validated': True})


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
            gpu_safety.record(f'ret-depth {label}')
    return r


def hardware(p):
    name = f"ret-depth-{p['mode']}"
    path = DATA / f'{name}.json.gz'
    if path.exists():
        raise SystemExit(f'refusing to overwrite {path}')
    gpu_safety.require_budget(1)
    DATA.mkdir(parents=True, exist_ok=True)
    runner = bench.Runner(SCRATCH / name)
    exp_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    rec = dict(
        name=name,
        utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        before={'budget_used': len(gpu_safety.used()), 'boot_id': gpu_safety.boot_id()},
        code=p['code'].hex(), table_in=p['table'],
        n=p['n'], wg=p['wg'], regs=p['regs'],
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

    def matches(r):
        return r['ok'] and r.get('out') == exp_out and len(r.get('table_after', [])) >= TABLE_WORDS

    # Control: jump-to-B surrogate (validates landing + fallthrough + recovery).
    e = RS.e
    site = drm.control_main()[1]
    jump = e(f'jmp_exec_any pc{site + TB_BODY - p["gate"]["ret_pc"]:+}',
             f'jmp_exec_any pc{site + TB_BODY - p["gate"]["ret_pc"]:+}')
    control_code = p['code'][:p['gate']['ret_pc']] + jump + p['code'][p['gate']['ret_pc'] + 6:]
    ctrl = dict(code=control_code, table=p['table'], n=p['n'], wg=p['wg'], regs=p['regs'])

    rec['phase'] = 'pre-control'
    save()
    rec['control_before'] = run_one(runner, ctrl['code'], ctrl, 'control-before')
    if not matches(rec['control_before']):
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
    rec['control_after'] = run_one(runner, ctrl['code'], ctrl, 'control-after')
    rec['recovery_control_passed'] = matches(rec['control_after'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established'
    rec['phase'] = 'finished'
    if rec['variant'].get('ok') and 'table_after' in rec['variant']:
        tab = rec['variant']['table_after']
        a1 = [i for i in range(N) if tab[32 + i] == MARKER_A1]
        a2 = [i for i in range(N) if tab[64 + i] == MARKER_A2]
        b1 = [i for i in range(N) if tab[96 + i] == MARKER_B1]
        b2 = [i for i in range(N) if tab[128 + i] == MARKER_B2]
        fl = [i for i in range(N) if tab[160 + i] == MARKER_FALL]
        rec['analysis'] = {'a1': a1, 'a2': a2, 'b1': b1, 'b2': b2, 'fall': fl}
        # Unified model (2026-10-17): ret sets r0l=2 on lanes ACTIVE at issue
        # and leaves inactive lanes' r0l unchanged; every lane transfers to
        # the winning target. Active lanes skip M1 (need 2 pops); dragged
        # lanes store M1 (need 1 pop); all store M2. No fallthrough ever.
        if p['mode'] == 'partial-uniform':
            odd = set(range(1, N, 2))
            even = set(range(0, N, 2))
            if set(b1) == even and set(b2) == set(range(N)) and not (a1 or a2) and not fl:
                rec['interpretation'] = 'partial_ret_active_depth2_dragged_depth1'
            else:
                rec['interpretation'] = (f"unexpected_a1{len(a1)}_a2{len(a2)}"
                                         f"_b1{len(b1)}_b2{len(b2)}_f{len(fl)}")
        else:
            if len(b2) == N and set(b1) == {0} and not (a1 or a2) and not fl:
                rec['interpretation'] = 'lowest_active_wins_B_active_depth2_dragged_depth1'
            elif len(a2) == N and set(a1) == {0} and not (b1 or b2) and not fl:
                rec['interpretation'] = 'lane0_wins_A_depth_split'
            else:
                rec['interpretation'] = (f"mixed_a1{len(a1)}_a2{len(a2)}"
                                         f"_b1{len(b1)}_b2{len(b2)}_f{len(fl)}")
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    ap.add_argument('--case', choices=['partial-uniform', 'lane0out', 'all'], default='all')
    args = ap.parse_args()
    cases = ['partial-uniform', 'lane0out'] if args.case == 'all' else [args.case]
    if args.mode == 'offline':
        print('=== Building and validating probes ===')
        for c in cases:
            print(f'--- case {c} ---')
            build_probe(c)
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    for c in cases:
        gpu_safety.require_budget(1)
        print(f'--- case {c} ---')
        probe = build_probe(c)
        rec = hardware(probe)
        print(f"  Variant ok: {rec['variant'].get('ok')}")
        print(f"  Recovery control: {rec.get('recovery_control_passed')}")
        if 'analysis' in rec:
            a = rec['analysis']
            print(f"  A1:{len(a['a1'])} A2:{len(a['a2'])} B1:{len(a['b1'])} B2:{len(a['b2'])} FALL:{len(a['fall'])}")
        print(f"  Interpretation: {rec.get('interpretation')}")
        print(f"  Saved to: {DATA / ('ret-depth-' + c + '.json.gz')}")
        if rec.get('halted'):
            print(f"  HALTED: {rec['halted']}; stopping batch.")
            return


if __name__ == '__main__':
    main()
