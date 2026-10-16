#!/usr/bin/env python3
"""SR113 over consecutive submissions of one process (direct DRM).

Every lane of every submission atomically adds its SR113 to one table word (device atomic add, validated in
sr-direct-drm), then the usual control store. With L lanes and R submissions the word ends at
sentinel + L * sum(SR113 per submission), so (word - sentinel) / (8 L) counts the submissions that read 8.
A second word gets 1 per lane per submission, proving every submission ran (= L * R).
Processes with R = 1, 2, 3, 5, 10, 20 submissions, each several times, optionally after an idle gap.
"""
import argparse, datetime, json, os, shlex, struct, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import run_drm_sr_scan as scan  # noqa: E402
agx_loop = scan.agx_loop
SENTINEL = scan.SENTINEL


def body(S, delay=0):
    b = agx_loop.chains.mov_imm(5, 1*S)+scan.get_sr(113, 6)+agx_loop.atomic_add(8, 5, 6)
    b += agx_loop.chains.mov_imm(5, 2*S)+agx_loop.chains.mov_imm(7, 1)+agx_loop.atomic_add(8, 5, 7)
    b += agx_loop.encode('wait 0')
    if delay:
        b += scan.delay_loop(delay)
    b += bytes.fromhex('620978563412')
    return b


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reps', default='1,2,3,5,10,20')
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--gap-ms', type=int, default=0, help='sleep before each process')
    p.add_argument('--lanes', type=int, default=64)
    p.add_argument('--delay', type=int, default=0, help='delay-loop trips after the atomics (4000 is about 1 ms; max 20000)')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if a.delay > 20000:
        sys.exit('refusing: delay > 20000 trips')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/sr113-reps')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    S = (a.lanes+31)//32*32
    (out/'k.bin').write_bytes(scan.drm.build_main(body(S, a.delay))+bytes(16))
    rows = []
    try:
        for t in range(a.trials):
            for R in [int(x) for x in a.reps.split(',')]:
                time.sleep(a.gap_ms/1e3)
                (out/'table.bin').write_bytes(struct.pack('<I', SENTINEL)*(4*S))
                env = dict(os.environ, AGX_TABLE_OUT=str(out/'dump'))
                res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(a.lanes), str(out/'rb'), str(R), '32', str(out/'table.bin')],
                                     env=env, capture_output=True, timeout=60)
                ev = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
                reps = [e for e in ev if 'rep' in e]
                normal = res.returncode == 0 and len(reps) == R and all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in reps)
                if not normal:
                    raise RuntimeError(f'R={R}: failed or hang signature: {res.stdout.decode(errors="replace")[-300:]}')
                t_ = struct.unpack(f'<{4*S}I', (out/'dump').read_bytes())
                w = list(struct.unpack(f'<{S+32}I', (out/'rb').read_bytes()))
                exp = [SENTINEL]*(S+16)+[0xa5a50000+j for j in range(16)]
                exp[8:8+a.lanes] = [0x12345678]*a.lanes
                ran = (t_[2*S]-SENTINEL) & 0xffffffff
                s113 = (t_[S]-SENTINEL) & 0xffffffff
                row = {'trial': t, 'R': R, 'buffer_ok': w == exp, 'ran_ok': ran == a.lanes*R, 'sr113_sum': s113,
                       'reps_reading_8': s113/(8*a.lanes), 'fw_us': [round((e['fw_ts'][1]-e['fw_ts'][0])/1e3, 1) for e in reps], 'fw_ts': [e['fw_ts'] for e in reps]}
                rows.append(row)
                print(json.dumps(row), flush=True)
                if not (row['buffer_ok'] and row['ran_ok']):
                    raise RuntimeError('oracle failed')
        passed = True
    except Exception as e:
        passed = False
        print(json.dumps({'error': f'{type(e).__name__}: {e}'}), flush=True)
    (out/'record.json').write_text(json.dumps({'utc': stamp, 'args': vars(a) | {'output': str(out)}, 'rows': rows, 'passed': passed})+'\n')
    print(json.dumps({'passed': passed, 'output': str(out)}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
