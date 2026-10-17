#!/usr/bin/env python3
"""Priority D: two divergent register-call targets (lane parity).

Even lanes call callee A, odd lanes call callee B (per-lane r30). Each
callee stores the link + its marker and returns via `ret r1` to the common
caller continuation, which pops twice with a store after each pop.

Slot map (per-lane, indexed by gid):
  table[gid]      link (set by call; pre-marker survives where no store runs)
  table[32+gid]   callee marker (MARK_A even / MARK_B odd)
  table[64+gid]   CONT1 (caller post-call, after first pop)
  table[96+gid]   CONT2 (caller post-call, after second pop)

Default: offline simulator/surrogate validation only. --hardware submits.

Callees never fall into each other (each ends in its ret island + stops).
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
SCRATCH = Path('/scratch/apple-m2-playground/divergent-call')

MARKER_PRE = 0xAAAA0001
MARKER_A = 0xA1A10001
MARKER_B = 0xB2B20001
MARKER_C1 = 0xC0FFEE01
MARKER_C2 = 0xC0FFEE02
N = 32
WG = 32
REGS = 64
TA_BODY = 1024
TB_BODY = 1536


def build_bodies(divergent=True, swap=False, lane0b=False):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]
    addr_a = 0x2000 + site + TA_BODY
    addr_b = 0x2000 + site + TB_BODY
    # swap: even lanes -> B, odd lanes -> A (default: even -> A, odd -> B).
    # lane0b: lane 0 -> B, lanes 1..31 -> A (tests lane-0-wins vs majority).

    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # link index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # marker index = 32 + gid
    setup += mov(27, 64)
    setup += e('iadd r22, r29, r27')    # cont1 index = 64 + gid
    setup += mov(27, 96)
    setup += e('iadd r25, r29, r27')    # cont2 index = 96 + gid (r23 unusable)
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)              # pre-marker for all lanes
    setup += wait
    setup += mov(1, 0xDEADBEEF)        # clobber r1 (call sets link)
    if divergent:
        if lane0b:
            # Lane 0 -> B, lanes 1..31 -> A.
            setup += mov(30, addr_a)        # default A
            setup += mov(27, 0)
            setup += RS.if_else('if_icmp r0l, seq, r29, r27, 1', None,
                                mov(30, addr_b), b'')
        else:
            # Default: r30 = A for even lanes, B for odd lanes. Swapped:
            # even -> B, odd -> A. Set before any mask change.
            default_addr = addr_a if swap else addr_b
            lane_addr = addr_b if swap else addr_a
            setup += mov(30, default_addr)   # default (odd lanes keep it)
            setup += mov(27, 1)
            setup += e('and r24, r29, r27')  # parity bit
            setup += mov(26, 0)
            setup += RS.if_else('if_icmp r0l, seq, r24, r26, 1', None,
                                mov(30, lane_addr), b'')
    else:
        setup += mov(30, addr_a)

    call_pc = site + len(setup)
    post_pc = call_pc + 6
    # Caller continuation: two pops with a store after each (covers depth 1/2).
    post = e('pop_exec r0l, 1')
    post += mov(23, MARKER_C1)
    post += st(23, 8, 22)
    post += wait
    post += e('pop_exec r0l, 1')
    post += mov(23, MARKER_C2)
    post += st(23, 8, 25)
    post += wait
    post += stop

    callee_a = st(1, 8, 20)
    callee_a += mov(23, MARKER_A)
    callee_a += st(23, 8, 21)
    callee_a += wait
    callee_a += e('ret r1') + wait + wait

    callee_b = st(1, 8, 20)
    callee_b += mov(23, MARKER_B)
    callee_b += st(23, 8, 21)
    callee_b += wait
    callee_b += e('ret r1') + wait + wait

    island = e('call r30') + wait + wait
    assert len(island) == 6
    body = setup + island + post
    assert len(body) <= TA_BODY, f"body overran callee A: {len(body)}"
    body += stop * ((TA_BODY - len(body)) // 2)
    assert len(body) == TA_BODY
    body += callee_a
    assert len(body) <= TB_BODY, f"callee A overran B: {len(body)}"
    body += stop * ((TB_BODY - len(body)) // 2)
    assert len(body) == TB_BODY
    body += callee_b
    code = drm.build_main(body)
    return code, call_pc, post_pc


def build_probe(swap=False, lane0b=False):
    cov.install()
    code, call_pc, post_pc = build_bodies(divergent=True, swap=swap, lane0b=lane0b)
    ctrl_a, ctrl_call_pc, _ = build_bodies(divergent=False)
    table = [0] * 128
    expected_out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    link_val = 0x2000 + call_pc + 2
    # Uniform-A control: link + MARK_A everywhere; depth-2 return so CONT1
    # skipped, CONT2 everywhere. Control has its own (shorter) call site.
    ctrl_link = 0x2000 + ctrl_call_pc + 2
    expected_ctrl = ([ctrl_link] * N + [MARKER_A] * N + [0] * N + [MARKER_C2] * N)
    # Divergent hope: link everywhere (uniform link), per-assignment markers,
    # CONT1 none, CONT2 everywhere.
    if lane0b:
        expected_div = ([link_val if i == 0 else 0 for i in range(N)]
                        + [MARKER_B if i == 0 else MARKER_A for i in range(N)]
                        + [0] * N + [MARKER_C2] * N)
    elif not swap:
        expected_div = ([link_val] * N
                        + [MARKER_A if i % 2 == 0 else MARKER_B for i in range(N)]
                        + [0] * N + [MARKER_C2] * N)
    else:
        expected_div = ([link_val] * N
                        + [MARKER_B if i % 2 == 0 else MARKER_A for i in range(N)]
                        + [0] * N + [MARKER_C2] * N)

    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        c_out, c_tab = cov.simulate(ctrl_a, N, WG, REGS, 0, table)
        assert (c_out, c_tab) == (expected_out, expected_ctrl), \
            f"control mismatch: link0={c_tab[0]:#x} m32={c_tab[32]:#x} c1={c_tab[64]:#x} c2={c_tab[96]:#x}"
        try:
            cov.simulate(code, N, WG, REGS, 0, table)
        except RuntimeError as exc:
            assert 'divergent' in str(exc), f"unexpected rejection: {exc}"
            print(f"  Simulator rejects divergent callreg as expected: {exc}")
        else:
            raise AssertionError('divergent callreg unexpectedly accepted by simulator')
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']

    cov.gate(code, allow=('call', 'ret'))
    print("  Uniform-A control validated; divergent variant rejected as required.")
    if lane0b:
        label = 'lane0->B,rest->A'
    else:
        label = 'swap(even->B,odd->A)' if swap else 'even->A,odd->B'
    print(f"  Assignment: {label}.")
    return dict(
        code=code, control=ctrl_a, table=table, n=N, wg=WG, regs=REGS,
        swap=swap, lane0b=lane0b,
        expected=(expected_out, expected_ctrl),
        expected_div=(expected_out, expected_div),
        gate={'call_pc': call_pc, 'post_pc': post_pc, 'link': link_val,
              'swap': swap, 'lane0b': lane0b,
              'variant_rejected_divergent': True, 'control_matches_oracle': True},
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
            gpu_safety.record(f'divergent-call {label}')
    return r


def matches(r, expected):
    return r['ok'] and (r.get('out'), r.get('table_after')) == expected


def hardware(p):
    if p.get('lane0b'):
        name = 'divergent-callreg-lane0b'
    else:
        name = 'divergent-callreg-swap' if p.get('swap') else 'divergent-callreg'
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
        ma = [i for i in range(N) if tab[32 + i] == MARKER_A]
        mb = [i for i in range(N) if tab[32 + i] == MARKER_B]
        c1 = [i for i in range(N) if tab[64 + i] == MARKER_C1]
        c2 = [i for i in range(N) if tab[96 + i] == MARKER_C2]
        rec['analysis'] = {'link': link, 'mark_a': ma, 'mark_b': mb, 'cont1': c1, 'cont2': c2}
        if (rec['variant']['out'], rec['variant']['table_after']) == p['expected_div']:
            rec['interpretation'] = 'divergent_calls_both_callees_rejoin'
        elif not ma and mb == list(range(N)):
            rec['interpretation'] = 'only_B_ran'
        elif ma == list(range(N)) and not mb:
            rec['interpretation'] = 'only_A_ran'
        elif not (ma or mb):
            rec['interpretation'] = 'neither_callee_ran'
        else:
            rec['interpretation'] = f"partial_A{len(ma)}_B{len(mb)}_C1{len(c1)}_C2{len(c2)}"
    elif not rec['variant'].get('ok'):
        rec['interpretation'] = 'variant_failed'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    ap.add_argument('--swap', action='store_true',
                    help='swap targets: even lanes -> B, odd lanes -> A')
    ap.add_argument('--lane0b', action='store_true',
                    help='lane 0 -> B, lanes 1..31 -> A (lane-0-wins vs majority)')
    args = ap.parse_args()
    print('=== Building and validating probe ===')
    probe = build_probe(swap=args.swap, lane0b=args.lane0b)
    print(f"  call_pc={probe['gate']['call_pc']:#x} link={probe['gate']['link']:#x}")
    if args.mode == 'offline':
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware ===')
    rec = hardware(probe)
    print(f"  Variant ok: {rec['variant'].get('ok')}")
    print(f"  Recovery control: {rec.get('recovery_control_passed')}")
    if 'analysis' in rec:
        a = rec['analysis']
        n_even_a = sum(1 for i in a['mark_a'] if i % 2 == 0)
        n_odd_a = sum(1 for i in a['mark_a'] if i % 2 == 1)
        n_even_b = sum(1 for i in a['mark_b'] if i % 2 == 0)
        n_odd_b = sum(1 for i in a['mark_b'] if i % 2 == 1)
        print(f"  MARK_A even/odd: {n_even_a}/{n_odd_a}; MARK_B even/odd: {n_even_b}/{n_odd_b}")
    print(f"  Interpretation: {rec.get('interpretation')}")
    print(f"  Saved to: {DATA / (rec['name'] + '.json.gz')}")


if __name__ == '__main__':
    main()
