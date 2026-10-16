#!/usr/bin/env python3
"""Cache line size per level from sequential pointer chases (simulator task safe-03 step 1), direct DRM.

Table: one sequential cycle, element i (at byte i*s) points to element i+1, the last back to 0; other words
0xffffffff. One SIMD group chases the whole cycle once per dispatch (hops = footprint / s), so every stride touches
the same bytes. Below the line size several hops share a line: ns per hop ~ (miss cost) * s / line + hit cost.
Footprints: 64 KiB (L2-resident: L1 line), 8 MiB (SLC-resident: L2 line), 128 MiB (> 48 MB SLC: DRAM / SLC line).
Run with scripts/clock_keeper.py in the background. Every kernel + table passes sim_gate (agx_run) first.
"""
import argparse, array, datetime, json, os, shlex, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import agx_loop, gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402


def seq_table(foot, s):
    w = s//4; n = foot//s
    t = array.array('I', [0xffffffff])*(foot//4)
    t[0::w] = array.array('I', (((i+1) % n)*w for i in range(n)))
    return t, n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sweeps', default='65536:4,8,16,32,64,128,256,512;8388608:4,8,16,32,64,128,256,512;134217728:32,64,128,256,512')
    p.add_argument('--repeats', type=int, default=4)
    p.add_argument('--passes', type=int, default=1, help='times the cycle is chased per dispatch (1 = cold data each dispatch)')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    sweeps = [(int(f), [int(x) for x in ss.split(',')]) for f, ss in (t.split(':') for t in a.sweeps.split(';'))]
    for f, ss in sweeps:
        if not (4096 <= f <= 256 << 20 and all(s in (4, 8, 16, 32, 64, 128, 256, 512, 1024) and f//s <= 1 << 23 for s in ss)):
            sys.exit('refusing: footprint 4 KiB..256 MiB, power-of-two stride, at most 2^23 hops')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/linesize')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    state = {'utc': stamp, 'repeats': a.repeats, 'passes': a.passes, 'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(), 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    for foot, strides in sweeps:
        for s in strides:
            t, n = seq_table(foot, s)
            hops = n*a.passes
            if hops > 1 << 24: sys.exit('refusing: more than 2^24 hops per dispatch')
            tp = out/'t.bin'; tp.write_bytes(t.tobytes())
            body = agx_loop.chase_body(hops, 1, starts=[0])
            want = agx_loop.chase_want(t, hops, [0])          # whole cycles return to 0
            code = drm.build_main(body)
            gate = sim_gate.require(code, 32, want, regs=16, table=tp)
            gpu_safety.require_budget(1)
            (out/'k.bin').write_bytes(code+bytes(16))
            try:
                res = subprocess.run([str(exe), a.device, str(out/'k.bin'), '32', str(out/'rb'), str(a.repeats), '16', str(tp)],
                                     capture_output=True, timeout=120)
            except subprocess.TimeoutExpired:
                gpu_safety.record(f'run_drm_linesize {foot}/{s}: timeout'); save(); sys.exit('timeout: stopping')
            lines = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{')]
            reps = [l for l in lines if 'rep' in l]
            w = len((out/'rb').read_bytes())//4 if (out/'rb').exists() else 0
            ok = res.returncode == 0 and w and sim_gate.oracle_ok(list(struct.unpack(f'<{w}I', (out/'rb').read_bytes())), 32, want)
            fw = [q['fw_ts'][1]-q['fw_ts'][0] for q in reps]
            rec = {'footprint': foot, 'stride': s, 'hops': hops, 'passes': a.passes, 'oracle_ok': bool(ok), 'fw_ns': fw, 'simulator': gate,
                   'ns_per_hop_min_warm': min(fw[1:] or fw)/hops if fw else None}
            state['runs'].append(rec); save()
            print(json.dumps({'footprint': foot, 'stride': s, 'hops': hops, 'ok': bool(ok), 'ns_per_hop': [round(x/hops, 2) for x in fw]}), flush=True)
            if not ok:
                sys.exit('stopping on failure')
            tp.unlink()


if __name__ == '__main__':
    sys.exit(main())
