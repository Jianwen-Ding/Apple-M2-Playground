#!/usr/bin/env python3
"""Priority B/F follow-up: nested calls under a partial mask.

Even lanes take an outer direct call; odd lanes are dragged along masked
(the whole group transfers). The outer callee stores the outer link + OUT
marker, saves r1, makes a uniform inner direct call, pops (inner ret leaves
depth 2 on executing lanes), restores r1, and returns. The inner callee
stores the inner link + IN marker and returns.
Caller post-call: pop, CONT1, pop, CONT2, stop.

Slot map (per-lane, table has 192 words):
  table[gid]        outer link
  table[32+gid]     inner link
  table[64+gid]     OUT marker (outer callee body)
  table[96+gid]     IN marker (inner callee body)
  table[128+gid]    CONT1 (caller post-call, after first pop)
  table[160+gid]    CONT2 (caller post-call, after second pop)

Expected under the unified model: even lanes hold both links and both callee
markers; CONT1 on odd (dragged) lanes; CONT2 on all lanes. Hardware decides.

Default: offline simulator validation (all-active control exact; variant must
match the same oracle). --hardware submits.
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
SCRATCH = Path('/scratch/apple-m2-playground/nested-partial')

MARKER_OUT = 0x0ABC0001
MARKER_IN = 0x1ABC0001
MARKER_C1 = 0xC0FFEE01
MARKER_C2 = 0xC0FFEE02
N = 32
WG = 32
REGS = 64
O_BODY = 1024
I_BODY = 1536
TABLE_WORDS = 192


def build_bodies(all_active):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]

    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # outer-link index
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # inner-link index
    setup += mov(27, 64)
    setup += e('iadd r22, r29, r27')    # OUT index
    setup += mov(27, 96)
    setup += e('iadd r24, r29, r27')    # IN index (r23 unusable)
    setup += mov(27, 128)
    setup += e('iadd r25, r29, r27')    # CONT1 index
    setup += mov(27, 160)
    setup += e('iadd r26, r29, r27')    # CONT2 index
    if not all_active:
        # even lanes active (parity == 0); mask stays set (bare if, no pop).
        # NOTE: r26 holds the CONT2 index; use r28 for the mask zero.
        setup += mov(27, 1)
        setup += e('and r23, r29, r27')  # parity in r23 (value reg, fine)
        setup += mov(28, 0)
        setup += e('if_icmp r0l, seq, r23, r28, 1')

    call_pc = site + len(setup) + (0 if all_active else 6)
    post_pc = call_pc + 6
    ocallee_pc = site + O_BODY
    off = ocallee_pc - call_pc
    call_island = (0xC010 | ((off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')

    # Caller post-call: pop, CONT1, pop, CONT2, stop.
    post = e('pop_exec r0l, 1')
    post += mov(23, MARKER_C1)
    post += st(23, 8, 25)
    post += wait
    post += e('pop_exec r0l, 1')
    post += mov(23, MARKER_C2)
    post += st(23, 8, 26)
    post += wait
    post += stop

    # Outer callee: outer link, OUT, save r1, inner call, pop, restore, ret.
    ocallee = st(1, 8, 20)
    ocallee += mov(23, MARKER_OUT)
    ocallee += st(23, 8, 22)
    ocallee += e('iadd r29, r1, 0')
    inner_pc = site + I_BODY
    inner_from = ocallee_pc + len(ocallee)
    inner_off = inner_pc - inner_from
    ocallee += (0xC010 | ((inner_off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
    ocallee += e('pop_exec r0l, 2')    # inner ret leaves depth 2
    ocallee += e('iadd r1, r29, 0')
    ocallee += e('ret r1') + wait + wait

    # Inner callee: inner link, IN, ret.
    icallee = st(1, 8, 21)
    icallee += mov(23, MARKER_IN)
    icallee += st(23, 8, 24)
    icallee += wait
    icallee += e('ret r1') + wait + wait

    body = setup
    if not all_active:
        body += RS.jnone(6 + len(call_island))
    body += call_island + post
    assert len(body) <= O_BODY, len(body)
    body += stop * ((O_BODY - len(body)) // 2)
    assert len(body) == O_BODY
    body += ocallee
    assert len(body) <= I_BODY, len(body)
    body += stop * ((I_BODY - len(body)) // 2)
    assert len(body) == I_BODY
    body += icallee
    code = drm.build_main(body)
    return code, call_pc, post_pc


def build_probe():
    cov.install()
    code, call_pc, post_pc = build_bodies(all_active=False)
    control, ctrl_call_pc, _ = build_bodies(all_active=True)
    table = [0] * TABLE_WORDS
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    # All-active control: uniform round trip at both levels; outer ret and
    # inner ret each leave depth 2, so CONT1 skipped, CONT2 everywhere.
    c_olink = 0x2000 + ctrl_call_pc + 6
    # inner call site: control outer callee starts at site+O_BODY; inner call
    # offset within ocallee: st(8)+mov(6)+st(8)+iadd(8) = 30 bytes in.
    c_ilink = 0x2000 + (drm.control_main()[1] + O_BODY) + 30 + 6
    expected_ctrl = ([c_olink] * N + [c_ilink] * N + [MARKER_OUT] * N
                     + [MARKER_IN] * N + [0] * N + [MARKER_C2] * N)
    # Variant: even lanes do the nested trip (uniform direct calls drag the
    # whole group; masked odd lanes ride along without storing). The inner
    # divergent ret is a full reconvergence (all lanes to depth 2), so the
    # outer post-inner pop reactivates everyone and the outer (divergent) ret
    # sets depth 2 again: CONT1 skipped everywhere, CONT2 stored everywhere.
    v_olink = 0x2000 + call_pc + 6
    v_ilink = 0x2000 + (drm.control_main()[1] + O_BODY) + 30 + 6
    expected_var = ([v_olink if i % 2 == 0 else 0 for i in range(N)]
                    + [v_ilink if i % 2 == 0 else 0 for i in range(N)]
                    + [MARKER_OUT if i % 2 == 0 else 0 for i in range(N)]
                    + [MARKER_IN if i % 2 == 0 else 0 for i in range(N)]
                    + [0] * N
                    + [MARKER_C2] * N)

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        c_out, c_tab = cov.simulate(control, N, WG, REGS, 0, table)
        assert (c_out, c_tab) == (expected_out, expected_ctrl), \
            f"control mismatch: olink={c_tab[0]:#x} ilink={c_tab[32]:#x}"
        # The nested inner ret is divergent when counting inactive lanes
        # (active hold the link, inactive hold stale r1), so lane 0 wins and
        # the whole group reconverges to depth 2. The variant must simulate
        # exactly (CONT1 nowhere, CONT2 everywhere).
        v_out, v_tab = cov.simulate(code, N, WG, REGS, 0, table)
        assert (v_out, v_tab) == (expected_out, expected_var), \
            f"variant mismatch vs oracle"
        print("  Simulator reproduces the partial nested variant exactly.")
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    cov.gate(code, allow=('call', 'ret'))
    try:
        cov.simulate(code, N, WG, REGS, 0, table)
        raise AssertionError('ret should be rejected in default mode')
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc)
    print("  All-active nested control validated.")
    return dict(code=code, control=control, table=table, n=N, wg=WG, regs=REGS,
                expected=(expected_out, expected_ctrl),
                expected_var=(expected_out, expected_var),
                gate={'call_pc': call_pc, 'post_pc': post_pc,
                      'outer_link': v_olink, 'inner_link': v_ilink})


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
            gpu_safety.record(f'nested-partial {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    name = 'nested-partial'
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
        if (rec['variant']['out'], rec['variant']['table_after']) == p['expected_var']:
            rec['interpretation'] = 'nested_partial_matches_dragging_model'
        else:
            tab = rec['variant']['table_after']
            ol = sum(1 for i in range(N) if tab[i] == p['gate']['outer_link'])
            il = sum(1 for i in range(N) if tab[32 + i] == p['gate']['inner_link'])
            rec['interpretation'] = f'mismatch_olink{ol}_ilink{il}'
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
    print(f"  call_pc={probe['gate']['call_pc']:#x}")
    if args.mode == 'offline':
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f"  Variant ok: {rec['variant'].get('ok')}")
    print(f"  Recovery control: {rec.get('recovery_control_passed')}")
    print(f"  Interpretation: {rec.get('interpretation')}")
    print(f"  Saved to: {DATA / 'nested-partial.json.gz'}")


if __name__ == '__main__':
    main()
