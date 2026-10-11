#!/usr/bin/env python3
"""Resident SIMD groups per core versus declared register count (direct DRM).

Each lane: core = SR20; old = atomic_add(counter[core], 1) (returned); a straight-line
chain of dependent iadds (no loop, so no hang risk); atomic_sub(counter[core], 1);
output = old. The maximum old+1 seen on a core is the peak number of lanes that were
between their increment and decrement at once; divided by 32 it is the peak resident
SIMD groups. Only encodings validated in the atomics finding are used.
"""
import argparse, json, struct, subprocess, sys
from collections import defaultdict
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
import patch_agx_sr as patcher
from run_drm_opcode_describe import get_sr

REPO = Path(__file__).resolve().parents[1]


def body(steps):
    e = agx_loop.encode; mov = chains.mov_imm
    gpu, _ = patcher.load_model(chains.APPLEGPU)
    # registers r2..r6 only (fits 16 declared halves): r3 core, r4 counter index, r5 = 1, r6 old
    ins = [get_sr(20, 3), mov(4, 256), e('iadd r4, r3, r4'), mov(5, 1),
           DA.atomic(0, 6, 4, 5, True), e('wait 0')]
    ins += [mov(2, 0)] + [chains.encode_step('iadd8', 2, gpu)]*steps
    ins += [DA.atomic(1, 0, 4, 5, False), e('wait 0'), e('iadd r2, r6, 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gprs', default=','.join(str(g) for g in range(16, 249, 8)))
    p.add_argument('--steps', type=int, default=2000)
    p.add_argument('--count', type=int, default=1 << 20)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--local-x', type=int, default=0, help='workgroup size (AGX_LOCAL_X); 0 = harness default')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/occupancy-atomic'))
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    code = drm.build_main(body(a.steps))
    (out/'c.bin').write_bytes(code+bytes(16))
    rec = {'local_x': a.local_x, 'steps': a.steps, 'count': a.count, 'code_bytes': len(code), 'points': []}
    for rep in range(a.repeats):
        for g in [int(x) for x in a.gprs.split(',')]:
            (out/'t.bin').write_bytes(bytes(4*320))
            try:
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(a.count), str(out/'rb'), '1', str(g), str(out/'t.bin')],
                                   capture_output=True, timeout=20, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin', **({'AGX_LOCAL_X': str(a.local_x)} if a.local_x else {})})
            except subprocess.TimeoutExpired:
                sys.exit(f'timeout at gprs {g}; stopping')
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or not smp: sys.exit(f'dispatch failed at gprs {g}')
            w = struct.unpack(f'<{a.count+32}I', (out/'rb').read_bytes())[8:8+a.count]
            t = struct.unpack('<320I', (out/'t.out').read_bytes())
            peak = max(w)+1
            pt = {'rep': rep, 'gprs': g, 'peak_lanes_any_core': peak, 'peak_simd_groups': peak/32,
                  'counters_back_to_zero': all(v == 0 for v in t[256:320]), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}
            rec['points'].append(pt)
            print(json.dumps(pt), flush=True)
    (out/'record.json').write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
