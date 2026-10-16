#!/usr/bin/env python3
"""Several compute commands per SUBMIT (simulator task safe-04 step 4), direct DRM, one queue.

tests/drm_compute.c AGX_CMDS=N puts N copies of the same compute command in one SUBMIT, each with its own firmware
start / end timestamps; AGX_CMD_BARRIER=chain makes command k wait on the k before it, none lets commands after the
first run without waiting. Kernels (both gated by sim_gate before any GPU use): the pinned control kernel and an
emulator-gated delay loop (~0.4 ms for 4000 trips). N grows only after the previous N passed its oracle.
"""
import argparse, datetime, json, os, shlex, statistics, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402
import run_drm_sr_scan as scan  # noqa: E402

ORACLE = 0x12345678


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ns', default='1,2,4,8,16,32,64')
    p.add_argument('--kinds', default='control,delay')
    p.add_argument('--barriers', default='chain,none')
    p.add_argument('--delay', type=int, default=4000)
    p.add_argument('--count', type=int, default=64)
    p.add_argument('--repeats', type=int, default=8)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    ns = [int(n) for n in a.ns.split(',')]
    if not (all(1 <= n <= 64 for n in ns) and ns == sorted(ns) and 1 <= a.delay <= 20000 and 1 <= a.repeats <= 64):
        sys.exit('refusing: N in 1..64 ascending, bounded delay / repeats required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/cmds')/stamp
    out.mkdir(parents=True, exist_ok=False)
    kernels = {'control': drm.build_main(bytes.fromhex('620978563412')),
               'delay': drm.build_main(scan.delay_loop(a.delay)+bytes.fromhex('620978563412'))}
    state = {'utc': stamp, 'count': a.count, 'repeats': a.repeats, 'delay': a.delay,
             'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(), 'kernels': {}, 'runs': []}
    for k in a.kinds.split(','):
        state['kernels'][k] = {'code_hex': kernels[k].hex(), 'simulator': sim_gate.require(kernels[k], a.count, ORACLE)}
        (out/f'{k}.bin').write_bytes(kernels[k]+bytes(16))
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    save()
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    for k in a.kinds.split(','):
        for bar in a.barriers.split(','):
            for n in ns:
                gpu_safety.require_budget(1)
                rb = out/f'{k}-{bar}-{n}.readback'
                env = dict(os.environ, AGX_CMDS=str(n), AGX_CMD_BARRIER=bar)
                try:
                    res = subprocess.run([str(exe), a.device, str(out/f'{k}.bin'), str(a.count), str(rb), str(a.repeats), '16'],
                                         capture_output=True, timeout=120, env=env)
                except subprocess.TimeoutExpired:
                    gpu_safety.record(f'run_drm_cmds {k} {bar} N={n}: harness timeout'); save(); sys.exit('timeout: stopping')
                lines = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{')]
                reps = [l for l in lines if 'rep' in l]
                words = len(rb.read_bytes())//4 if rb.exists() else 0
                ok = res.returncode == 0 and words and sim_gate.oracle_ok(list(struct.unpack(f'<{words}I', rb.read_bytes())), a.count, ORACLE)
                for q in reps:
                    c = q.get('cmd_ts', [q['fw_ts']])
                    q['span'] = max(e for _, e in c)-min(s for s, _ in c)
                    q['gaps'] = [c[i+1][0]-c[i][1] for i in range(len(c)-1)]
                    q['submit_to_first_start'] = min(s for s, _ in c)-q['drm_time'][0]
                rec = {'kind': k, 'barrier': bar, 'n': n, 'returncode': res.returncode, 'oracle_ok': bool(ok), 'reps': reps,
                       'failure': [l for l in lines if 'failure' in l], 'stderr': res.stderr.decode()[-300:]}
                state['runs'].append(rec); save()
                warm = reps[1:] or reps
                med = lambda f: statistics.median(f(q) for q in warm) if warm else None
                print(json.dumps({'kind': k, 'barrier': bar, 'n': n, 'ok': bool(ok), 'failure': rec['failure'],
                                  'span_med_us': med(lambda q: q['span']/1e3),
                                  'per_cmd_us': med(lambda q: q['span']/n/1e3),
                                  'gap_med_us': med(lambda q: statistics.median(q['gaps'])/1e3 if q['gaps'] else 0),
                                  'host_med_us': med(lambda q: q['host_ns']/1e3)}), flush=True)
                if not ok:
                    sys.exit('stopping on failure')
    return 0


if __name__ == '__main__':
    sys.exit(main())
