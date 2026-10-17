#!/usr/bin/env python3
"""One staged ret landing-map probe. Default is offline; --hardware submits one variant.

No return model is trusted. The complete wait surrogate and each direct-jump
landing path must pass agx_run, while the actual ret must be rejected by default.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT.parent / 'AGX-Performance-Simulator'
sys.path.insert(0, str(SIM / 'scripts'))
import coverage as cov
import record_suite as RS
import run_drm_compute as drm
import run_bench as bench
import gpu_safety

RET_PC = 512
VALUE = 1024
LANDINGS = (1024, 1536, 2048, 2560)
N = 32
TABLE = [0] * 128


def build(reenable=None):
    cov.install()
    e, mov, store = RS.e, RS.mov, RS.agx_loop.store
    stop, wait = e('stop'), e('wait 0')
    body = e('iadd r20, r1, 0') + mov(21, 32) + e('iadd r21, r20, r21')
    body += mov(22, 64) + e('iadd r22, r20, r22')
    body += mov(23, 0xfeed0001) + store(23, 8, 20)
    body += mov(30, VALUE) + store(30, 8, 22) + e('wait 0')
    # Keep the implicit link register equal to the explicit target for this first probe.
    body += mov(1, VALUE)
    site = drm.control_main()[1]
    assert (RET_PC - site - len(body)) >= 0 and (RET_PC - site - len(body)) % 2 == 0
    body += wait * ((RET_PC - site - len(body)) // 2)
    body += e('ret r30') + wait * 2

    def marker(value):
        prefix = e(f'pop_exec r0l, {reenable}') if reenable is not None else b''
        return prefix + mov(23, value) + store(23, 8, 21) + e('wait 0') + stop

    body += marker(1)  # Fallthrough observed independently of any return hypothesis.
    for pc in LANDINGS:
        assert pc >= site + len(body) and (pc - site - len(body)) % 2 == 0
        body += stop * ((pc - site - len(body)) // 2)
        body += marker(pc)
    code = drm.build_main(body)
    surrogate = code[:RET_PC] + wait + code[RET_PC + 2:]
    return code, surrogate


def expected(marker):
    out = [0xcdcdcdcd] * 48 + [0xa5a50000 + i for i in range(16)]
    tab = [0xfeed0001] * N + [marker] * N + [VALUE] * N + [0] * N
    return out, tab


def simulate(code):
    return cov.simulate(code, N, N, 64, 0, TABLE)


def gate(code, surrogate):
    if os.environ.get('AGX_EXPERIMENTAL_RET'):
        raise RuntimeError('unset AGX_EXPERIMENTAL_RET: this gate requires default rejection')
    cov.gate(code, allow=('ret',))
    assert simulate(surrogate) == expected(1), 'wait surrogate differs from oracle'
    checked = [1]
    for target in LANDINGS:
        # Replace the six-byte ret/wait/wait island only; all surrounding bytes stay identical.
        jump = RS.e(f'jmp_exec_any pc+{target - RET_PC}', f'jmp_exec_any pc+{target - RET_PC}')
        assert len(jump) == 6
        path = code[:RET_PC] + jump + code[RET_PC + 6:]
        assert simulate(path) == expected(target), f'landing {target} differs from oracle'
        checked.append(target)
    try:
        simulate(code)
    except RuntimeError as exc:
        assert 'ret semantics unresolved' in str(exc), str(exc)
    else:
        raise AssertionError('unvalidated ret model unexpectedly accepted the variant')
    return {'surrogate_and_landing_markers_checked': checked, 'variant_rejected_as_unresolved': True,
            'limitation': 'simulator validates surrounding code, not the ret target or behavior'}


def snapshot():
    stat = dict(line.split() for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines())
    pressure = {}
    for name in ('memory.current', 'memory.max', 'memory.events', 'memory.pressure'):
        path = Path('/sys/fs/cgroup') / name
        if path.exists():
            pressure[name] = path.read_text()
    return {'shmem': int(stat['shmem']), 'budget_used': len(gpu_safety.used()),
            'memory_cgroup': pressure, 'meminfo': Path('/proc/meminfo').read_text(),
            'boot_id': gpu_safety.boot_id(), 'ac_online': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    global VALUE, LANDINGS
    ap.add_argument('--hardware', action='store_true')
    ap.add_argument('--halfword-map', action='store_true', help='test a buffer-relative halfword target as well')
    ap.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/ret-landing/R1-map.json'))
    a = ap.parse_args()
    if a.halfword_map:
        VALUE = (0x2000 + 1024) // 2
        LANDINGS = (1024, VALUE, RET_PC + VALUE, 2 * VALUE, RET_PC + 2 * VALUE)
    code, surrogate = build()
    checked = gate(code, surrogate)
    print(json.dumps(checked), flush=True)
    if not a.hardware:
        return
    if a.out.exists():
        raise SystemExit(f'refusing to overwrite {a.out}')
    gpu_safety.require_budget(1)
    rec = {'name': f'R1_ret_r30_{VALUE}_at_{RET_PC}', 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'code': code.hex(), 'surrogate_code': surrogate.hex(), 'gate': checked,
           'ret_pc': RET_PC, 'target_value': VALUE, 'landing_offsets': LANDINGS,
           'n': N, 'wg': N, 'regs': 64, 'table_in': TABLE, 'before': snapshot(),
           'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    runner = bench.Runner(a.out.parent / 'runner')
    log = Path('/save/kernel.log')
    start = log.stat().st_size

    def run(blob):
        out, table, ns, va = RS.run(runner, blob, N, N, TABLE, 64)
        return {'out': out, 'table_after': table, 'fw_ns': ns, 'table_va': va}

    def save():
        rec['after'] = snapshot()
        with log.open('rb') as f:
            f.seek(start)
            rec['kernel_log_delta'] = f.read().decode(errors='replace')
        a.out.write_text(json.dumps(rec, indent=1) + '\n')

    try:
        rec['control_before'] = run(surrogate)
        assert (rec['control_before']['out'], rec['control_before']['table_after']) == expected(1)
        rec['variant'] = run(code)
        save()  # Preserve the unknown result before any further dispatch.
        if rec['after']['budget_used'] != rec['before']['budget_used']:
            raise RuntimeError('fault budget changed; stopping without a post-control')
        if any(s in rec['kernel_log_delta'].lower() for s in ('fault', 'timeout', 'timed out')):
            raise RuntimeError('kernel log reports a fault/timeout; stopping without a post-control')
        rec['control_after'] = run(surrogate)
        assert (rec['control_after']['out'], rec['control_after']['table_after']) == expected(1)
    except Exception as exc:
        rec['failure'] = str(exc)
        # record_suite does not account for a subprocess-level timeout.
        if isinstance(exc, __import__('subprocess').TimeoutExpired) and len(gpu_safety.used()) == rec['before']['budget_used']:
            gpu_safety.record('ret landing host timeout')
        raise
    finally:
        save()
        print(json.dumps({'record': str(a.out), 'failure': rec.get('failure'),
                          'markers': sorted(set(rec.get('variant', {}).get('table_after', [])[32:64]))}), flush=True)


if __name__ == '__main__':
    main()
