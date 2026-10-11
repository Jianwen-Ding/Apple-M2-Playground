#!/usr/bin/env python3
"""Check that every part of a large direct-DRM grid executes (tests/drm_compute.c).

Grid: global X = 32 (AGX_GLOBAL_X), global Y = 2^k / 32, local 32 x ly. Threads in
rows with y % 2^s == 0 store y to out[8 + (y >> s) * 32 + x] if that is < count; the oracle requires every
sampled row (all 32 lanes) to hold its own y. Rows are spread over the whole Y
range, so a truncated or wrapped grid leaves 0xcdcdcdcd or wrong values.
s is chosen so at most 2^15 rows are sampled (2^20 output lanes).
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import agx_loop

REPO = Path(__file__).resolve().parents[1]
STORE = bytes.fromhex('45112c0e00c01200')   # device_store 0, i32, x, r2, u6_u7, r1 (control main's store)
ADD8 = bytes.fromhex('0e05082064000000')    # iadd r1, 8, r1.sx (control main)
CHECK = bytes.fromhex('522842a21800')       # if_icmp r0l, ult, r1, u5, 1 (control main's bounds check)


def main_code(s):
    """Sampled rows store y; the index is also bounds-checked against u5 (count) before the store."""
    e = agx_loop.encode
    return b''.join([
        e('get_sr r1, sr80 (thread_position_in_grid.x)'),
        e('get_sr r3, sr81 (thread_position_in_grid.y)'),
        e(f'mov_imm r6, {(1 << s) - 1}, 0b0'),
        e('and r4, r3, r6'),
        e('mov_imm r0l, 0'),
        e('if_icmp r0l, seq, r4, 0, 1'),
        e(f'asr r5, r3, {s}'),
        e('imadd r1, r5, 32, r1'),
        CHECK,
        ADD8,
        e('iadd r2, r3, 0'),
        STORE,
        e('wait 0'), e('pop_exec r0l, 2'), e('stop'),
    ])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log2', default='16,20', help='comma-separated log2 grid sizes (16..30)')
    p.add_argument('--local-y', type=int, default=32)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    ks = [int(x) for x in a.log2.split(',')]
    if not all(16 <= k <= 30 for k in ks) or not 1 <= a.repeats <= 64 or a.local_y not in (1, 2, 4, 8, 16, 32):
        p.error('bounded sizes/repeats/local-y required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/grid-coverage')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(a.cc.split()+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True)
    if r.returncode: sys.exit('build failed: '+r.stderr.decode()[-400:])
    state = {'utc': stamp, 'local_y': a.local_y, 'runs': []}
    ok_all = True
    for k in ks:
        gy = (1 << k)//32
        s = max(0, k-5-15)
        rows = gy >> s
        count = rows*32
        code = main_code(s); cpath = out/f'k{k}.bin'; cpath.write_bytes(code+bytes(16))
        rb = out/f'k{k}.readback'
        env = dict(os.environ, AGX_GLOBAL_X='32', AGX_GLOBAL_Y=str(gy), AGX_LOCAL_Y=str(a.local_y))
        res = subprocess.run([str(exe), a.device, str(cpath), str(count), str(rb), str(a.repeats), '16'],
                             capture_output=True, timeout=120, env=env)
        ev = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
        rec = {'log2': k, 'global_y': gy, 'shift': s, 'rows_sampled': rows, 'count': count, 'code_hex': code.hex(),
               'returncode': res.returncode, 'fw_ns': [e['fw_ts'][1]-e['fw_ts'][0] for e in ev if 'rep' in e],
               'cdm_hex': next((e['cdm_hex'] for e in ev if 'cdm_hex' in e), None)}
        if res.returncode == 0:
            w = struct.unpack(f'<{count+32}I', rb.read_bytes())
            want = [0xcdcdcdcd]*8+[(i//32) << s for i in range(count)]+[0xcdcdcdcd]*8+[0xa5a50000+j for j in range(16)]
            bad = [i for i in range(len(w)) if w[i] != want[i]]
            rec.update(buffer_ok=not bad, mismatches=len(bad), first_mismatches=[[i, w[i], want[i]] for i in bad[:8]])
            rb.unlink()
        else:
            rec.update(buffer_ok=False, stdout_tail=res.stdout.decode(errors='replace')[-600:])
        state['runs'].append(rec)
        (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
        print(json.dumps({k2: rec[k2] for k2 in ('log2', 'shift', 'buffer_ok', 'mismatches', 'fw_ns') if k2 in rec}), flush=True)
        if not rec['buffer_ok']:
            ok_all = False
            break
    print(json.dumps({'passed': ok_all, 'output': str(out)}))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
