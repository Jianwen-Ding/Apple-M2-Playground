#!/usr/bin/env python3
"""Check simulator launch rejection and batch isolation; synthetic fixtures, no GPU."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition, detail='launch check failed'):
    if not condition:
        raise AssertionError(detail)


def check(run):
    env = {**os.environ, 'AGX_THREADS': '2'}
    with tempfile.TemporaryDirectory(prefix='agx-launch-check-') as directory:
        directory = Path(directory)
        code = directory / 'stop.bin'
        code.write_bytes(bytes.fromhex('8800'))
        base = [str(code), '--grid', '64', '--wg', '32', '--no-mem']

        def invoke(args, workers=2):
            return subprocess.run([str(run), *args], capture_output=True, text=True,
                env={**env, 'AGX_THREADS': str(workers)}, timeout=60)

        result = invoke(base)
        require(result.returncode == 0, result.stderr)
        reference = json.loads(result.stdout)
        require(reference['workgroups'] == 2 and reference['groups_per_wg'] == 1)
        for key in ['time_us', 'core_cycles', 'clock_mhz']:
            require(isinstance(reference[key], (float, int)) and math.isfinite(reference[key]), key)
        functional = base + ['--alloc', '0x10000=4']
        expected_functional = {**reference, 'paths': 'functional'}
        result = invoke(functional)
        require(result.returncode == 0 and json.loads(result.stdout) == expected_functional, result.stderr)

        cases = [
            (['--wg', '0'], 'workgroup'), (['--wg', '65536,65536'], 'workgroup'),
            (['--wg', '1025'], 'workgroup'), (['--grid', '0'], 'grid'),
            (['--grid', '4294967295,4294967295,4294967295'], 'workgroup count'),
            (['--cores', '0'], 'core'), (['--regs', '2147483648'], 'occupancy'),
            (['--tg-bytes', '65537'], 'threadgroup memory'),
            (['--uniform', 'u256=1'], 'uniform'), (['--uniform', 'u18446744073709551615=1'], 'uniform'),
            (['--clock', '0'], 'clock_mhz'), (['--clock', '-1'], 'clock_mhz'),
            (['--clock', 'NaN'], 'clock_mhz'), (['--clock', 'inf'], 'clock_mhz'),
            (['--launch-us', '-1'], 'launch_ns'), (['--launch-us', 'NaN'], 'launch_ns'),
            (['--grid', '1,1,1,2'], 'dimensions'), (['--grid', '1,,3'], 'dimension'),
            (['--wg', 'x'], 'dimension'), (['--regs', '-1'], '--regs'),
            (['--max-waves', 'x'], '--max-waves'), (['--clock'], 'requires a value'),
            (['--uniform', '1'], 'IDX=VALUE'), (['--uniform', 'r1=1'], 'uniform index'),
            (['--uniform', '1=0xg'], 'invalid'), (['--alloc', '12'], 'VA=FILE'),
            (['--alloc', '0xg=4'], 'u64'), (['--alloc', '0x1000=bad'], 'u32'),
            (['--map', '12'], 'VA=FILE'), (['--unknown'], 'unknown argument'),
        ]
        invalid = [(base + args, needle) for args, needle in cases]
        missing = str(directory / 'missing')
        invalid += [([], 'empty job'), ([missing, '--wg', '0'], 'workgroup'),
            (base + ['--wg', '0', '--preamble', missing], 'workgroup'),
            (base + ['--wg', '0', '--map', '0x1000=' + missing], 'workgroup')]
        for args, needle in invalid:
            # Empty jobs have a meaningful batch error; the single form has no path/usage.
            if not args:
                continue
            result = invoke(args)
            require(result.returncode == 1 and needle in result.stderr, (args, result.returncode, result.stderr))
            require('panicked' not in result.stderr)

        lines = [json.dumps(base)]
        expected = [reference]
        for args, needle in invalid:
            lines.append(json.dumps(args))
            expected.append(needle)
        for text in ['{', '{}', '[1]']:
            lines.append(text)
            expected.append('batch line')
        lines.extend(['', json.dumps(functional), json.dumps(base)])
        expected.extend([expected_functional, reference])
        batch = directory / 'mixed.jsonl'
        batch.write_text('\n'.join(lines) + '\n')
        for workers in [1, 4]:
            result = invoke(['--batch', str(batch)], workers)
            require(result.returncode == 1, (result.returncode, result.stderr))
            rows = [json.loads(s) for s in result.stdout.splitlines()]
            require(len(rows) == len(expected), (len(rows), len(expected)))
            for row, want in zip(rows, expected):
                if isinstance(want, str):
                    require(set(row) == {'error'} and want in row['error'], (row, want))
                else:
                    require(row == want, (row, want))
            require('panicked' not in result.stderr)
        batch.write_text(' \n\n')
        require(invoke(['--batch', str(batch)]).returncode == 1)
        require(invoke(['--batch']).returncode == 2)
        require(invoke(['--batch', missing]).returncode == 1)
    return dict(invalid_jobs=len(invalid), malformed_json_lines=3, valid_batch_controls=3,
        batch_workers=[1, 4], checks='pass', hardware_run=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, default=Path(os.environ.get('SIMREPO', ROOT.parent / 'AGX-Performance-Simulator')) / 'rust/target/release/agx_dispatch')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    if not args.run.is_file():
        ap.error(f'{args.run} not found; build the simulator or set --run')
    result = check(args.run.resolve())
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{result["invalid_jobs"]} invalid jobs and 3 malformed JSON lines isolated; valid controls unchanged (1/4 workers); no GPU')


if __name__ == '__main__':
    main()
