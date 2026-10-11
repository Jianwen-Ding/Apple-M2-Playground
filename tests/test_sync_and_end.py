#!/usr/bin/env python3
"""Regression test for novel-results/2026-10-11-sync-and-end-opcodes.

Default: offline (every suite builds, decodes and passes the emulator gates).
--hardware (CONFIRM_GPU_FAULTS=1): runs a small subset and asserts that
  * 0x78 synchronizes two SIMD groups like threadgroup_barrier (device and threadgroup memory),
    and 0x18 does not
  * threadgroup memory works on the direct DRM path
  * 0x18 adds the same fixed cost with or without a pending device load, while wait 0 does not
  * 0x01 and 0x98 end all 32 lanes by themselves; all 16 pending stores before 0x01 land
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
SENT = 0xcdcdcdcd


def probe(suite, names='.*', *extra, out=None):
    cmd = [sys.executable, '-B', str(REPO/'scripts/run_drm_sync_probe.py'), '--suite', suite, '--names', names, *extra]
    if out: cmd += ['--output', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode: raise AssertionError(f'{suite} failed: {r.stdout[-400:]} {r.stderr[-300:]}')
    return json.loads((out/'record.json').read_text())['results'] if out else None


def main():
    for s in ('barrier', 'memwait', 'scope', 'tgcheck', 'tgwait', 'endcost', 'endpend', 'endfollow'):
        r = subprocess.run([sys.executable, '-B', str(REPO/'scripts/run_drm_sync_probe.py'), '--suite', s, '--dry-run'],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, (s, r.stdout, r.stderr)
    print('offline: all sync-probe suites build, decode and pass the emulator gates')
    if '--hardware' not in sys.argv:
        return 0
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1':
        sys.exit('--hardware needs CONFIRM_GPU_FAULTS=1')
    import analyze_sync_probe as an
    tmp = Path(tempfile.mkdtemp(prefix='sync-', dir='/scratch/apple-m2-playground/drm-compute'))
    B = {r['name']: r for r in probe('barrier', r'barrier-(tg-)?g2-(wait|tg_barrier|18|78)', out=tmp/'b')}
    g0 = lambda r: set(r['table'][128:160])
    for pre in ('barrier-g2-', 'barrier-tg-g2-'):
        assert g0(B[pre+'wait']) == {SENT} and g0(B[pre+'tg_barrier']) == {2}, pre
        assert g0(B[pre+'78']) == {2} and g0(B[pre+'18']) == {SENT}, pre
    T = probe('tgcheck', 'tgcheck-g2', out=tmp/'t')[0]
    assert T['table'][:64] == [0x7e000000+63-i for i in range(64)]
    M = an.floor(probe('memwait', r'memwait-(none|load)-(ref|wait|18)', '--trips', '50000', '--repeats', '4', out=tmp/'m'), 50000)
    x = lambda k: M[k]['extra_ns_per_iter']
    assert abs(x('memwait-load-18')-x('memwait-none-18')) < 0.5, M
    assert x('memwait-load-wait') > x('memwait-none-wait')+10, M
    F = {r['name']: r for r in probe('endfollow', 'endfollow-(wait|01|98)', out=tmp/'f')}
    after = lambda r: ''.join('1' if v == 0xafafafaf else '0' for v in r['table'][:32])
    assert after(F['endfollow-wait']) == '0'*16+'1'*16 and after(F['endfollow-01']) == after(F['endfollow-98']) == '0'*32
    E = probe('endpend', 'endpend-01', out=tmp/'e')[0]['table']
    assert all(E[k*32+i] == (0xe0000000 | k << 16)+i for k in range(16) for i in range(32))
    print('hardware: PASS', {k: x(k) for k in M}, 'records in', tmp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
