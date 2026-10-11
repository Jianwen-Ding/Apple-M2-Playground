#!/usr/bin/env python3
"""Hardware regression for novel-results/2026-10-11-in-shader-clock.

Runs scripts/run_drm_cpu_clock.py (decoded, Mesa-emitted instructions only) and asserts:
a normal re-read of the same line is stale; a coherent load after device_barrier_1 is fresh;
and the shader-measured time equals the firmware dispatch time minus 3-8 us.
Default (no --hardware): the offline verifier on the retained evidence.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    if '--hardware' not in sys.argv:
        return subprocess.run([sys.executable, '-B', str(REPO/'scripts/verify_in_shader_clock.py')]).returncode
    out = Path(tempfile.mkdtemp(prefix='clock-', dir='/scratch/apple-m2-playground/drm-compute'))/'r'
    only = "flush==0 and second_line==False and ((not coherent and between=='none') or (coherent and between=='device_barrier_1'))"
    r = subprocess.run([sys.executable, '-B', 'run_drm_cpu_clock.py', '--trips', '0,1000,10000', '--repeats', '3', '--only', only,
                        '--output', str(out)], cwd=REPO/'scripts', capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-400:]+r.stderr[-400:]
    R = json.loads((out/'record.json').read_text())['results']
    stale = [x for x in R if not x['coherent']]
    fresh = [x for x in R if x['coherent']]
    assert stale and all(x['timer_delta_ticks'] == 0 for x in stale), stale
    assert fresh and all(x['timer_delta_ticks'] > 0 for x in fresh), fresh
    d = [x['fw_ns_last']/1e3-x['timer_delta_ns']/1e3 for x in fresh]
    assert all(3 <= v <= 8 for v in d), d
    print('hardware: PASS', [(x['trips'], round(x['timer_delta_ns']/1e3, 2), round(x['fw_ns_last']/1e3, 2)) for x in fresh])
    return 0


if __name__ == '__main__':
    sys.exit(main())
