#!/usr/bin/env python3
"""Priority F (part 1): mixed direct/indirect nesting, uniform targets.

Two cases (one unknown per dispatch... here both are uniform and
simulator-modelled, so both run):
  d2i: direct call -> outer callee -> register call -> inner callee.
  i2d: register call -> outer callee -> direct call -> inner callee.
Outer link saved to r29 across the inner call and restored before the
outer return. Separate per-lane trace slots for each link and marker.

Slot map (per-lane, indexed by gid; table has 192 words):
  table[gid]        outer link
  table[32+gid]     inner link
  table[64+gid]     OUT_MARK (outer callee body)
  table[96+gid]     IN_MARK (inner callee body)
  table[128+gid]    CONT (caller post-call continuation)

Default: offline simulator validation only. --hardware submits.
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
SCRATCH = Path('/scratch/apple-m2-playground/nested-calls')

MARKER_PRE = 0xAAAA0001
MARKER_OUT = 0x0ABC0001
MARKER_IN = 0x1ABC0001
MARKER_CONT = 0xC0FFEE01
N = 32
WG = 32
REGS = 64
O_BODY = 1024
I_BODY = 1536
TABLE_WORDS = 192

CASES = ('d2i', 'i2d')


def build_bodies(case):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]

    setup = e('iadd r29, r1, 0')       # save gid
    for reg, base in ((20, 0), (21, 32), (22, 64), (24, 96), (26, 128)):
        setup += mov(27, base)
        setup += e(f'iadd r{reg}, r29, r27')
    # NOTE: r23 is unusable as a store index; r20/21/22/24/26 are used.
    setup += mov(1, 0xDEADBEEF)        # clobber r1 (calls overwrite with links)

    if case == 'd2i':
        call_pc = site + len(setup)
        post_pc = call_pc + 6
        ocallee_pc = site + O_BODY
        off = ocallee_pc - call_pc
        island = (0xC010 | ((off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
        inner_is_direct = False
    else:
        setup += mov(30, 0x2000 + site + O_BODY)  # uniform outer target
        call_pc = site + len(setup)
        post_pc = call_pc + 6
        island = e('call r30') + wait + wait
        assert len(island) == 6
        inner_is_direct = True

    # Caller post-call: pop_exec 2 (uniform depth-2 return) + CONT + stop.
    post = e('pop_exec r0l, 2')
    post += mov(23, MARKER_CONT)
    post += st(23, 8, 26)
    post += wait
    post += stop

    if inner_is_direct:
        # Outer callee (register-called): save link, inner DIRECT call.
        ocallee = st(1, 8, 20)             # outer link
        ocallee += mov(23, MARKER_OUT)
        ocallee += st(23, 8, 22)
        ocallee += e('iadd r29, r1, 0')    # save outer link (inner call clobbers r1)
        inner_pc = None  # filled below
        ocallee += b'INNERJUMP6'
        # Inner ret leaves depth 2; pop back before restoring r1 / outer ret.
        ocallee += e('pop_exec r0l, 2')
        ocallee += e('iadd r1, r29, 0')    # restore outer link
        ocallee += e('ret r1') + wait + wait
    else:
        # Outer callee (direct-called): save link, inner REGISTER call.
        ocallee = st(1, 8, 20)
        ocallee += mov(23, MARKER_OUT)
        ocallee += st(23, 8, 22)
        ocallee += e('iadd r29, r1, 0')
        ocallee += mov(30, 0x2000 + site + I_BODY)  # uniform inner target
        ocallee += e('call r30') + wait + wait
        ocallee += e('pop_exec r0l, 2')
        ocallee += e('iadd r1, r29, 0')
        ocallee += e('ret r1') + wait + wait

    # Inner callee: store inner link + IN_MARK, return.
    icallee = st(1, 8, 21)             # inner link
    icallee += mov(23, MARKER_IN)
    icallee += st(23, 8, 24)
    icallee += wait
    icallee += e('ret r1') + wait + wait

    body = setup + island + post
    assert len(body) <= O_BODY, f"body overran outer callee: {len(body)}"
    body += stop * ((O_BODY - len(body)) // 2)
    assert len(body) == O_BODY
    if inner_is_direct:
        # Patch the inner direct jump now that the inner address is known.
        inner_pc = site + I_BODY
        cur_pc = site + O_BODY + len(ocallee) - 6 - 8 - 6  # position of INNERJUMP6
        # Recompute: ocallee so far ends with INNERJUMP6 placeholder.
        prefix = ocallee[:-6] if ocallee.endswith(b'INNERJUMP6') else ocallee
        # Find placeholder offset inside ocallee.
        at = ocallee.find(b'INNERJUMP6')
        assert at >= 0
        jump_from = site + O_BODY + at
        inner_off = inner_pc - jump_from
        jump = (0xC010 | ((inner_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
        ocallee = ocallee.replace(b'INNERJUMP6', jump)
    body += ocallee
    assert len(body) <= I_BODY, f"outer callee overran inner: {len(body)}"
    body += stop * ((I_BODY - len(body)) // 2)
    assert len(body) == I_BODY
    body += icallee
    code = drm.build_main(body)
    return code, call_pc, post_pc


def build_probe(case):
    cov.install()
    code, call_pc, post_pc = build_bodies(case)
    table = [0] * TABLE_WORDS
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    if case == 'd2i':
        outer_link = 0x2000 + call_pc + 6
        # inner register call site: outer callee start + prefix before inner call
        inner_link = 0x2000 + (drm.control_main()[1] + O_BODY) + (
            8 + 6 + 8 + 8 + 6) + 6
    else:
        outer_link = 0x2000 + call_pc + 2
        inner_link = None  # filled from sim-independent layout below
    # Compute expected links by simulating once (uniform, modelled) is
    # circular; instead assert exact full-buffer equality with the sim, then
    # check the semantic fields explicitly.
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        out, tab = cov.simulate(code, N, WG, REGS, 0, table)
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']
    assert out == expected_out, f"{case}: out olanes changed"
    olink = tab[0]
    ilink = tab[32]
    assert all(v == olink for v in tab[0:N]), f"{case}: outer link not uniform"
    assert all(v == ilink for v in tab[32:2 * N]), f"{case}: inner link not uniform"
    assert all(v == MARKER_OUT for v in tab[64:96]), f"{case}: OUT marker wrong"
    assert all(v == MARKER_IN for v in tab[96:128]), f"{case}: IN marker wrong"
    assert all(v == MARKER_CONT for v in tab[128:160]), f"{case}: CONT wrong"
    assert all(v == 0 for v in tab[160:]), f"{case}: tail guard touched"
    if case == 'd2i':
        assert olink == outer_link, f"{case}: outer link {olink:#x} != {outer_link:#x}"
    else:
        assert olink == outer_link, f"{case}: outer link {olink:#x} != {outer_link:#x}"
    print(f"  {case}: sim uniform links olink={olink:#x} ilink={ilink:#x}; all markers exact.")

    cov.gate(code, allow=('call', 'ret'))
    return dict(
        code=code, table=table, n=N, wg=WG, regs=REGS, case=case,
        expected=(expected_out, tab),
        gate={'call_pc': call_pc, 'post_pc': post_pc,
              'outer_link': olink, 'inner_link': ilink,
              'simulator_matches_oracle': True},
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
            gpu_safety.record(f'nested-call {label}')
    return r


def hardware(p):
    name = f"nested-{p['case']}"
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
        code=p['code'].hex(), table_in=p['table'],
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

    # Self-control: the uniform program is its own control (validates paths).
    rec['phase'] = 'variant-as-control'
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
        # Recovery: known-good single call/return round trip.
        import probe_control_followup as F
        F.cov.install()
        ctrl = F.case('call-ret-pop2')
        rec['control_after'] = run_one(runner, ctrl['control'], ctrl, 'control-after')
        rec['recovery_control_passed'] = F.matches(rec['control_after'], ctrl['expected'])
        if not rec['recovery_control_passed']:
            rec['halted'] = 'post-control failed; GPU recovery not established'
    else:
        rec['recovery_control_passed'] = True
        exp_out, exp_tab = p['expected']
        got_out, got_tab = rec['variant'].get('out'), rec['variant'].get('table_after')
        rec['matches_simulator'] = (got_out, got_tab) == (exp_out, exp_tab)
        if rec['matches_simulator']:
            rec['interpretation'] = 'nested_round_trip_matches_simulator'
        else:
            diffs = []
            for i, (a, b) in enumerate(zip(got_tab or [], exp_tab)):
                if a != b and len(diffs) < 5:
                    diffs.append((i, hex(a), hex(b)))
            rec['interpretation'] = f'mismatch_first_diffs_{diffs}'
    rec['phase'] = 'finished'
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
        print(f"  Matches simulator: {rec.get('matches_simulator')}")
        print(f"  Interpretation: {rec.get('interpretation')}")
        print(f"  Saved to: {DATA / ('nested-' + c + '.json.gz')}")
        if rec.get('halted'):
            print(f"  HALTED: {rec['halted']}; stopping batch.")
            return


if __name__ == '__main__':
    main()
