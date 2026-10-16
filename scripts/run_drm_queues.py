#!/usr/bin/env python3
"""How many queues execute at once (simulator task safe-04 step 2), direct DRM, one process.

tests/drm_compute.c AGX_QUEUES=N creates N queues on one VM; per repeat each submits the same small delay-kernel
command (64 lanes, gated by sim_gate) with no dependencies, and all are waited for. From the firmware timestamps:
the largest number of commands running at the same instant, the spread of start times, and each command's time.
"""
import argparse, datetime, json, os, shlex, statistics, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402
import run_drm_sr_scan as scan  # noqa: E402

ORACLE = 0x12345678


def concurrency(ts):
    ev = sorted([(s, 1) for s, _ in ts]+[(e, -1) for _, e in ts])
    cur = best = 0
    for _, d in ev:
        cur += d; best = max(best, cur)
    return best


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ns', default='2,4,8,16,32')
    p.add_argument('--delay', type=int, default=4000)
    p.add_argument('--count', type=int, default=64)
    p.add_argument('--repeats', type=int, default=8)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    ns = [int(n) for n in a.ns.split(',')]
    if not (all(2 <= n <= 32 for n in ns) and ns == sorted(ns) and 1 <= a.delay <= 20000 and 1 <= a.repeats <= 64):
        sys.exit('refusing: N in 2..32 ascending, bounded delay / repeats required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/queues')/stamp
    out.mkdir(parents=True, exist_ok=False)
    k = drm.build_main(scan.delay_loop(a.delay)+bytes.fromhex('620978563412'))
    state = {'utc': stamp, 'count': a.count, 'delay': a.delay, 'repeats': a.repeats,
             'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(),
             'kernel': {'code_hex': k.hex(), 'simulator': sim_gate.require(k, a.count, ORACLE)}, 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    save()
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    (out/'k.bin').write_bytes(k+bytes(16))
    for n in ns:
        gpu_safety.require_budget(1)
        rb = out/f'q{n}.readback'
        try:
            res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(a.count), str(rb), str(a.repeats), '16'],
                                 capture_output=True, timeout=120, env=dict(os.environ, AGX_QUEUES=str(n)))
        except subprocess.TimeoutExpired:
            gpu_safety.record(f'run_drm_queues N={n}: harness timeout'); save(); sys.exit('timeout: stopping')
        lines = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{')]
        reps = [l for l in lines if 'multi' in l]
        w = len(rb.read_bytes())//4 if rb.exists() else 0
        ok = res.returncode == 0 and w and sim_gate.oracle_ok(list(struct.unpack(f'<{w}I', rb.read_bytes())), a.count, ORACLE)
        for q in reps:
            q['concurrency'] = concurrency(q['ts'])
            q['start_spread'] = max(s for s, _ in q['ts'])-min(s for s, _ in q['ts'])
            q['span'] = max(e for _, e in q['ts'])-min(s for s, _ in q['ts'])
        state['runs'].append({'n': n, 'returncode': res.returncode, 'oracle_ok': bool(ok), 'reps': reps,
                              'failure': [l for l in lines if 'failure' in l]}); save()
        med = lambda f: statistics.median(f(q) for q in reps) if reps else None
        print(json.dumps({'n': n, 'ok': bool(ok), 'concurrency': [q['concurrency'] for q in reps],
                          'start_spread_med_us': med(lambda q: q['start_spread']/1e3), 'submit_med_us': med(lambda q: q['submit_ns']/1e3),
                          'span_med_us': med(lambda q: q['span']/1e3),
                          'cmd_med_us': med(lambda q: statistics.median(e-s for s, e in q['ts'])/1e3)}), flush=True)
        if not ok:
            sys.exit('stopping on failure')


if __name__ == '__main__':
    sys.exit(main())
