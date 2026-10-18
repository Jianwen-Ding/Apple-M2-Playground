#!/usr/bin/env python3
"""SLC / shared-cache capacity by bandwidth (safe-03 section 3). Direct DRM, bounded counted loop (emulator-gated), no data-dependent exit.

All lanes of a dispatch (65,536 lanes = 2,048 SIMD groups on all 38 cores) sweep a shared window of W MiB: lane i loads word
(i + j * 65536) mod Wwords for j = 0 .. loads - 1 (the whole grid advances 256 KiB per step and wraps at W), so every word of the window is read
once per pass, passes = total / W. Total traffic is the same for every W (512 MiB: 2,048 loads per group), so the dispatch time shows where
passes after the first stop being served from the caches. A dispatch is one command (a command boundary flushes the caches, so reuse inside a
dispatch is what is measured); the first pass is always cold. Table T[w] = w so the sum each lane accumulates checks the access pattern.
  run_drm_slc.py offline | hardware [--windows 4,8,...]
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import array
import agx_loop, run_drm_compute as drm, gpu_safety
import run_agx_timestamps as chains

REPO = Path(__file__).resolve().parents[1]
mov, enc = chains.mov_imm, agx_loop.encode
LANES = 65536
STEPS = 8
TRIPS = 256            # 8 x 256 = 2,048 loads per lane = 512 MiB over the dispatch
S = LANES              # words advanced per load by the whole grid


def body(trips, wwords):
    head = mov(3, 0)+mov(4, trips)+mov(14, S)+mov(2, 0)+mov(16, wwords)+enc('iadd r5, r1, 0')
    head += enc('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    loop = b''
    for k in range(STEPS):
        loop += enc(f'device_load 0, i32, x, r{6+k}, u8_u9, r5, unsigned')+enc('iadd r5, r5, r14')
        loop += enc('isub r17, r5, r16')+enc('icmpsel ult, r5, r5, r16, r5, r17')      # r5 = r5 < W ? r5 : r5 - W (W >= S)
    loop += enc('wait 0')
    loop += b''.join(enc(f'iadd r2, r2, r{6+k}') for k in range(STEPS))
    loop += enc('iadd r3, 1, r3.sx')+enc('while_icmp r0l, ult, r3, r4, 1')
    jump = enc(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}')
    return head+loop+jump+enc('pop_exec r0l, 1')


def oracle(lane, trips, wwords):
    return sum((lane + j*S) % wwords for j in range(trips*STEPS)) & 0xffffffff


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--windows', default='4,8,12,16,20,24,28,32,40,48,56,64,80,96,128')
    p.add_argument('--repeats', type=int, default=9)
    p.add_argument('--keeper', action='store_true', help='hold the top GPU clock with scripts/clock_keeper.py (its 6.3 ms command boundaries flush the caches now and then)')
    p.add_argument('--cpu-threads', type=int, default=0, help='run this many CPU threads streaming 64 MiB each (tests/cpu_stream.c) during the measurement')
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/slc'))
    a = p.parse_args()
    if a.mode == 'offline':
        sys.path.insert(0, str(REPO.parent/'AGX-Performance-Simulator/scripts'))
        import coverage as cov
        wwords, trips, n = 4*262144, 5, 64
        code = drm.build_main(body(trips, wwords))
        table = list(range(wwords))           # the simulator maps the table words as given
        o, t = cov.simulate(code, n, 32, 64, 0, table)
        got = o[8:8+n]
        want = [oracle(i, trips, wwords) for i in range(n)]
        print('simulator gate (4 MiB window, 5 trips, 64 lanes): outputs equal the oracle:', got == want)
        return 0 if got == want else 1
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'lanes': LANES, 'loads_per_lane': TRIPS*STEPS, 'traffic_mib': 512, 'keeper': a.keeper, 'windows': {}}
    cpu = None
    if a.cpu_threads:
        import time
        subprocess.run(['cc', '-std=c11', '-O2', '-pthread', str(REPO/'tests/cpu_stream.c'), '-o', str(out/'cpu_stream')], check=True)
        cstop = out/'cpu-stop'; cstop.unlink(missing_ok=True)
        cpu = subprocess.Popen([str(out/'cpu_stream'), str(a.cpu_threads), str(cstop)])
        time.sleep(3)
        rec['cpu_threads'] = a.cpu_threads
    keeper = None
    if a.keeper:
        import time
        stop = out/'keeper-stop'; stop.unlink(missing_ok=True)
        keeper = subprocess.Popen([sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '900', '--stop-file', str(stop)], cwd=REPO,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
    for wm in [int(x) for x in a.windows.split(',')]:
        wwords = wm*262144
        with open(out/'t.bin', 'wb') as f:
            for lo in range(0, wwords, 1 << 22):
                array.array('I', range(lo, min(lo + (1 << 22), wwords))).tofile(f)
        (out/'c.bin').write_bytes(drm.build_main(body(TRIPS, wwords))+bytes(16))
        gpu_safety.require_budget(1)
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(LANES), str(out/'rb'), str(a.repeats), '64', str(out/'t.bin')],
                           capture_output=True, timeout=300, env={'PATH': '/usr/bin'})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != a.repeats or not all(x['fw_ts'][0] and x['fw_ts'][1] for x in smp):
            gpu_safety.record(f'slc {wm}')
            sys.exit(f'run failed at {wm} MiB: '+r.stdout.decode()[-300:])
        w = struct.unpack(f'<{LANES+32}I', (out/'rb').read_bytes())
        exact = all(w[8+i] == oracle(i, TRIPS, wwords) for i in range(0, LANES, 997))
        ns = [x['fw_ts'][1]-x['fw_ts'][0] for x in smp]
        rec['windows'][str(wm)] = {'fw_ns': ns, 'outputs_exact_sampled': exact}
        med = sorted(ns)[len(ns)//2]
        print(f'{wm:4d} MiB window: median {med/1e6:7.3f} ms  effective {512*1048576/med:7.1f} GB/s  min {min(ns)/1e6:.3f}  exact {exact}', flush=True)
    if cpu is not None:
        cstop.touch(); cpu.wait(timeout=60)
    if keeper is not None:
        stop.touch()
        try:
            keeper.wait(timeout=60)
        except subprocess.TimeoutExpired:
            keeper.kill()
        rec['keeper_stopped'] = keeper.poll() is not None
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
