#!/usr/bin/env python3
"""Run a hand-built AGX helper program on the direct DRM path and log what it sees.

The helper is the compute-like program the hardware runs to serve stack /
threadgroup allocation requests (Mesa libagx/helper.cl). Ours:

  1. reads all 256 get_sr selectors and stores them to table[core*512 + s]
     through the 64-bit pointer in SR146/SR147 (helper.data = table VA);
  2. loops at most 64 times: doorbell 32 (wait for a request), log
     (SR144 op, SR146 arg_lo, SR147 arg_hi) at table[core*512 + 256 + 3k],
     exit on op 15 (END) or the cap, otherwise doorbell 49 (NACK);
  3. exits with Mesa's fence_helper_exit barrier sequence and stop.

The main shader is the unchanged control (no stack, spill size 0), so no
allocation request is expected. Doorbell = `jmp_if_skipping_doorbell pc+6;
doorbell imm`, as Mesa emits it and applegpu decodes it. Not emulatable:
the first run is one bounded submission (3 s syncobj wait).
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys

import agx_loop
import run_drm_compute as drm
import run_drm_sr_scan as scan

REPO = Path(__file__).resolve().parents[1]
SENTINEL = 0xcdcdcdcd
REGION = 512
CORES = 64
DB_NEXT, DB_NACK = 32, 49
EXIT = bytes.fromhex('f596f533f59af503f599')+bytes.fromhex('8800')


def doorbell(imm):
    return bytes.fromhex('20000600')+bytes([0x28, imm])


def helper_program(max_requests=64):
    e, mi, gs = agx_loop.encode, agx_loop.chains.mov_imm, scan.get_sr
    st = lambda reg: agx_loop.store_regbase(reg, 2, 5)+e('iadd r5, 1, r5.sx')
    p = bytes.fromhex('62000000')                        # mov_imm r0l, 0 (exec nesting counter)
    p += gs(146, 2)+gs(147, 3)                           # r2_r3 = helper.data
    p += gs(20, 4)+mi(6, REGION)+mi(7, 0)+e('imadd r5, r4, r6, r7')
    for s in range(256):
        p += gs(s, 1)+st(1)+e('wait 0')
    p += mi(8, 0)+mi(9, max_requests)+mi(11, 15)
    p += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    top = len(p)
    p += doorbell(DB_NEXT)
    p += gs(144, 10)+agx_loop.store_regbase(10, 2, 5)+e('iadd r5, 1, r5.sx')
    p += gs(146, 1)+st(1)+gs(147, 12)+agx_loop.store_regbase(12, 2, 5)+e('iadd r5, 1, r5.sx')+e('wait 0')
    p += e('iadd r8, 1, r8.sx')
    p += e('while_icmp r0l, nueq, r10, r11, 1')            # END -> inactive
    p += e('while_icmp r0l, ult, r8, r9, 1')             # cap -> inactive
    nack = doorbell(DB_NACK)
    back_len = 6                                         # jmp_exec_any size
    skip = 6+len(nack)+back_len                          # jmp_exec_none + nack + jmp back
    p += e(f'jmp_exec_none pc+{skip}', f'jmp_exec_none pc+{skip}')
    p += nack
    p += e(f'jmp_exec_any pc-{len(p)-top}', f'jmp_exec_any pc-{len(p)-top}')
    p += e('pop_exec r0l, 1')+EXIT
    return p


def disassemble(code):
    _, g = agx_loop._tools()
    out, i = [], 0
    while i < len(code):
        n = g.opcode_to_number(code[i:]); d = g.get_instruction_descriptor(n)
        if d is None: raise ValueError(f'undecodable helper byte at {i}')
        sz = d.decode_size(n); out.append((i, code[i:i+sz].hex(), ' '.join(str(d.disassemble(n)).split()))); i += sz
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--count', type=int, default=64)
    p.add_argument('--cfg', default='0')
    p.add_argument('--max-requests', type=int, default=64)
    p.add_argument('--dry-run', action='store_true', help='build and disassemble only')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    helper = helper_program(a.max_requests)
    listing = disassemble(helper)
    if a.dry_run:
        for x in listing[:6]+[('...',)]+listing[-24:]: print(*x)
        print('bytes', len(helper)); return 0
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/helper')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode: sys.exit('build failed')
    (out/'helper.bin').write_bytes(helper)
    main_code = drm.build_main(bytes.fromhex('620978563412'))
    (out/'main.bin').write_bytes(main_code+bytes(16))
    table = out/'table.bin'; table.write_bytes(struct.pack('<I', SENTINEL)*(CORES*REGION))
    dump = out/'table.out'; rb = out/'readback'
    env = dict(os.environ, AGX_HELPER_CODE=str(out/'helper.bin'), AGX_HELPER_DATA='table', AGX_HELPER_CFG=a.cfg, AGX_TABLE_OUT=str(dump))
    res = subprocess.run([str(exe), a.device, str(out/'main.bin'), str(a.count), str(rb), '1', '32', str(table)],
                         env=env, capture_output=True, timeout=60)
    events = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
    rec = {'utc': stamp, 'path': 'direct-drm', 'kind': 'helper', 'count': a.count, 'cfg': a.cfg, 'max_requests': a.max_requests,
           'returncode': res.returncode, 'events': events, 'helper_hex': helper.hex(), 'helper_listing': listing}
    if res.returncode == 0:
        rounded = (a.count+31)//32*32
        w = list(struct.unpack(f'<{rounded+32}I', rb.read_bytes()))
        expected = [SENTINEL]*(rounded+16)+[0xa5a50000+j for j in range(16)]; expected[8:8+a.count] = [0x12345678]*a.count
        rec['buffer_ok'] = w == expected
        t = struct.unpack(f'<{CORES*REGION}I', dump.read_bytes())
        cores = {}
        for c in range(CORES):
            region = t[c*REGION:(c+1)*REGION]
            if all(v == SENTINEL for v in region): continue
            log = []
            for k in range(a.max_requests):
                op = region[256+3*k:259+3*k]
                if op[0] == SENTINEL: break
                log.append(list(op))
            cores[c] = {'sr': list(region[:256]), 'log': log}
        rec['cores'] = cores
    (out/'record.json').write_text(json.dumps(rec)+'\n')
    summary = {'returncode': res.returncode, 'buffer_ok': rec.get('buffer_ok'), 'cores_with_helper_output': sorted(rec.get('cores', {})),
               'fw_ns': [e['fw_ts'][1]-e['fw_ts'][0] for e in events if 'rep' in e], 'output': str(out),
               'tail': res.stdout.decode(errors='replace')[-300:] if res.returncode else ''}
    print(json.dumps(summary))
    return 0 if res.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
