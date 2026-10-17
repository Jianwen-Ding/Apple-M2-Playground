#!/usr/bin/env python3
"""Offline functional CLI geometry checks. Synthetic inputs, not hardware evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='agx-functional-geometry-') as temporary:
        directory = Path(temporary)
        code = directory / 'stop.bin'
        code.write_bytes(bytes.fromhex('8800'))
        source = directory / 'memory.bin'
        source.write_bytes(bytes(range(64)))
        dump = directory / 'dump.bin'

        def invoke(grid, wg='1,1,1'):
            result = subprocess.run([str(args.run.resolve()), str(code), '--grid', grid, '--wg', wg,
                '--map', f'0x10000={source}', '--dump', f'0x10000=64:{dump}'],
                capture_output=True, text=True, timeout=3)
            return result, json.loads(result.stdout)

        for axis in range(3):
            grid = ['4294967295'] * 3
            grid[axis] = '0'
            result, report = invoke(','.join(grid))
            require(result.returncode == 0 and report == dict(instructions=0, groups=0, preamble_uniforms={}), f'empty axis {axis}: {result.stdout} {result.stderr}')
            require(dump.read_bytes() == source.read_bytes(), 'empty dispatch changed memory')
        for grid in ['65537,65536,65536', '4294967295,4294967295,4294967295']:
            result, report = invoke(grid)
            require(result.returncode == 1 and '48-bit' in report.get('error', ''), f'capacity not checked: {report}')
        for grid, wg, expected in [('3,3,3', '2,2,2', 8), ('65,1,1', '64,1,1', 4), ('33,1,1', '32,1,1', 2)]:
            result, report = invoke(grid, wg)
            require(result.returncode == 0 and report == dict(instructions=expected, groups=expected, preamble_uniforms={}), f'partial group counts changed: {report}')
            require(dump.read_bytes() == source.read_bytes(), 'stop shader changed memory')
    print('functional geometry: 3 empty axes, 2 capacity errors, 3 partial-grid controls pass; memory unchanged')


if __name__ == '__main__':
    main()
