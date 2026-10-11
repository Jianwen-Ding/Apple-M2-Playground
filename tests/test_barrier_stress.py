#!/usr/bin/env python3
"""Regression test for novel-results/2026-10-11-barrier-0x68-vs-0x78.

Default: offline (bodies build, decode, and pass the emulator gate).
--hardware (CONFIRM_GPU_FAULTS=1): 256-lane workgroups, device memory, Mesa sequence
(wait, memory_barrier, barrier). Asserts 0x68 = 0 stale reads, `wait` = stale reads everywhere,
and 0x78 = stale reads only in SIMD groups 3 and 7 (whose partner is in the other block of 4).
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    run = lambda *a: subprocess.run([sys.executable, '-B', str(REPO/'scripts/run_drm_barrier_stress.py'), *a], capture_output=True, text=True, timeout=900)
    r = run('--dry-run', '--sizes', '64,128,256,512,1024')
    assert r.returncode == 0, r.stdout+r.stderr
    print('offline: barrier-stress bodies build, decode and pass the emulator gate')
    if '--hardware' not in sys.argv: return 0
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1': sys.exit('--hardware needs CONFIRM_GPU_FAULTS=1')
    out = Path(tempfile.mkdtemp(prefix='bstress-', dir='/scratch/apple-m2-playground/drm-compute'))/'r'
    r = run('--sizes', '256', '--names', r'dev-n256-(68-wait\+mb|78-wait\+mb|wait-none)', '--trips', '1000', '--output', str(out))
    assert r.returncode == 0, r.stdout[-500:]
    R = {x['name']: x for x in json.loads((out/'record.json').read_text())['results']}
    assert R['dev-n256-68-wait+mb']['mismatches'] == 0, R
    assert all(c > 0 for c in R['dev-n256-wait-none']['err_lanes_by_group']), R
    g = R['dev-n256-78-wait+mb']['err_lanes_by_group']
    assert [c > 0 for c in g] == [False, False, False, True, False, False, False, True], g
    print('hardware: PASS', {k: v['err_lanes_by_group'] for k, v in R.items()})
    return 0


if __name__ == '__main__':
    sys.exit(main())
