#!/usr/bin/env python3
"""Regression test for the undecoded-opcode descriptions (novel-results/2026-10-11-opcode-descriptions).

Default: offline only (every probe body builds, decodes and passes the emulator gates).
--hardware: also runs a small representative subset on the direct DRM path
(needs CONFIRM_GPU_FAULTS=1; never runs the faulting opcodes) and asserts:
  * 0x03 is a 6-byte no-op (swallows exactly one marker in both layouts, no register change)
  * 0x18 is a 2-byte no-op; with bit 7 set (dt1) it ends execution
  * 0x01 ends the whole SIMD group even when half or none of its lanes are active,
    unlike stop, which ends only active lanes
  * a 0x03 loop takes as long as a 6-byte mov_imm loop; a 0x18 loop clearly longer (3.9-5.0x in six runs)
"""
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO/'scripts'
sys.path.insert(0, str(SCRIPTS))


def runner(*args, out=None):
    cmd = [sys.executable, '-B', str(SCRIPTS/'run_drm_opcode_describe.py'), *args]+(['--output', str(out)] if out else [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise AssertionError(f'runner failed: {r.stdout[-400:]} {r.stderr[-400:]}')
    return r.stdout


def main():
    hardware = '--hardware' in sys.argv
    out = json.loads(runner('--dry-run').splitlines()[-1])
    assert out['jobs'] > 800, out
    json.loads(runner('--suite', 'timing', '--dry-run').splitlines()[-1])
    print('offline: all probe bodies build, decode and pass the emulator gates')
    if not hardware:
        return 0
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1':
        sys.exit('--hardware needs CONFIRM_GPU_FAULTS=1')
    import analyze_opcode_describe as an
    tmp = Path(tempfile.mkdtemp(prefix='opdesc-', dir='/scratch/apple-m2-playground/drm-compute'))
    runner('--names', r'ref-wait-[AB]|op-(03|18|01)-(base|dt1)-[AB]|gran-(wait|stop|01)-(half|none|none-jump)', out=tmp/'shape')
    runner('--suite', 'timing', '--names', 'time-(mov_imm|03|18)', out=tmp/'timing')
    sys.argv = ['x', str(tmp/'shape/record.json')]
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        an.main()
    d = json.loads(buf.getvalue())
    L = {(r['op'], r['enc']): r for r in d['length_suite']}
    G = d['granularity']
    assert d['ref-A-ok'] and d['ref-B-ok'], 'reference body does not match its oracle'
    for en in ('base', 'dt1'):
        r = L[('0x03', en)]
        assert r['class'] == 'continues' and r['length'] == 6 and r['exact'] == [True, True], r
    assert L[('0x18', 'base')]['length'] == 2 and L[('0x18', 'dt1')]['class'] == 'ends'
    assert L[('0x01', 'base')]['class'] == 'ends' and L[('0x01', 'base')]['before_ok'] == [True, True]
    assert G['gran-stop-half']['after'] == '0'*16+'1'*16 and G['gran-stop-none']['after'] == '1'*32
    assert G['gran-01-half']['after'] == '0'*32 and G['gran-01-none']['after'] == '0'*32
    assert G['gran-01-none-jump']['after'] == '1'*32 and G['gran-wait-half']['after'] == '1'*32
    T = {r['name']: r for r in json.loads((tmp/'timing/record.json').read_text())['results']}
    ns = {k[5:]: statistics.median(v['fw_ns']) for k, v in T.items()}   # raw loop times; only same-run ratios are stable
    assert abs(ns['03']/ns['mov_imm']-1) < 0.02, ns
    assert ns['18']/ns['mov_imm'] > 3, ns   # 3.9-5.0x in six runs; variable, so only 'clearly slower' is asserted
    print('hardware: PASS', {k: round(v, 3) for k, v in ns.items()}, 'records in', tmp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
