#!/usr/bin/env python3
"""Occupancy follow-ups (safe-11 section 1): workgroup-size sweep, 2-D / 3-D shapes, registers x threadgroup memory together.

Like run_drm_occupancy.py (per-core counter: SR20-indexed device atomic add with return, a straight-line dependent chain, atomic sub),
but the peak is tracked on the device with an atomic *umax* of (old + 1) into a per-core slot, so any launch geometry works (the
per-lane output of the first runner is indexed by the x position only). peak SIMD groups of a core = peak lanes / 32.
Only Mesa-named atomic ops 0 (add), 1 (sub), 6 (umax) and instructions validated earlier. No loops.
  run_drm_occupancy2.py --mode sizes|shapes|combined|offline
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
import patch_agx_sr as patcher
from run_drm_opcode_describe import get_sr

REPO = Path(__file__).resolve().parents[1]
CNT, MAX = 256, 512


def body(steps):
    e = agx_loop.encode; mov = chains.mov_imm
    gpu, _ = patcher.load_model(chains.APPLEGPU)
    # r3 core (then the max-slot index), r4 counter index, r5 = 1, r6 old, r7 old + 1: r0..r7 = the 16 declared halves
    ins = [get_sr(20, 3), mov(4, CNT), e('iadd r4, r3, r4'), mov(5, 1), mov(3, MAX-CNT), e('iadd r3, r4, r3'),
           DA.atomic(0, 6, 4, 5, True), e('wait 0'), e('iadd r7, r6, 1'), DA.atomic(6, 0, 3, 7, False)]
    ins += [mov(2, 0)] + [chains.encode_step('iadd8', 2, gpu)]*steps
    ins += [DA.atomic(1, 0, 4, 5, False), e('wait 0'), e('iadd r2, r6, 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def shape_env(count, lx, ly, lz):
    """Local size (lx, ly, lz); global = (count / (ky*kz), ly*ky, lz*kz) with ky = kz = 4 when the dimension is > 1."""
    ky = 4 if ly > 1 else 1
    kz = 4 if lz > 1 else 1
    gy, gz = ly*ky, lz*kz
    gx = count//(gy*gz)
    assert gx % lx == 0 and gx*gy*gz == count, (lx, ly, lz, gx)
    return {'AGX_LOCAL_X': str(lx), 'AGX_LOCAL_Y': str(ly), 'AGX_LOCAL_Z': str(lz),
            'AGX_GLOBAL_X': str(gx), 'AGX_GLOBAL_Y': str(gy), 'AGX_GLOBAL_Z': str(gz)}


def shared_word(sh):
    return {'AGX_SHARED_WORD': str(0x4d | 1 << 8 | 0x24 << 10 | (((sh // 256) & 255) << 24))} if sh else {}


def run_point(exe, out, g, env, count):
    (out/'t.bin').write_bytes(bytes(4*640))
    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(count), str(out/'rb'), '1', str(g), str(out/'t.bin')],
                       capture_output=True, timeout=30, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin', **env})
    smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
    if r.returncode or not smp or not all(smp[0]['fw_ts']):
        sys.exit(f'dispatch failed (gprs {g}, env {env}): '+r.stdout.decode()[-200:])
    t = struct.unpack('<640I', (out/'t.out').read_bytes())
    return {'peak_lanes': max(t[MAX:MAX+64]), 'peak_simd_groups': max(t[MAX:MAX+64])/32,
            'counters_back_to_zero': all(v == 0 for v in t[CNT:CNT+64]), 'cores_used': sum(1 for v in t[MAX:MAX+64] if v),
            'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', required=True, choices=['sizes', 'shapes', 'combined', 'steps', 'offline'])
    p.add_argument('--steps', type=int, default=2000)
    p.add_argument('--count', type=int, default=1 << 20)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/occupancy2'))
    a = p.parse_args()
    code = drm.build_main(body(a.steps))
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        o, t = cov.simulate(code, 4096, 128, 16, 0, [0]*640)
        print('simulator run: counters back to zero', all(v == 0 for v in t[CNT:CNT+64]), 'peak slot', max(t[MAX:MAX+64]))
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    (out/'c.bin').write_bytes(code+bytes(16))
    points = []
    jobs = []
    if a.mode == 'sizes':
        for lx in [32, 64, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 640, 768, 896, 1024]:
            jobs.append(({'lx': lx}, 16, {'AGX_LOCAL_X': str(lx), 'AGX_GLOBAL_X': str(-(-a.count//lx)*lx)}))   # the program's bounds guard skips lanes >= count
    elif a.mode == 'shapes':
        for shape in [(128, 1, 1), (32, 4, 1), (16, 8, 1), (8, 16, 1), (4, 32, 1), (64, 2, 1), (8, 4, 4), (4, 4, 8), (16, 4, 2), (32, 2, 2), (256, 1, 1),
                      (64, 4, 1), (16, 4, 4), (32, 32, 1), (64, 1, 1), (8, 8, 1), (2, 2, 2), (4, 4, 4)]:
            jobs.append(({'shape': list(shape), 'threads': shape[0]*shape[1]*shape[2]}, 16, shape_env(a.count, *shape)))
    else:
        for g in (16, 48, 64, 96, 128, 192):
            for sh in (0, 4096, 8192, 16384, 24576, 32768):
                jobs.append(({'gprs': g, 'shared': sh}, g, {'AGX_LOCAL_X': '128', **shared_word(sh)}))
    if a.mode == 'steps':
        for rep in range(a.repeats):
            for steps in (250, 1000, 4000, 16000):
                (out/'c.bin').write_bytes(drm.build_main(body(steps))+bytes(16))
                for lx in (32, 64, 96):
                    pt = {'rep': rep, 'lx': lx, 'steps': steps, **run_point(exe, out, 16, {'AGX_LOCAL_X': str(lx), 'AGX_GLOBAL_X': str(-(-a.count//lx)*lx)}, a.count)}
                    points.append(pt)
                    print(json.dumps(pt), flush=True)
        jobs = []
    for rep in range(a.repeats):
        for meta, g, env in jobs:
            pt = {'rep': rep, **meta, **run_point(exe, out, g, env, a.count)}
            points.append(pt)
            print(json.dumps(pt), flush=True)
    if a.result:
        a.result.write_text(json.dumps({'mode': a.mode, 'steps': a.steps, 'count': a.count, 'points': points})+'\n')


if __name__ == '__main__':
    main()
