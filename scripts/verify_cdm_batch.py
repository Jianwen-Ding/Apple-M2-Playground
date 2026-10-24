#!/usr/bin/env python3
"""Compile an authored PTX dependency probe and verify ordered CDM batching."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zoc', default=os.environ.get('ZLUDA_AGX_ZOC', 'zoc'))
    parser.add_argument('--runner', default=os.environ.get(
        'AGX_CDM_BATCH', str(ROOT.parent / 'ZLUDA/target/release/agx_cdm_batch')))
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--threads', type=int, default=65536)
    parser.add_argument('--dispatches', type=int, default=64)
    args = parser.parse_args()
    if min(args.repetitions, args.threads, args.dispatches) < 1:
        parser.error('repetitions, threads and dispatches must be positive')
    reports = []
    with tempfile.TemporaryDirectory(prefix='agx-cdm-dependency-') as directory:
        work = Path(directory)
        subprocess.run([args.zoc, '--target', 'agx', '--arch', 'agx-g14c',
                        '--output-dir', str(work), str(ROOT / 'tests/cdm_batch.ptx')],
                       check=True, stdout=subprocess.PIPE)
        for _ in range(args.repetitions):
            run = subprocess.run([args.runner, str(work / 'cdm_batch.o'),
                                  str(work / 'cdm_batch.asm'), '--n', str(args.threads),
                                  '--dispatches', str(args.dispatches)],
                                 check=True, capture_output=True, text=True)
            report = json.loads(run.stdout)
            if any(report[field] != 0 for field in ['wrong_separate', 'wrong_batched', 'wrong_chain']):
                raise RuntimeError(f'dependent dispatches produced wrong output: {report}')
            if report['cdm_barriers'] != args.dispatches:
                raise RuntimeError(f'missing inter-dispatch CDM barrier: {report}')
            reports.append(report)
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
