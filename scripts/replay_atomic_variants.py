#!/usr/bin/env python3
"""Replay retained atomic-variant programs in the Rust simulator, without a GPU.

Deterministic records must match every output/table word. Contended float adds
may serialize in a different order; validate their own return chain with the
independent rational model from verify_atomic_variants instead.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from verify_atomic_variants import fadd

ROOT = Path(__file__).resolve().parents[1]
SIMREPO = Path(os.environ.get('SIMREPO', ROOT.parent / 'AGX-Performance-Simulator'))
DATA_VA = 0x1100000000


def pack(words):
    return struct.pack(f'<{len(words)}I', *words)


def unpack(path):
    data = path.read_bytes()
    return list(struct.unpack(f'<{len(data) // 4}I', data))


def simulate(record, run, timeout):
    n = record['n']
    rounded = (n + 31) // 32 * 32
    words = 8 + rounded + 8 + 16
    out_va = DATA_VA + 0x8000
    table_va = DATA_VA + max(1 << 20, (0x8000 + words * 4 + 16383) // 16384 * 16384)
    with tempfile.TemporaryDirectory(prefix='agx-atomic-replay-') as tmp:
        tmp = Path(tmp)
        (tmp / 'code.bin').write_bytes(bytes.fromhex(record['code']))
        (tmp / 'out.bin').write_bytes(pack([0xcdcdcdcd] * (words - 16) + [0xa5a50000 + i for i in range(16)]))
        (tmp / 'table.bin').write_bytes(pack(record['table_in']))
        args = [str(run), str(tmp / 'code.bin'), '--grid', f'{rounded},1,1',
                '--wg', f'{record["wg"]},1,1', '--regs', str(record['regs']),
                '--shared', str(record.get('shared', 2048 if record['name'].startswith('T') else 0))]
        for reg, value in [(4, 0), (5, n), (6, out_va & 0xffffffff), (7, out_va >> 32),
                           (8, table_va & 0xffffffff), (9, table_va >> 32)]:
            args += ['--uniform', f'{reg}={value}']
        args += ['--map', f'{out_va:#x}={tmp / "out.bin"}', '--map', f'{table_va:#x}={tmp / "table.bin"}',
                 '--dump', f'{out_va:#x}={4 * words}:{tmp / "out-after.bin"}',
                 '--dump', f'{table_va:#x}={4 * len(record["table_in"])}:{tmp / "table-after.bin"}',
                 '--alloc-regs', str(max(8, (record['regs'] + 7) // 8 * 8)), '--vm-slot', '0', '--pipeline', '4096']
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr).strip()[-1000:])
        return unpack(tmp / 'out-after.bin'), unpack(tmp / 'table-after.bin')


def mismatch(label, got, want):
    if len(got) != len(want):
        raise AssertionError(f'{label}: {len(got)} words, expected {len(want)}')
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            raise AssertionError(f'{label}[{i}]: {g:#010x}, expected {w:#010x}')


def check(record, out, table):
    if record['deterministic']:
        mismatch('output', out, record['out'])
        mismatch('table', table, record['table_after'])
        return
    if record['name'] not in ('H_fadd_contend_ones', 'H_fadd_contend_mixed'):
        raise AssertionError('no order-independent oracle for this nondeterministic case')
    n = record['n']
    mismatch('output guards', out[:8] + out[8 + n:], record['out'][:8] + record['out'][8 + n:])
    mismatch('untouched table', table[1:], record['table_in'][1:])
    # Each return must be the predecessor of the next lane's return, consuming
    # every lane exactly once. This permits any valid serialization order.
    pool = {}
    for i, value in enumerate(out[8:8 + n]):
        pool.setdefault(value, []).append(i)
    value = record['table_in'][0]
    for _ in range(n):
        if not pool.get(value):
            raise AssertionError('contended returns do not form a complete atomic chain')
        i = pool[value].pop()
        value = fadd(value, record['table_in'][2048 + 2 * i], True)
        if value is None:
            value = 0x7fc00000
    if table[0] != value:
        raise AssertionError('contended final value differs from the return chain')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=SIMREPO / 'rust/target/release/agx_run')
    parser.add_argument('--records', type=Path, default=ROOT / 'results/2026-10-17-atomic-variants/records.json.gz')
    parser.add_argument('--only', help='regex on record names')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if not args.run.is_file():
        parser.error(f'{args.run} not found; build the simulator with make rust or set --run')
    with gzip.open(args.records, 'rt') as f:
        records = json.load(f)['records']
    selected = [r for r in records if not args.only or re.search(args.only, r['name'])]
    if not selected:
        parser.error('no records selected')
    failed = 0
    for record in selected:
        try:
            if 'fault' in record:
                raise AssertionError('record contains a GPU fault')
            check(record, *simulate(record, args.run.resolve(), args.timeout))
            print(f'ok   {record["name"]}', flush=True)
        except (AssertionError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            failed += 1
            print(f'FAIL {record["name"]}: {exc}', flush=True)
    print(f'{len(selected)} atomic records replayed; {failed} failures')
    return int(failed != 0)


if __name__ == '__main__':
    raise SystemExit(main())
