#!/usr/bin/env python3
"""Priority E: divergent return targets (no call).

Per-lane r30 selects landing A or B (parity; --swap and --lane0b variants).
Each landing pops twice, stores its marker, and stops. There is no
fallthrough path: every lane issues `ret r30`.

Slot map (per-lane, indexed by gid):
  table[gid]      pre-marker (no link in this probe; ret does not set r1)
  table[32+gid]   landing marker (MARK_A / MARK_B)
  table[64+gid]   spare (0)
  table[96+gid]   spare (0)

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
SCRATCH = Path('/scratch/apple-m2-playground/divergent-ret')

MARKER_PRE = 0xAAAA0001
MARKER_A = 0xA1A10001
MARKER_B = 0xB2B20001
N = 32
WG = 32
REGS = 64
TA_BODY = 1024
TB_BODY = 1536


def build_bodies(mode='parity'):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]
    addr_a = 0x2000 + site + TA_BODY
    addr_b = 0x2000 + site + TB_BODY

    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # pre-marker index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # marker index = 32 + gid
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)              # pre-marker for all lanes
    setup += wait
    if mode == 'uniformA':
        setup += mov(30, addr_a)
    elif mode == 'uniformB':
        setup += mov(30, addr_b)
    elif mode == 'parity':              # even -> A, odd -> B
        setup += mov(30, addr_b)
        setup += mov(27, 1)
        setup += e('and r24, r29, r27')
        setup += mov(26, 0)
        setup += RS.if_else('if_icmp r0l, seq, r24, r26, 1', None,
                            mov(30, addr_a), b'')
    elif mode == 'swap':                # even -> B, odd -> A
        setup += mov(30, addr_a)
        setup += mov(27, 1)
        setup += e('and r24, r29, r27')
        setup += mov(26, 0)
        setup += RS.if_else('if_icmp r0l, seq, r24, r26, 1', None,
                            mov(30, addr_b), b'')
    elif mode == 'lane0b':              # lane 0 -> B, rest -> A
        setup += mov(30, addr_a)
        setup += mov(27, 0)
        setup += RS.if_else('if_icmp r0l, seq, r29, r27, 1', None,
                            mov(30, addr_b), b'')
    else:
        raise ValueError(mode)

    ret_pc = site + len(setup)
    island = e('ret r30') + wait + wait
    assert len(island) == 6

    landing_a = e('pop_exec r0l, 2')
    landing_a += mov(23, MARKER_A)
    landing_a += st(23, 8, 21)
    landing_a += wait
    landing_a += stop

    landing_b = e('pop_exec r0l, 2')
    landing_b += mov(23, MARKER_B)
    landing_b += st(23, 8, 21)
    landing_b += wait
    landing_b += stop

    body = setup + island
    body += stop * ((TA_BODY - len(body)) // 2)
    assert len(body) == TA_BODY
    body += landing_a
    body += stop * ((TB_BODY - len(body)) // 2)
    assert len(body) == TB_BODY
    body += landing_b
    code = drm.build_main(body)

    # Jump surrogates (simulation only): whole group lands at one side.
    jump_a = e(f'jmp_exec_any pc{site + TA_BODY - ret_pc:+}', f'jmp_exec_any pc{site + TA_BODY - ret_pc:+}')
    jump_b = e(f'jmp_exec_any pc{site + TB_BODY - ret_pc:+}', f'jmp_exec_any pc{site + TB_BODY - ret_pc:+}')
    assert len(jump_a) == len(island)
    sur_a = code[:ret_pc] + jump_a + code[ret_pc + len(island):]
    sur_b = code[:ret_pc] + jump_b + code[ret_pc + len(island):]
    return code, sur_a, sur_b, ret_pc


def build_probe(mode='parity'):
    cov.install()
    code, sur_a, sur_b, ret_pc = build_bodies(mode)
    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    expected_a = ([MARKER_PRE] * N + [MARKER_A] * N + [0] * N + [0] * N)
    expected_b = ([MARKER_PRE] * N + [MARKER_B] * N + [0] * N + [0] * N)

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        if mode in ('uniformA', 'uniformB'):
            exp = expected_a if mode == 'uniformA' else expected_b
            v_out, v_tab = cov.simulate(code, N, WG, REGS, 0, table)
            assert (v_out, v_tab) == (expected_out, exp), \
                f"{mode} control mismatch: tab32={v_tab[32]:#x}"
        else:
            # Jump surrogates validate both landing paths.
            a_out, a_tab = cov.simulate(sur_a, N, WG, REGS, 0, table)
            assert (a_out, a_tab) == (expected_out, expected_a), "jump-A surrogate mismatch"
            b_out, b_tab = cov.simulate(sur_b, N, WG, REGS, 0, table)
            assert (b_out, b_tab) == (expected_out, expected_b), "jump-B surrogate mismatch"
            # Variant must be rejected (divergent ret unmodelled).
            try:
                cov.simulate(code, N, WG, REGS, 0, table)
            except RuntimeError as exc:
                assert 'divergent' in str(exc), f"unexpected rejection: {exc}"
                print(f"  Simulator rejects divergent ret as expected.")
            else:
                raise AssertionError('divergent ret unexpectedly accepted')
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    cov.gate(code, allow=('ret',))
    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('ret should be rejected in default mode')
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc)

    active = {'uniformA': list(range(N)), 'uniformB': list(range(N)),
              'parity': [i for i in range(N) if i % 2 == 0],
              'swap': [i for i in range(N) if i % 2 == 0],
              'lane0b': [0]}[mode]
    print(f"  Mode {mode}: simulator gates pass.")
    return dict(
        code=code, table=table, n=N, wg=WG, regs=REGS, mode=mode,
        expected=(expected_out, expected_a if mode in ('uniformA',) else expected_out),
        gate={'ret_pc': ret_pc, 'mode': mode,
              'variant_rejected_divergent': mode not in ('uniformA', 'uniformB')},
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
            gpu_safety.record(f'divergent-ret {label}')
    return r


def ctrl_expected(mode):
    # Uniform controls: pre-marker + landing marker everywhere.
    out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    m = MARKER_A if mode == 'uniformA' else MARKER_B
    return (out, [MARKER_PRE] * N + [m] * N + [0] * N + [0] * N)


def hardware(p, ctrl):
    name = f"divergent-ret-{p['mode']}"
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
        code=p['code'].hex(), control_code=ctrl['code'].hex(),
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

    def matches(r, expected):
        return r['ok'] and (r.get('out'), r.get('table_after')) == expected

    rec['phase'] = 'pre-control'
    save()
    rec['control_before'] = run_one(runner, ctrl['code'], ctrl, 'control-before')
    if not matches(rec['control_before'], ctrl_expected(ctrl['mode'])):
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
    rec['recovery_control_passed'] = matches(rec['control_after'], ctrl_expected(ctrl['mode']))
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established'
    rec['phase'] = 'finished'
    if rec['variant'].get('ok') and 'table_after' in rec['variant']:
        tab = rec['variant']['table_after']
        ma = [i for i in range(N) if tab[32 + i] == MARKER_A]
        mb = [i for i in range(N) if tab[32 + i] == MARKER_B]
        z = [i for i in range(N) if tab[32 + i] == 0]
        rec['analysis'] = {'mark_a': ma, 'mark_b': mb, 'zero': z}
        if set(ma) == set(range(0, N, 2)) and set(mb) == set(range(1, N, 2)):
            rec['interpretation'] = 'divergent_ret_both_landings_per_lane'
        elif len(ma) == N and not mb:
            rec['interpretation'] = 'all_land_A'
        elif len(mb) == N and not ma:
            rec['interpretation'] = 'all_land_B'
        elif not (ma or mb):
            rec['interpretation'] = 'no_landing_markers'
        else:
            rec['interpretation'] = f"partial_A{len(ma)}_B{len(mb)}_Z{len(z)}"
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    ap.add_argument('--case', choices=['parity', 'swap', 'lane0b', 'all'], default='all')
    args = ap.parse_args()
    cases = ['parity', 'swap', 'lane0b'] if args.case == 'all' else [args.case]
    if args.mode == 'offline':
        print('=== Building and validating probes ===')
        for c in cases:
            print(f'--- case {c} ---')
            build_probe(c)
        for c in ('uniformA', 'uniformB'):
            print(f'--- control {c} ---')
            build_probe(c)
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    # Controls first (uniformA validates the A path on hardware).
    ctrl = build_probe('uniformA')
    for c in cases:
        gpu_safety.require_budget(1)
        print(f'--- case {c} ---')
        probe = build_probe(c)
        rec = hardware(probe, ctrl)
        print(f"  Variant ok: {rec['variant'].get('ok')}")
        print(f"  Recovery control: {rec.get('recovery_control_passed')}")
        if 'analysis' in rec:
            a = rec['analysis']
            print(f"  A lanes ({len(a['mark_a'])}): {a['mark_a'][:8]}{'...' if len(a['mark_a']) > 8 else ''}")
            print(f"  B lanes ({len(a['mark_b'])}): {a['mark_b'][:8]}{'...' if len(a['mark_b']) > 8 else ''}")
        print(f"  Interpretation: {rec.get('interpretation')}")
        print(f"  Saved to: {DATA / ('divergent-ret-' + c + '.json.gz')}")
        if rec.get('halted'):
            print(f"  HALTED: {rec['halted']}; stopping batch.")
            return


if __name__ == '__main__':
    main()
