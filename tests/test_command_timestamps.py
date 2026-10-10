#!/usr/bin/env python3
"""Hardware regression for Honeykrisp command-timestamp placement on G14C.

Runs two native-AGX dispatches (4-byte fadd32 chain of 0 and 65536 steps,
exact readback oracle each), four timestamps per dispatch, and requires:

  * t1-t0 (top-of-pipe -> compute stamp recorded BEFORE vkCmdDispatch)
    grows by at least 250 us between the two lengths;
  * t2-t1 (the conventional before/after pair) stays below 60 us for both;
  * every timestamp is a truncated 24 MHz tick and t0 < t1 < t2 < t3.

Needs the GPU (bounded: 10 dispatches, ~10 ms of shader time). Execute:

    python3 -B tests/test_command_timestamps.py [--output DIR]
"""
import argparse
import datetime
import json
from pathlib import Path
import statistics as st
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--runtime', default='/scratch/apple-m2-playground/vulkan-runtime/usr/lib64')
    a = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = a.output or Path('/scratch/apple-m2-playground/timestamp-runs')/f'test-{stamp}'
    r = subprocess.run([sys.executable, '-B', str(REPO/'scripts/run_agx_timestamps.py'), '--kind', 'fadd4',
                        '--lengths', '0,65536', '--repeats', '4', '--runtime', a.runtime, '--output', str(out)],
                       capture_output=True, text=True, timeout=180)
    record = json.loads((out/'record.json').read_text())
    failures = []
    if r.returncode or not record['passed']:
        failures.append(f"runner failed: {record.get('error')}")
    v = {x['n']: x for x in record['variants']}
    if not failures:
        d01 = {n: st.median(s['ts'][1]-s['ts'][0] for s in v[n]['samples']) for n in (0, 65536)}
        d12 = {n: st.median(s['ts'][2]-s['ts'][1] for s in v[n]['samples']) for n in (0, 65536)}
        stamps = [t for x in record['variants'] for s in x['samples'] for t in s['ts']]
        if d01[65536]-d01[0] < 250000: failures.append(f'top->compute-before did not track work: {d01}')
        if max(d12.values()) >= 60000: failures.append(f'conventional pair not flat: {d12}')
        if not all((t*3+124)//125*125//3 == t for t in stamps): failures.append('timestamp off 24 MHz grid')
        if not all(s['ts'][0] < s['ts'][1] < s['ts'][2] < s['ts'][3] for x in record['variants'] for s in x['samples']):
            failures.append('timestamps out of order')
        print(json.dumps({'t1_t0_median_ns': d01, 't2_t1_median_ns': d12}))
    print(json.dumps({'passed': not failures, 'failures': failures, 'output': str(out)}))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
