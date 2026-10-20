#!/usr/bin/env python3
"""Probe sparse-mask shuffles and paired b32 lowering of 64-bit payloads.

Only recorded instruction forms, full 32-lane launches, straight-line programs.
Inputs and index-register poison are initialized before divergence. Every exact
program passes the independent raw-AGX oracle in agx_run before hardware use.
PTX comparisons exclude reads from inactive source lanes; no rendezvous claim.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys

import agx_loop
import collect_environment
import gpu_safety
import run_agx_timestamps as chains
import run_drm_compute as drm
import run_drm_shfl as shfl
import sim_gate
from run_drm_cpu_clock import load

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT.parent / 'AGX-Performance-Simulator'
GUARD = 0xcdcdcdcd
SENT = 0xdeadbeef
REGS = 80


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pack(words):
    return struct.pack(f'<{len(words)}I', *words)


def unpack(data):
    return list(struct.unpack(f'<{len(data)//4}I', data))


def source(mode, lane, b, c):
    """Independent scalar transcription of NVIDIA's shfl.sync pseudocode."""
    amount, clamp, mask = b & 31, c & 31, (c >> 8) & 31
    upper = (lane & mask) | (clamp & (~mask & 31))
    if mode == 'up':
        j = lane - amount
        pred = j >= upper
    elif mode == 'down':
        j = lane + amount
        pred = j <= upper
    elif mode == 'bfly':
        j = lane ^ amount
        pred = j <= upper
    elif mode == 'idx':
        j = (lane & mask) | (amount & (~mask & 31))
        pred = j <= upper
    else:
        raise ValueError(mode)
    return (j if pred else lane), int(pred)


def masks():
    # Include every prefix and singleton, missing quad neighbours, no active
    # lanes, all lanes, alternating quads and reproducible arbitrary masks.
    rng = random.Random(20261020)
    return ([0, 0xffffffff, 0x55555555, 0xaaaaaaaa, 0x11111111,
             0x88888888, 0x33333333, 0xcccccccc, 0x0f0f0f0f, 0xf0f0f0f0]
            + [(1 << n)-1 for n in range(1, 32)]
            + [1 << n for n in range(32)]
            + [rng.getrandbits(32) for _ in range(23)])


def inputs(groups, seed, fast_b=None):
    rng = random.Random(seed)
    n = groups*32
    lo = [rng.getrandbits(32) for _ in range(n)]
    hi = [rng.getrandbits(32) for _ in range(n)]
    b, active = [], []
    ms = masks()
    for g in range(groups):
        for lane in range(32):
            b.append(fast_b if fast_b is not None else
                     [rng.getrandbits(32), lane*5+g, g & 31, 0][g % 4])
            active.append((ms[g % len(ms)] >> lane) & 1)
    # Four read-only planes, three output planes, then an untouched suffix.
    return lo+hi+b+active+[GUARD]*(3*n+16)


def lines(case):
    base, _, _ = shfl.generic_lines(case['mode'], case['c'])
    split = base.index('icmpsel ueq, r16, r15, 0, r10, r14')
    if case['path'] == 'fast':
        op = dict(up='simd_shuffle_up', down='simd_shuffle_down',
                  bfly='simd_shuffle_xor', idx='simd_shuffle')[case['mode']]
        b = case['b'] & 31
        return base[:split]+[f'{op} r28, r8, {b}', f'{op} r29, r30, {b}']
    # Share the source-index arithmetic, shuffle the two independent words.
    high = [f'simd_shuffle r{31+k}, r30, r{19+k}l' for k in range(4)]
    high += ['icmpsel ueq, r29, r17, 2, r33, r34',
             'icmpsel ueq, r29, r17, 1, r32, r29',
             'icmpsel ueq, r29, r17, 0, r31, r29']
    return base+high


def build(case, n):
    e, mov = agx_loop.encode, chains.mov_imm
    ins = [load(8, 1, True)]
    for plane, reg in ((1, 30), (2, 9), (3, 35)):
        ins += [mov(6, plane*n), e('iadd r7, r1, r6'), load(reg, 7, True)]
    ins += [e('wait 0'), mov(28, SENT), mov(29, SENT), mov(15, SENT)]
    for k in range(4):
        ins.append(mov(19+k, k if case['path'] == 'seeded' else case.get('poison', 3)))
    ins += [e('if_icmp r0l, ugt, r35, 0, 1')]
    ins += [e(line) for line in lines(case)]
    ins += [e('pop_exec r0l, 1')]
    for plane, reg in ((4, 28), (5, 29), (6, 15)):
        ins += [mov(6, plane*n), e('iadd r7, r1, r6'), agx_loop.store(reg, 8, 7)]
    ins += [e('wait 0'), mov(2, 0x12345678)]
    code = drm.build_main(b''.join(ins))
    if code[-2:] != b'\x88\x00':
        raise ValueError('missing stop')
    return code


