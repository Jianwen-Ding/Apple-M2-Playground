#!/usr/bin/env python3
"""Queue priority under load (simulator task safe-04 step 1), direct DRM, two processes.

Process A (priority 0, LOW) fills the GPU: a large grid of the emulator-gated delay kernel, `a_repeats` submissions.
Process B submits the pinned control kernel every `b_gap_us` with priority `b_prio` (1 = MEDIUM, or 0 as the
control). For every B submission the firmware timestamps tell whether A was running at that moment, how long B
waited (submit -> start) and how long it ran. Both kernels pass sim_gate (agx_run oracle) before any GPU use; the
delay kernel's code does not depend on the lane count, so it is simulated at 4,096 lanes.
"""
import argparse, datetime, json, os, shlex, statistics, struct, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402
import run_drm_sr_scan as scan  # noqa: E402

ORACLE = 0x12345678


def parse(stdout):
    return [json.loads(l) for l in stdout.splitlines() if l.startswith('{')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a-count', type=int, default=1 << 20)
    p.add_argument('--a-delay', type=int, default=4000)
    p.add_argument('--a-repeats', type=int, default=24)
    p.add_argument('--a-local', type=int, default=32, help='workgroup size of A (128 fills all 96 SIMD-group slots per core)')
    p.add_argument('--b-prios', default='1,0')
    p.add_argument('--b-repeats', type=int, default=48)
    p.add_argument('--b-gap-us', type=int, default=1500)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if a.a_local not in (32, 64, 128, 256) or a.a_count % a.a_local:
        sys.exit('refusing: A workgroup must be 32-256 lanes and divide the count')
    if not (32 <= a.a_count <= 1 << 22 and 1 <= a.a_delay <= 20000 and 1 <= a.a_repeats <= 64 and 1 <= a.b_repeats <= 64):
        sys.exit('refusing: bounded sizes required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/priority')/stamp
    out.mkdir(parents=True, exist_ok=False)
    ka = drm.build_main(scan.delay_loop(a.a_delay)+bytes.fromhex('620978563412'))
    kb = drm.build_main(bytes.fromhex('620978563412'))
    state = {'utc': stamp, 'args': {k: v for k, v in vars(a).items() if k not in ('output',)} | {'output': str(out)},
             'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(),
             'kernels': {'a': {'code_hex': ka.hex(), 'simulator': sim_gate.require(ka, 4096, ORACLE, wg=a.a_local)},
                         'b': {'code_hex': kb.hex(), 'simulator': sim_gate.require(kb, 32, ORACLE)}}, 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    save()
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    (out/'a.bin').write_bytes(ka+bytes(16)); (out/'b.bin').write_bytes(kb+bytes(16))
    for bp in [int(x) for x in a.b_prios.split(',')]:
        gpu_safety.require_budget(2)
        pa = subprocess.Popen([str(exe), a.device, str(out/'a.bin'), str(a.a_count), str(out/f'a-{bp}.readback'), str(a.a_repeats), '16'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, AGX_PRIORITY='0', AGX_LOCAL_X=str(a.a_local)))
        time.sleep(0.05)
        try:
            rb = subprocess.run([str(exe), a.device, str(out/'b.bin'), '32', str(out/f'b-{bp}.readback'), str(a.b_repeats), '16'],
                                capture_output=True, timeout=120, env=dict(os.environ, AGX_PRIORITY=str(bp), AGX_REP_SLEEP_US=str(a.b_gap_us)))
            sa, ea = pa.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            pa.kill(); gpu_safety.record(f'run_drm_priority b_prio {bp}: harness timeout'); save(); sys.exit('timeout: stopping')
        A, B = parse(sa.decode()), parse(rb.stdout.decode())
        ok = {}
        for name, res_rc, cnt in (('a', pa.returncode, a.a_count), ('b', rb.returncode, 32)):
            f = out/f'{name}-{bp}.readback'
            w = len(f.read_bytes())//4 if f.exists() else 0
            ok[name] = res_rc == 0 and w > 0 and sim_gate.oracle_ok(list(struct.unpack(f'<{w}I', f.read_bytes())), cnt, ORACLE)
        busy = [tuple(q['fw_ts']) for q in A if 'rep' in q]
        reps = [q for q in B if 'rep' in q]
        for q in reps:
            q['a_running'] = any(s <= q['drm_time'][0] <= e for s, e in busy)
            q['submit_to_start'] = q['fw_ts'][0]-q['drm_time'][0]
            q['fw'] = q['fw_ts'][1]-q['fw_ts'][0]
            q['a_end_after_b_start'] = [e-q['fw_ts'][0] for s, e in busy if s <= q['drm_time'][0] <= e]
        run = {'b_prio': bp, 'ok': ok, 'a': [q for q in A if 'rep' in q], 'b': reps, 'a_failure': [q for q in A if 'failure' in q],
               'b_failure': [q for q in B if 'failure' in q]}
        state['runs'].append(run); save()
        inside = [q for q in reps if q['a_running']]
        med = lambda xs: statistics.median(xs) if xs else None
        print(json.dumps({'b_prio': bp, 'ok': ok, 'a_fw_med_ms': med([(e-s)/1e6 for s, e in busy]), 'b_inside_a': len(inside),
                          'b_wait_inside_med_us': med([q['submit_to_start']/1e3 for q in inside]),
                          'b_wait_inside_max_us': max([q['submit_to_start']/1e3 for q in inside], default=None),
                          'b_fw_inside_med_us': med([q['fw']/1e3 for q in inside]),
                          'b_wait_outside_med_us': med([q['submit_to_start']/1e3 for q in reps if not q['a_running']])}), flush=True)
        if not all(ok.values()):
            sys.exit('stopping on failure')
        time.sleep(1)


if __name__ == '__main__':
    sys.exit(main())
