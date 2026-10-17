#!/usr/bin/env python3
"""Priority G (bounded): call/ret pair cost vs jump-pair control.

Unrolled chains of N call/ret pairs through one shared callee, against
matched jump-pair controls (jmp out + jmp back around the same stores).
N = 1, 4, 16 for direct calls; N = 4 for register-indirect calls.

Slot map (per-lane, indexed by gid; table has 640 words):
  table[gid]        pre-marker
  table[32+gid]     callee/block MARK (shared slot, overwritten N times)
  table[64+i*32+gid] CONT_i (post marker of pair i; proves pair i ran)

Per-pair delta = (call + ret + stores) - (2*jmp + stores), reported in
firmware ns with per-sample distributions. A background clock keeper holds
the top GPU clock during the batch (best effort; recorded whether active).

Default: offline simulator validation only. --hardware submits the batch.
"""
import argparse
import gzip
import hashlib
import json
import os
import struct
import subprocess
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
SCRATCH = Path('/scratch/apple-m2-playground/callret-cost')

MARKER_PRE = 0xAAAA0001
MARKER_CALLEE = 0xCA110001
MARKER_CONT_BASE = 0xC0000000
N_REPEATS = 5
CALLEE_BODY = 2048
TABLE_WORDS = 640


def build_pair_chain(n, indirect=False, control=False):
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    site = drm.control_main()[1]

    setup = e('iadd r29, r1, 0')       # save gid
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')    # pre-marker index = gid
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')    # MARK index = 32 + gid
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)
    setup += wait
    if indirect and not control:
        setup += mov(30, 0x2000 + site + CALLEE_BODY)  # uniform callee (code offset)

    body = setup
    for i in range(n):
        slot = 64 + i * 32
        if indirect:
            body += e('call r30') + wait + wait
        else:
            callee_pc = site + CALLEE_BODY
            call_pc = site + len(body)
            off = callee_pc - call_pc
            body += (0xC010 | ((off & 0xFFFFFFFF) << 16)).to_bytes(6, 'little')
        # post: pop_exec 2 (uniform ret leaves depth 2), then CONT_i store
        body += e('pop_exec r0l, 2')
        body += mov(27, slot)
        body += e('iadd r22, r29, r27')
        body += mov(23, MARKER_CONT_BASE + i)
        body += st(23, 8, 22)
        body += wait
    # pad to callee
    assert len(body) <= CALLEE_BODY, f"chain too long for N={n}"
    body += stop * ((CALLEE_BODY - len(body)) // 2)
    assert len(body) == CALLEE_BODY
    callee = mov(23, MARKER_CALLEE)
    callee += st(23, 8, 21)
    callee += wait
    callee += e('ret r1') + wait + wait
    body += callee
    code = drm.build_main(body)
    return code


def build_control_chain(n):
    # Matched control: per unit, a forward jump over a 6-byte filler (3 waits),
    # then the same MARK + post stores as the variant. Per-unit delta vs the
    # variant = (call + ret) - jmp, reported as-is (no jmp-cost assumption).
    e, mov, st = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')

    setup = e('iadd r29, r1, 0')
    setup += mov(27, 0)
    setup += e('iadd r20, r29, r27')
    setup += mov(27, 32)
    setup += e('iadd r21, r29, r27')
    setup += mov(23, MARKER_PRE)
    setup += st(23, 8, 20)
    setup += wait

    body = setup
    for i in range(n):
        slot = 64 + i * 32
        body += e('jmp_exec_any pc+12', 'jmp_exec_any pc+12')  # skip filler
        body += wait * 3                                        # 6-byte filler
        body += mov(23, MARKER_CALLEE)                          # MARK block
        body += st(23, 8, 21)
        body += wait
        body += e('pop_exec r0l, 2')                           # matched pop (no-op here)
        body += mov(27, slot)                                   # post: CONT_i
        body += e('iadd r22, r29, r27')
        body += mov(23, MARKER_CONT_BASE + i)
        body += st(23, 8, 22)
        body += wait
    body += stop
    code = drm.build_main(body)
    return code


def expected_tables(n):
    out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    tab = [MARKER_PRE] * 32 + [MARKER_CALLEE] * 32
    for i in range(n):
        tab += [MARKER_CONT_BASE + i] * 32
    tab += [0] * (TABLE_WORDS - len(tab))
    return out, tab


def build_probe(n, indirect=False):
    cov.install()
    code = build_pair_chain(n, indirect=indirect)
    control = build_control_chain(n)
    table = [0] * TABLE_WORDS
    exp_out, exp_tab = expected_tables(n)
    os.environ['AGX_EXPERIMENTAL_RET'] = 'buffer-pop2'
    try:
        v_out, v_tab = cov.simulate(code, 32, 32, 64, 0, table)
        assert (v_out, v_tab) == (exp_out, exp_tab), f"variant N={n} mismatch"
        c_out, c_tab = cov.simulate(control, 32, 32, 64, 0, table)
        assert (c_out, c_tab) == (exp_out, exp_tab), f"control N={n} mismatch"
    finally:
        del os.environ['AGX_EXPERIMENTAL_RET']
    cov.gate(code, allow=('call', 'ret'))
    print(f"  N={n}{' indirect' if indirect else ''}: variant + control validated.")
    return dict(code=code, control=control, table=table, n=32, wg=32, regs=64,
                expected=(exp_out, exp_tab), pairs=n, indirect=indirect,
                gate={'pairs': n, 'indirect': indirect})


def run_bounded(argv, env, timeout=20, kill_timeout=2):
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
    d.mkdir(exist_ok=True)
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
            gpu_safety.record(f'callret-cost {label}')
    return r


def hardware(probes):
    name = 'callret-cost'
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
        gate={k: p['gate'] for k, p in probes.items()},
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

    # Clock keeper (best effort): holds the top GPU clock during the batch.
    keeper = None
    keeper_stop = SCRATCH / 'keeper-stop'
    try:
        keeper_stop.unlink(missing_ok=True)
        keeper = subprocess.Popen(
            [sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '300',
             '--stop-file', str(keeper_stop)],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)  # let the keeper reach steady state
        rec['keeper'] = {'started': True, 'pid': keeper.pid}
    except Exception as exc:
        rec['keeper'] = {'started': False, 'error': str(exc)}

    def matches(r, expected):
        return r['ok'] and (r.get('out'), r.get('table_after')) == expected

    rec['samples'] = {}
    try:
        for key in sorted(probes):
            p = probes[key]
            rec['samples'][key] = {'variant': [], 'control': []}
            for rep in range(N_REPEATS):
                for kind, blob in (('variant', p['code']), ('control', p['control'])):
                    label = f'{key}-{kind}-r{rep}'
                    r = run_one(runner, blob, p, label)
                    entry = {'ok': r['ok'], 'fw_ns': r.get('fw_ns'),
                             'match': matches(r, p['expected'])}
                    rec['samples'][key][kind].append(entry)
                    save()
                    if r.get('host_process_stuck'):
                        rec['halted'] = 'probe process blocked after SIGKILL; stopping'
                        save()
                        return rec
                    if not r['ok']:
                        time.sleep(2)
    finally:
        if keeper is not None and keeper.poll() is None:
            try:
                keeper_stop.touch()
                keeper.wait(timeout=30)
            except Exception:
                keeper.kill()
            rec['keeper']['stopped'] = keeper.poll() is not None

    # Recovery control: established round trip.
    import probe_control_followup as F
    import coverage as cov2
    cov2.install()
    ctrl = F.case('call-ret-pop2')
    rec['control_after'] = run_one(runner, ctrl['control'], ctrl, 'control-after')
    rec['recovery_control_passed'] = F.matches(rec['control_after'], ctrl['expected'])
    if not rec['recovery_control_passed']:
        rec['halted'] = 'post-control failed; GPU recovery not established'

    # Analysis: per-pair delta from medians.
    import statistics
    rec['analysis'] = {}
    for key in sorted(probes):
        s = rec['samples'][key]
        vf = sorted(e['fw_ns'] for e in s['variant'] if e['ok'] and e['fw_ns'] is not None)
        cf = sorted(e['fw_ns'] for e in s['control'] if e['ok'] and e['fw_ns'] is not None)
        n = probes[key]['gate']['pairs']
        vm = statistics.median(vf) if vf else None
        cm = statistics.median(cf) if cf else None
        rec['analysis'][key] = {
            'variant_ns': vf, 'control_ns': cf,
            'variant_median': vm, 'control_median': cm,
            'per_pair_delta_ns': (vm - cm) / n if vm is not None and cm is not None else None,
        }
    rec['phase'] = 'finished'
    save()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'], default='offline', nargs='?')
    args = ap.parse_args()
    cfgs = [(1, False), (4, False), (16, False), (4, True)]
    if args.mode == 'offline':
        print('=== Building and validating probes ===')
        for n, ind in cfgs:
            print(f'--- N={n}{" indirect" if ind else ""} ---')
            build_probe(n, indirect=ind)
        print('Validation done. Use hardware mode to submit.')
        return
    print('=== Submitting to hardware (with clock keeper) ===')
    probes = {}
    for n, ind in cfgs:
        build_probe(n, indirect=ind)  # gate first
        key = f'N{n}{"-ind" if ind else ""}'
        probes[key] = build_probe(n, indirect=ind)
    rec = hardware(probes)
    for key, a in rec.get('analysis', {}).items():
        print(f"  {key}: per-pair delta = {a['per_pair_delta_ns']} ns "
              f"(variant median {a['variant_median']}, control median {a['control_median']})")
    print(f"  Recovery control: {rec.get('recovery_control_passed')}")
    print(f"  Saved to: {DATA / 'callret-cost.json.gz'}")


if __name__ == '__main__':
    main()