def expected(case, initial, raw=False):
    """Host PTX oracle; raw=True adds documented unmasked quad-index OR.

    Inputs are initialized in all lanes. For negative controls only, the raw
    AGX oracle predicts the poisoned source even when that source is inactive.
    """
    n = (len(initial)-16)//7
    result = initial.copy()
    defined = [False]*n
    counts = Counter()
    for i in range(n):
        group, lane = i & ~31, i & 31
        if not initial[3*n+i]:
            for plane in (4, 5, 6):
                result[plane*n+i] = SENT
            counts['inactive'] += 1
            continue
        j, pred = source(case['mode'], lane, initial[2*n+i], case['c'])
        defined[i] = bool(initial[3*n+group+j])
        counts['defined' if defined[i] else 'undefined_source'] += 1
        counts['predicate_true' if pred else 'predicate_false'] += 1
        if raw and case['path'] == 'poisoned':
            q = group+(j & ~3)
            live = sum(initial[3*n+q+k] for k in range(4))
            if live != 4:
                low = ((j & 3) if live else 0) | case['poison']
                j = (j & ~3) | low
        for plane in (0, 1):
            result[(4+plane)*n+i] = initial[plane*n+group+j]
        result[6*n+i] = pred
    return result, defined, dict(counts)


def assess(case, initial, observed):
    want, defined, counts = expected(case, initial)
    n = len(defined)
    bad, examples = Counter(), []
    if len(observed) != len(want):
        raise ValueError('wrong table length')
    bad['readonly_or_guard'] = sum(a != b for a, b in zip(observed[:4*n], initial[:4*n]))
    bad['readonly_or_guard'] += sum(a != b for a, b in zip(observed[7*n:], initial[7*n:]))
    for i in range(n):
        active = initial[3*n+i]
        for plane in (4, 5, 6):
            # Inactive destinations and arithmetic predicates are always checked.
            if plane != 6 and active and not defined[i]:
                continue
            if observed[plane*n+i] != want[plane*n+i]:
                key = 'inactive_write' if not active else 'predicate' if plane == 6 else 'defined_value'
                bad[key] += 1
                if len(examples) < 4:
                    examples.append({'lane': i, 'plane': plane, 'expected': want[plane*n+i],
                                     'observed': observed[plane*n+i]})
    return {'counts': counts, 'bad': dict(bad), 'examples': examples}


def configs():
    out = []
    # A known full-mask-capable instruction sequence brackets the sweep.
    for mode, c in shfl.configs():
        out.append(dict(name=f'seeded-{mode}-c{c:x}', path='seeded', mode=mode, c=c))
    for mode in shfl.MODES:
        for b in (0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 33, 63):
            out.append(dict(name=f'fast-{mode}-b{b}', path='fast', mode=mode,
                            c=shfl.default_c(mode), b=b))
        for poison in (0, 1, 2, 3):
            out.append(dict(name=f'poison-{mode}-{poison}', path='poisoned', mode=mode,
                            c=shfl.default_c(mode), poison=poison))
    return [dict(out[0], name='control-before')]+out+[dict(out[0], name='control-after')]


def simulate(code, n, table):
    # Import by path to avoid a dependency on a site-installed coverage package.
    import importlib.util
    spec = importlib.util.spec_from_file_location('agx_coverage', SIM/'scripts/coverage.py')
    cov = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SIM/'scripts'))
    spec.loader.exec_module(cov)
    return cov.simulate(code, n, 32, REGS, 0, table)


