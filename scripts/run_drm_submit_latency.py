#!/usr/bin/env python3
"""Submission latency versus idle gap (simulator task safe-04 step 3), direct DRM, one queue.

The pinned control kernel (simulator-gated by sim_gate) is submitted `repeats` times per gap, with a host sleep of
`gap` us between submissions (tests/drm_compute.c AGX_REP_SLEEP_US). Per submission, in the GPU timebase (ns):
  submit_to_start = firmware start - GET_TIME read just before SUBMIT   (driver + firmware + power-up)
  end_to_wake     = GET_TIME read just after the syncobj wait - firmware end   (fence signal + host wake-up)
  fw              = firmware end - start
"""
import argparse, datetime, json, os, shlex, statistics, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gaps-us', default='0,100,1000,3000,10000,30000,100000')
    p.add_argument('--repeats', type=int, default=16)
    p.add_argument('--count', type=int, default=32)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    gaps = [int(g) for g in a.gaps_us.split(',')]
    if not (all(0 <= g <= 1_000_000 for g in gaps) and 1 <= a.repeats <= 64):
        sys.exit('refusing: bounded gaps / repeats required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/submit-latency')/stamp
    out.mkdir(parents=True, exist_ok=False)
    code = drm.build_main(bytes.fromhex('620978563412'))
    state = {'utc': stamp, 'count': a.count, 'repeats': a.repeats, 'code_hex': code.hex(),
             'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(),
             'simulator': sim_gate.require(code, a.count, 0x12345678), 'gaps': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    save()
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    (out/'k.bin').write_bytes(code+bytes(16))
    for g in gaps:
        gpu_safety.require_budget(1)
        rb = out/f'gap{g}.readback'
        try:
            res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(a.count), str(rb), str(a.repeats), '16'],
                                 capture_output=True, timeout=120, env=dict(os.environ, AGX_REP_SLEEP_US=str(g)))
        except subprocess.TimeoutExpired:
            gpu_safety.record(f'run_drm_submit_latency gap {g}: harness timeout'); sys.exit('timeout: stopping')
        lines = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{')]
        reps = [l for l in lines if 'rep' in l]
        words = len(rb.read_bytes())//4 if rb.exists() else 0
        ok = res.returncode == 0 and words and sim_gate.oracle_ok(list(struct.unpack(f'<{words}I', rb.read_bytes())), a.count, 0x12345678)
        for q in reps:
            q['submit_to_start'] = q['fw_ts'][0]-q['drm_time'][0]
            q['end_to_wake'] = q['drm_time'][1]-q['fw_ts'][1]
            q['fw'] = q['fw_ts'][1]-q['fw_ts'][0]
        state['gaps'].append({'gap_us': g, 'returncode': res.returncode, 'oracle_ok': bool(ok), 'reps': reps}); save()
        med = lambda k: statistics.median(q[k] for q in reps[1:]) if len(reps) > 1 else None
        print(json.dumps({'gap_us': g, 'ok': bool(ok), 'submit_to_start_med': med('submit_to_start'), 'end_to_wake_med': med('end_to_wake'),
                          'fw_med': med('fw'), 'host_med': med('host_ns'), 'first': reps[0]['submit_to_start'] if reps else None}))
        if not ok:
            sys.exit('stopping on failure')


if __name__ == '__main__':
    sys.exit(main())
