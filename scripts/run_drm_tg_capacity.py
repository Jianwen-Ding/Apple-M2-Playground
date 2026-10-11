#!/usr/bin/env python3
"""Usable threadgroup memory versus the declared USC Shared size (direct DRM).

64 lanes store 0x7e000000+i at element index OFF+i (i32), pass threadgroup_barrier and read
element OFF+63-i. The exchange is exact only while the touched bytes fit in the usable size.
Writes a JSON list to --output (default stdout). CONFIRM_GPU_FAULTS=1 is not required: only
decoded, Mesa-emitted instructions are used.
"""
import json, os, struct, subprocess, sys, tempfile
from pathlib import Path
import agx_loop, run_drm_compute as drm
from run_drm_sync_probe import tg_mem, finish, decodes, H
from run_drm_opcode_describe import get_sr, WAIT

REPO = Path(__file__).resolve().parents[1]
mov, enc = agx_loop.chains.mov_imm, agx_loop.encode


def main():
    out = Path(tempfile.mkdtemp(prefix='tgcap-', dir='/scratch/apple-m2-playground/drm-compute'))
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rows = []
    for kb in (8, 16, 32):
        word = 0x4d | 1 << 8 | 0x24 << 10 | (kb*1024//256) << 24
        for off in (0, 448, 480, 512, 960, 1024, 1984, 2000):
            if off*4+256 > kb*1024: continue
            b = get_sr(80, 24)+mov(9, 0x7e000000)+enc('iadd r6, r9, r24')+mov(10, off)+enc('iadd r22, r24, r10')+tg_mem(False, 6, 22)
            b += H('6800')+mov(10, 0xffffffff)+mov(11, 63+off)+enc('imadd r23, r24, r10, r11')
            b += tg_mem(True, 5, 23)+WAIT+agx_loop.store(5, 8, 24)+WAIT+finish()
            decodes(b, set())
            (out/'c.bin').write_bytes(drm.build_main(b)+bytes(16)); (out/'t.bin').write_bytes(struct.pack('<I', 0xcdcdcdcd)*64)
            env = dict(os.environ, AGX_LOCAL_X='64', AGX_SHARED_WORD=str(word), AGX_TABLE_OUT=str(out/'t.out'))
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), '64', str(out/'rb'), '1', '64', str(out/'t.bin')],
                               capture_output=True, env=env, timeout=20)
            if r.returncode: sys.exit('dispatch failed: '+r.stdout.decode()[-200:])
            t = struct.unpack('<64I', (out/'t.out').read_bytes())
            rows.append({'declared_bytes': kb*1024, 'element_offset': off, 'highest_byte_touched': (off+63)*4+3,
                         'exact': list(t) == [0x7e000000+63-i for i in range(64)], 'sample': hex(t[0])})
    text = json.dumps(rows, indent=1)
    if len(sys.argv) > 2 and sys.argv[1] == '--output': Path(sys.argv[2]).write_text(text+'\n')
    else: print(text)


if __name__ == '__main__':
    main()
