#!/usr/bin/env python3
"""Offline check of the B1 direct-DRM scratch evidence (no GPU).
1. GPU outputs: word 8+i == 8i+8 for every thread; the 16 guard words after the output are intact.
2. Block layout of the single-group run: the 12 KiB allocation holds B=5i+7 (byte offset 4) at 0x2700+4i and
   A=3i+1 (byte offset 0) at 0x2780+4i, i.e. slot (80-1-offset/4) * 128 + 4*lane.
3. Scratch header after the single-group run: subgroups 128, all alloc_cur 0, alloc_failed 0, exactly one core used.
4. Optional (--sim AGX_RUN): the kernels replay in the simulator's agx_run to the same outputs.
"""
import struct, subprocess, sys, os, tempfile
H = os.path.dirname(os.path.abspath(__file__))
def words(p): b = open(os.path.join(H, p), 'rb').read(); return struct.unpack('<%dI' % (len(b) // 4), b)
fails = 0
def check(ok, what):
    global fails; fails += not ok; print(('PASS ' if ok else 'FAIL ') + what)
for name, n in (('out32', 32), ('out64k', 65536), ('outbig32', 32), ('outbig64k', 65536)):
    w = words(f'gpu/{name}.bin')
    check(all(w[8 + i] == 8 * i + 8 for i in range(n)), f'{name}: {n} threads give 8i+8')
    rounded = (n + 31) // 32 * 32
    check(list(w[8 + rounded + 8:8 + rounded + 24]) == [0xa5a50000 + k for k in range(16)], f'{name}: guard words intact')
blk = words('gpu/full32-core0-sg0-blocks.bin')
check(all(blk[(0x2700 + 4 * i) // 4] == 5 * i + 7 and blk[(0x2780 + 4 * i) // 4] == 3 * i + 1 for i in range(32)),
      'block layout: slot (80-1-offset/4)*128 + 4*lane')
hdr = words('gpu/hdr32.bin')
cores = [hdr[(8 + c * 88) // 4 + 2: (8 + c * 88) // 4 + 5] for c in range(128)]
check(hdr[0] == 128 and all(c[0] == 0 and c[2] == 0 for c in cores) and sum(c[1] > 0 for c in cores) == 1,
      'header after run: balanced, no failures, one core used')
if '--sim' in sys.argv:
    run = sys.argv[sys.argv.index('--sim') + 1]
    for k, n in (('scratch_rt', 65536), ('scratch_big_4000', 65536)):
        with tempfile.TemporaryDirectory() as t:
            o = os.path.join(t, 'o.bin'); size = (n + 72) * 4
            subprocess.run([run, os.path.join(H, 'kernels', k + '.bin'), '--grid', str(n), '--wg', '32', '--regs', '16',
                            '--alloc', f'0x100000={size}', '--uniform', '4=0', '--uniform', f'5={n}', '--uniform', '6=0x100000',
                            '--uniform', '7=0', '--dump', f'0x100000={size}:{o}'], check=True, capture_output=True)
            b = open(o, 'rb').read(); w = struct.unpack('<%dI' % (len(b) // 4), b)
            check(all(w[8 + i] == 8 * i + 8 for i in range(n)), f'sim {k}: {n} threads give 8i+8')
print('failures:', fails); sys.exit(1 if fails else 0)
