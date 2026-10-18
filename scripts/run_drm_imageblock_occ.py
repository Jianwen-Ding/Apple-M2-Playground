#!/usr/bin/env python3
"""Does an imageblock layout change threadgroup-memory capacity or occupancy? (safe-11 section 2). Direct DRM, straight-line, no loops.

The USC Shared words of the sr12-sr13-sr15 finding (imageblock width / height, sample stride, sample count) also carry the threadgroup bytes field.
For each of those words the occupancy counter of run_drm_occupancy2.py (peak resident SIMD groups per core; 128-lane workgroups, 16 declared halves,
a 16,000-step chain) runs once with the word and once with a plain-layout word (layout 0x24, no imageblock) that has the same bytes field. If the
imageblock layout consumed threadgroup memory, the peak would be lower than the plain word's.
  run_drm_imageblock_occ.py hardware
"""
import argparse, json, subprocess, sys
from pathlib import Path
import run_drm_compute as drm
import run_drm_occupancy2 as O

REPO = Path(__file__).resolve().parents[1]
WORDS = {'32x32-s8': 0x2010bd4d, '32x16-s8': 0x2010fd4d, '16x16-s8': 0x2010d94d, '32x32-s32': 0x8040bd4d, '32x32-st2': 0x4020bd4d,
         '32x32-st3': 0x6030bd4d, '32x32-st7': 0xe070bd4d, '32x32-st15': 0xe0f0bd4d, '32x32-st0': 0x8000bd4d, '32x32-samples2': 0x4011bd4d,
         '32x32-samples4': 0x8012bd4d, '16x16-samples4': 0x0022d94d}


def plain(bytes_field):
    return 0x4d | 1 << 8 | 0x24 << 10 | (bytes_field << 24)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['hardware'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/imageblock-occ'))
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    (out/'c.bin').write_bytes(drm.build_main(O.body(16000))+bytes(16))
    rec = {'results': []}
    for rep in range(a.repeats):
        for name, word in WORDS.items():
            bf = word >> 24
            for kind, w in (('imageblock', word), ('plain', plain(bf))):
                pt = O.run_point(exe, out, 16, {'AGX_LOCAL_X': '128', 'AGX_SHARED_WORD': str(w)}, 1 << 18)
                r = {'rep': rep, 'name': name, 'kind': kind, 'word': hex(w), 'bytes_field': bf, 'peak_groups': pt['peak_simd_groups'], 'back_to_zero': pt['counters_back_to_zero']}
                rec['results'].append(r)
                print(json.dumps(r), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
