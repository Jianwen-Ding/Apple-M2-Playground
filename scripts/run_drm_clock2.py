#!/usr/bin/env python3
"""In-shader clock under load (safe-11 section 3). Direct DRM, straight-line, no loops, no waiting on a value.

tests/drm_compute.c with AGX_CPU_CLOCK=0 keeps a CPU thread writing the low 32 bits of CNTVCT_EL0 (24 MHz) into table words
32*l + 1 for `AGX_CPU_CLOCK_LINES` = L copies l = 0..L-1 (128 B apart). Every lane reads its copy R = 8 times, each read being
`device_barrier_1` (f59d) + a coherent load + `wait 0`, and stores the eight timer words and its SR20 core.
  cost per read = (t[R-1] - t[0]) / (R - 1) ticks x 41.67 ns; the copy is  l = core & (L-1)  (L = 1: everyone reads the same line).
Sweeps lane counts 1 / 32 / 1,024 / 65,536 and L = 1 / 2 / 4 / 8 / 16.
  run_drm_clock2.py offline|hardware
"""
import argparse, json, os, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
from run_drm_cpu_clock import load, RES
from run_drm_opcode_describe import get_sr, WAIT
from run_drm_sync_probe import finish

REPO = Path(__file__).resolve().parents[1]
mov, enc = agx_loop.chains.mov_imm, agx_loop.encode
R = 8
F59D = bytes.fromhex('f59d')
TICK_NS = 1e9/24e6


def body(L):
    b = get_sr(80, 24)+get_sr(20, 25)
    b += mov(22, L-1)+enc('and r26, r25, r22')+mov(21, 32)+mov(20, 1)+enc('imadd r27, r26, r21, r20')   # timer word index of this lane's copy
    for k in range(R):
        b += F59D+load(10+k, 27, True)+WAIT
    stride = R+1
    b += mov(18, stride)+mov(19, RES)+enc('imadd r29, r24, r18, r19')
    for k in range(R):
        b += agx_loop.store(10+k, 8, 29)+enc('iadd r29, r29, 1')
    b += agx_loop.store(25, 8, 29)
    return b+WAIT+finish()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/clock2'))
    a = p.parse_args()
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        for L in (1, 16):
            n = 64
            code = drm.build_main(body(L))
            o, t = cov.simulate(code, n, 32, 64, 0, [0]*(RES+(R+1)*n))
            print('simulator run L=%d ok, core words' % L, sorted({t[RES+(R+1)*i+R] for i in range(n)}))
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'R': R, 'results': []}
    for n in (1, 32, 1024, 65536):
        for L in (1, 2, 4, 8, 16):
            code = drm.build_main(body(L))
            words = RES+(R+1)*n
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack('<I', 0xcdcdcdcd)*words)
            env = dict(os.environ, AGX_CPU_CLOCK='0', AGX_CPU_CLOCK_LINES=str(L), AGX_TABLE_OUT=str(out/'t.out'))
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), str(a.repeats), '64', str(out/'t.bin')],
                               capture_output=True, env=env, timeout=120)
            ev = [json.loads(l) for l in r.stdout.decode().splitlines() if l.startswith('{')]
            smp = [e for e in ev if 'rep' in e]
            if r.returncode or len(smp) != a.repeats:
                sys.exit(f'dispatch failed n={n} L={L}: '+r.stdout.decode()[-300:])
            cal = next(e['cpu_clock'] for e in ev if 'cpu_clock' in e)
            t = struct.unpack(f'<{words}I', (out/'t.out').read_bytes())
            lanes = [t[RES+(R+1)*i:RES+(R+1)*(i+1)] for i in range(n)]
            cost = sorted(((l[R-1]-l[0]) & 0xffffffff)/(R-1)*TICK_NS for l in lanes)
            mono = all(all(((l[k+1]-l[k]) & 0xffffffff) < 0x80000000 for k in range(R-1)) for l in lanes)
            first = [l[0] for l in lanes]
            base = min(first)
            spread0 = (max(first)-base)*TICK_NS
            spreadK = (max(l[R-1] for l in lanes)-min(l[R-1] for l in lanes))*TICK_NS
            # lanes of one SIMD group read the same value?
            same_group = all(len({l[k] for l in lanes[g:g+32]}) == 1 for g in range(0, n-n % 32 if n >= 32 else 0, 32) for k in range(R)) if n >= 32 else True
            cores = len({l[R] for l in lanes})
            res = {'lanes': n, 'copies': L, 'cost_ns_median': cost[len(cost)//2], 'cost_ns_p10': cost[len(cost)//10], 'cost_ns_p90': cost[9*len(cost)//10],
                   'monotonic': mono, 'first_read_spread_ns': spread0, 'last_read_spread_ns': spreadK, 'group_uniform': same_group,
                   'cores': cores, 'sentinel_words': sum(1 for x in t[RES:] if x == 0xcdcdcdcd),
                   'fw_ns': [e['fw_ts'][1]-e['fw_ts'][0] for e in smp], 'cntfrq': cal['cntfrq']}
            rec['results'].append(res)
            print(json.dumps(res), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
