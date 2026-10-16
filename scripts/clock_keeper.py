#!/usr/bin/env python3
"""Clock keeper: hold the GPU at its top clock state while another process measures timing.

Runs back-to-back SUBMITs of 64 commands of a 64-lane delay kernel (2 SIMD groups, at most 2 of 38 cores; ~8 ms per
SUBMIT at the top clock) until the stop file exists or --seconds pass. The kernel passes the simulator's agx_run
oracle (sim_gate) before any GPU use. Without it, sub-ms dispatches separated by host waits run in a mix of clock
states (references jump by > 30 ns per loop trip; results/2026-10-16-fixed18-waits); with it they are stable to
< 1 ns per trip. Usage: clock_keeper.py --seconds 120 &  ... measure ...  ; touch <stop file>
"""
import argparse, os, shlex, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402
import run_drm_sr_scan as scan  # noqa: E402

DIR = Path('/scratch/apple-m2-playground/drm-compute/keeper')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds', type=float, default=120)
    p.add_argument('--stop-file', type=Path, default=DIR/'stop')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if not 1 <= a.seconds <= 3600:
        sys.exit('refusing: 1..3600 s')
    DIR.mkdir(parents=True, exist_ok=True)
    a.stop_file.unlink(missing_ok=True)
    k = drm.build_main(scan.delay_loop(4000)+bytes.fromhex('620978563412'))
    sim_gate.require(k, 64, 0x12345678)
    (DIR/'k.bin').write_bytes(k+bytes(16))
    exe = DIR/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    end, n, bad = time.monotonic()+a.seconds, 0, 0
    while time.monotonic() < end and not a.stop_file.exists():
        gpu_safety.require_budget(1)
        try:
            res = subprocess.run([str(exe), a.device, str(DIR/'k.bin'), '64', str(DIR/'rb'), '32', '16'], capture_output=True, timeout=30,
                                 env=dict(os.environ, AGX_CMDS='64', AGX_CMD_BARRIER='none'))
            ok = res.returncode == 0 and b'"completed":true' in res.stdout
        except subprocess.TimeoutExpired:
            gpu_safety.record('clock_keeper: harness timeout'); ok = False
        n += 1; bad += not ok
        if not ok:
            print(f'clock_keeper: submission process {n} failed; stopping', file=sys.stderr); break
    print(f'clock_keeper: {n} processes, {bad} failed', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