def run_hardware(exe, out, code, n, table):
    gpu_safety.require_budget()
    (out/'code.bin').write_bytes(code+bytes(16))
    (out/'input.bin').write_bytes(pack(table))
    argv = [str(exe), '/dev/dri/renderD128', str(out/'code.bin'), str(n),
            str(out/'output.bin'), '1', str(REGS), str(out/'input.bin')]
    env = {'PATH': os.environ['PATH'], 'AGX_TABLE_OUT': str(out/'table.bin')}
    try:
        run = subprocess.run(argv, capture_output=True, text=True, timeout=30, env=env)
    except subprocess.TimeoutExpired:
        gpu_safety.record('shfl-mask harness timeout')
        raise
    (out/'stdout.txt').write_text(run.stdout)
    (out/'stderr.txt').write_text(run.stderr)
    events = [json.loads(line) for line in run.stdout.splitlines() if line.startswith('{')]
    samples = [e for e in events if 'rep' in e]
    if run.returncode or len(samples) != 1 or samples[0]['wait'] or not all(samples[0]['fw_ts']):
        gpu_safety.record(f'shfl-mask harness failure {run.returncode}')
        raise RuntimeError(f'hardware failed: {run.stdout[-500:]} {run.stderr[-500:]}')
    params = next(e['params'] for e in events if 'params' in e)
    if (params['gen'], params['variant'], params['rev']) != (14, 'C', 17):
        raise RuntimeError(f'unexpected hardware: {params}')
    return unpack((out/'output.bin').read_bytes()), unpack((out/'table.bin').read_bytes()), events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('offline', 'hardware'))
    p.add_argument('--groups', type=int, default=len(masks()))
    p.add_argument('--seed', type=int, default=113)
    p.add_argument('--only', help='substring of case name (small first)')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.groups <= 512:
        p.error('groups must be 1..512')
    a.output.mkdir(parents=True, exist_ok=False)
    rec = dict(schema=1, mode=a.mode, groups=a.groups, seed=a.seed,
               utc=datetime.now(timezone.utc).isoformat(), complete=False, results=[],
               environment=collect_environment.collect(ROOT),
               argv=sys.argv, shmem_before=collect_environment.text_file('/sys/fs/cgroup/memory.stat'),
               power_ac=collect_environment.text_file('/sys/class/power_supply/macsmc-ac/online'),
               boot_id=gpu_safety.boot_id(), budget_before=len(gpu_safety.used()),
               simulator_commit=collect_environment.command_output(['git', 'rev-parse', 'HEAD'], SIM)['stdout'],
               simulator_binary_sha256=digest((SIM/'rust/target/release/agx_run').read_bytes()),
               assembler_sha256={name: digest((chains.APPLEGPU/name).read_bytes())
                                 for name in ('applegpu.py', 'assemble.py')},
               source_hashes={str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in
                              (Path(__file__).resolve(), ROOT/'scripts/run_drm_shfl.py', ROOT/'scripts/agx_loop.py',
                               ROOT/'scripts/run_drm_compute.py', ROOT/'scripts/run_drm_cpu_clock.py',
                               ROOT/'scripts/run_agx_timestamps.py', ROOT/'tests/drm_compute.c')})
    def save():
        with gzip.open(a.output/'record.json.gz', 'wt') as f:
            json.dump(rec, f, separators=(',', ':'))
    save()
    exe = a.output/'drm_compute'
    if a.mode == 'hardware':
        gpu_safety.require_budget()
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                        str(ROOT/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    for case in configs():
        if a.only and a.only not in case['name']:
            continue
        caseout = a.output/case['name']
        caseout.mkdir()
        table = inputs(a.groups, a.seed, case.get('b'))
        n = a.groups*32
        code = build(case, n)
        sim_out, sim_table = simulate(code, n, table)
        raw, _, _ = expected(case, table, raw=True)
        if sim_table != raw or not sim_gate.oracle_ok(sim_out, n, 0x12345678):
            raise RuntimeError(f'simulator oracle failed: {case["name"]}, '+str(assess(case, table, sim_table)))
        result = dict(case=case, code_hex=code.hex(), input_sha256=digest(pack(table)),
                      simulator_gate=True, simulator_assessment=assess(case, table, sim_table))
        if a.mode == 'hardware':
            output, observed, events = run_hardware(exe, caseout, code, n, table)
            result.update(events=events, table=observed, output=output)
        else:
            output, observed = sim_out, sim_table
        result.update(assessment=assess(case, table, observed),
                      output_guards_ok=sim_gate.oracle_ok(output, n, 0x12345678))
        rec['results'].append(result)
        save()
        bad = result['assessment']['bad']
        if (not result['output_guards_ok'] or bad.get('readonly_or_guard') or bad.get('inactive_write')
                or bad.get('predicate') or (case['path'] != 'poisoned' and bad.get('defined_value'))):
            raise RuntimeError(f'readback mismatch: {case["name"]}: {result["assessment"]}')
        print(case['name'], json.dumps(result['assessment']), flush=True)
    if not rec['results']:
        raise RuntimeError('empty selection')
    rec.update(complete=True, budget_after=len(gpu_safety.used()),
               shmem_after=collect_environment.text_file('/sys/fs/cgroup/memory.stat'))
    save()
    print(f'{a.mode}: {len(rec["results"])} programs complete')


if __name__ == '__main__':
    main()
