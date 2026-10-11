#!/usr/bin/env python3
"""Message-passing stress test: threadgroup_barrier 0x68 versus 0x78 (direct DRM).

Each workgroup has G SIMD groups (64..256 lanes), and the dispatch has many workgroups.
Every iteration k of a counted loop:

    each lane writes 8 values  v = (k+1)<<16 | local*16 | j  (no wait)
    [pre-sequence: none | wait | memory_barrier | wait+memory_barrier]   (Mesa: stores, wait, memory_barrier, barrier)
    BARRIER A (candidate)
    read the 8 values of lane (local+32) mod n (another SIMD group), wait,
    count every mismatch against the expected value
    BARRIER B (candidate)  (stops the next iteration's writes racing these reads)

Every SIMD group executes both barriers in every iteration with uniform control flow, so a
barrier cannot deadlock. The negative control uses `wait 0` as the "barrier" and must show
mismatches; the Mesa sequence with 0x68 must show none. Each lane reports its mismatch
count and the OR of all (read XOR expected).

Memory: `tg` = threadgroup memory (USC Shared declares 32 KiB; 8 KiB used, see SHARED_32K), `dev` = device memory (table).
Refuses the faulting opcodes; stops at the first fault; CONFIRM_GPU_FAULTS=1.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

import agx_loop
import run_drm_compute as drm
from run_drm_opcode_describe import WAIT, get_sr
from run_drm_sync_probe import tg_mem, finish, decodes

REPO = Path(__file__).resolve().parents[1]
SENT = 0xcdcdcdcd
mov, enc, H = agx_loop.chains.mov_imm, agx_loop.encode, bytes.fromhex
BARRIERS = {'68': H('6800'), '78': H('7809'), 'wait': WAIT}
PRE = {'none': b'', 'wait': WAIT, 'mb': H('f596'), 'wait+mb': WAIT+H('f596')}
# Usable threadgroup memory measured at 1/4 of the declared bytes (8 KiB -> 2 KiB), so declare 32 KiB for 8 KiB used.
SHARED_32K = 0x4d | 1 << 8 | 0x24 << 10 | (32768 // 256) << 24
SHARED_64K = 0x4d | 1 << 8 | 0x24 << 10                          # bytes field 0 = 65536 (Mesa agx_usc_shared_none)
GPRS = 80   # 16-bit halves; the body uses r0..r31


def body(mem, barrier, pre, n, trips, total, dist=1):
    """n = workgroup size (power of two, 64..256); total = dispatch size."""
    st = (lambda r, i: tg_mem(False, r, i)) if mem == 'tg' else (lambda r, i: agx_loop.store(r, 8, i))
    ld = (lambda r, i: tg_mem(True, r, i)) if mem == 'tg' else (lambda r, i: enc(f'device_load 0, i32, x, r{r}, u8_u9, r{i}, unsigned'))
    b = get_sr(80, 24)+mov(18, n-1)+enc('and r25, r24, r18')+enc(f'iadd r26, r25, {32*dist}')+enc('and r26, r26, r18')
    b += mov(14, 16)+mov(19, 8)+mov(17, 65536)+mov(27, 0)+mov(31, 0)+mov(23, 0)
    b += enc('imadd r20, r25, r14, r27')+enc('imadd r21, r26, r14, r27')      # local*16, partner*16
    if mem == 'tg':
        b += enc('imadd r28, r25, r19, r27')+enc('imadd r30, r26, r19, r27')  # slot bases: local*8, partner*8
    else:
        b += enc('imadd r28, r24, r19, r27')                                    # writer: gid*8
        # partner gid = gid - local + partner_local ; reader base = partner_gid*8
        b += mov(22, 0xffffffff)+enc('imadd r29, r25, r22, r24')+enc('iadd r29, r29, r26')+enc('imadd r30, r29, r19, r27')
    b += mov(3, 0)+mov(4, trips)+enc('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    loop = enc('iadd r27, r27, r17')+enc('iadd r15, r27, r20')+enc('iadd r16, r27, r21')
    for j in range(8):
        loop += enc(f'iadd r13, r15, {j}')+enc(f'iadd r29, r28, {j}')+st(13, 29)
    loop += PRE[pre]+BARRIERS[barrier]
    for j in range(8):
        loop += enc(f'iadd r29, r30, {j}')+ld(5+j, 29)
    loop += WAIT
    for j in range(8):
        loop += enc(f'iadd r13, r16, {j}')+enc(f'xor r22, r{5+j}, r13')+enc('or r23, r23, r22')
        loop += enc('icmpsel ugt, r22, r22, 0, 1, 0')+enc('iadd r31, r31, r22')
    loop += BARRIERS[barrier]
    loop += enc('iadd r3, 1, r3.sx')+enc('while_icmp r0l, ult, r3, r4, 1')
    b += loop+enc(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}')+enc('pop_exec r0l, 1')+WAIT
    # results after the data region (dev: total*8 words): count[gid], or-mask[gid]
    res = 8*total if mem == 'dev' else 0
    b += mov(22, res)+enc('iadd r29, r24, r22')+agx_loop.store(31, 8, 29)
    b += mov(22, res+total)+enc('iadd r29, r24, r22')+agx_loop.store(23, 8, 29)+WAIT
    return b+finish()


def gate():
    """Emulate the loop skeleton (memory ops and barriers replaced by same-length waits) for trip count/exec."""
    b = body('tg', 'wait', 'none', 64, 5, 64)
    _, g = agx_loop._tools()
    out, i = b'', 0
    while i < len(b):
        n = g.opcode_to_number(b[i:]); d = g.get_instruction_descriptor(n); s = d.decode_size(n)
        out += WAIT*(s//2) if d.name in ('threadgroup_store', 'threadgroup_load', 'device_store', 'device_load', 'get_sr') else b[i:i+s]
        i += s
    st = g.CoreState(num_registers=32, uniforms=g.Uniforms())
    for t in range(32):
        st.set_reg16(0, t, 0); st.set_reg32(24, t, t)   # get_sr r24 (gid) is replaced by waits: preset it
    st.exec = [True]*32
    pc, jumps, steps = 0, 0, 0
    while pc < len(out) and steps < 100000:
        n = g.opcode_to_number(out[pc:]); d = g.get_instruction_descriptor(n); s = d.decode_size(n)
        n &= (1 << (8*s))-1
        if d.name == 'jmp_exec_any':
            off = dict(d.decode_fields(n))['off']; off = off-(1 << 32) if off & (1 << 31) else off
            if any(st.exec): pc += off; jumps += 1
            else: pc += s
        else:
            d.exec(n, st); pc += s
        steps += 1
    # with every load/store replaced by a wait, r5..r12 stay 0, so each lane counts 8 mismatches per trip
    return (jumps == 4 and st.exec == [True]*32 and pc == len(out)
            and [st.get_reg32(31, t) for t in range(32)] == [8*5]*32
            and [st.get_reg32(26, t) for t in range(32)] == [(t+32) & 63 for t in range(32)])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--names', default='.*')
    p.add_argument('--dist', type=int, default=1, help='partner = local + 32*dist (mod n): SIMD groups apart')
    p.add_argument('--sizes', default='64,128,256', help='workgroup sizes (powers of two)')
    p.add_argument('--trips', type=int, default=2000)
    p.add_argument('--total', type=int, default=16384, help='threads per dispatch')
    p.add_argument('--repeats', type=int, default=3, help='submissions per job')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--timeout', type=int, default=60)
    p.add_argument('--output', type=Path)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if not gate(): sys.exit('emulator gate failed')
    jobs = []
    for mem in ('tg', 'dev'):
        for n in [int(x) for x in a.sizes.split(',')]:
            for bar in ('wait', '68', '78'):
                for pre in (('none',) if bar == 'wait' else ('none', 'wait', 'mb', 'wait+mb')):
                    name = f'{mem}-n{n}-{bar}-{pre}'
                    if not re.fullmatch(a.names, name): continue
                    if mem == 'tg' and n > 512: continue   # 8 KiB used per 256 lanes; 4x declared would exceed the field
                    bb = body(mem, bar, pre, n, a.trips, a.total, a.dist)
                    decodes(bb, {BARRIERS['78']})
                    env = {'AGX_LOCAL_X': str(n)}
                    if mem == 'tg': env['AGX_SHARED_WORD'] = str(SHARED_32K if n <= 256 else SHARED_64K)
                    words = (8*a.total if mem == 'dev' else 0)+2*a.total
                    jobs.append(dict(name=name, body=bb, env=env, words=words))
    print(json.dumps({'jobs': len(jobs), 'dry_run': a.dry_run}), flush=True)
    if a.dry_run: return 0
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1': sys.exit('refusing to run without CONFIRM_GPU_FAULTS=1')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/barrier-stress')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode: sys.exit('build failed')
    state = {'utc': stamp, 'dist': a.dist, 'sizes': a.sizes, 'trips': a.trips, 'total': a.total, 'repeats': a.repeats, 'gprs': GPRS, 'results': [], 'complete': False}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')

    def run(jb):
        (out/'code.bin').write_bytes(drm.build_main(jb['body'])+bytes(16))
        (out/'table.bin').write_bytes(struct.pack('<I', SENT)*jb['words'])
        env = dict(os.environ, **jb['env'], AGX_TABLE_OUT=str(out/'table.out'))
        rec = {'name': jb['name']}
        try:
            res = subprocess.run([str(exe), a.device, str(out/'code.bin'), str(a.total), str(out/'rb'), str(a.repeats), str(GPRS), str(out/'table.bin')],
                                 capture_output=True, timeout=a.timeout, env=env)
            smp = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{"rep"')]
            rec['fw_ns'] = [e['fw_ts'][1]-e['fw_ts'][0] for e in smp]
            ok = res.returncode == 0 and len(smp) == a.repeats and all(e['fw_ts'][0] and e['fw_ts'][1] for e in smp)
            if ok:
                rounded = (a.total+31)//32*32
                w = struct.unpack(f'<{rounded+32}I', (out/'rb').read_bytes())
                ok &= all(v == SENT for v in w[:8]) and list(w[rounded+16:]) == [0xa5a50000+j for j in range(16)]
                rec['suffix_lanes'] = sum(v == 0x12345678 for v in w[8:8+a.total])
                t = struct.unpack(f"<{jb['words']}I", (out/'table.out').read_bytes())
                base = 8*a.total if jb['name'].startswith('dev') else 0
                cnt, orm = t[base:base+a.total], t[base+a.total:base+2*a.total]
                # the table persists across repeats in one process: counts are from the LAST submission only
                rec['mismatches'] = sum(cnt); rec['lanes_with_errors'] = sum(c > 0 for c in cnt)
                rec['or_mask'] = hex(0 if not orm else __import__('functools').reduce(lambda x, y: x | y, orm))
                rec['max_lane_count'] = max(cnt)
                n = int(jb['name'].split('-')[1][1:])
                # lanes with errors per reading SIMD group (local // 32); reader g reads group (g+1) mod G
                rec['err_lanes_by_group'] = [sum(1 for i, c in enumerate(cnt) if c and (i % n)//32 == g) for g in range(n//32)]
            rec['fault'] = not ok
        except subprocess.TimeoutExpired:
            rec['fault'] = True; rec['timed_out'] = True
        return rec

    try:
        for jb in jobs:
            rec = run(jb); state['results'].append(rec); save()
            print(json.dumps({k: rec.get(k) for k in ('name', 'fault', 'mismatches', 'lanes_with_errors', 'or_mask', 'suffix_lanes')}
                             | {'fw_ms': [round(x/1e6, 2) for x in rec.get('fw_ns', [])]}), flush=True)
            if rec['fault']: raise RuntimeError(f"fault on {rec['name']}")
        state['complete'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save()
        print(json.dumps({'complete': state['complete'], 'n': len(state['results']), 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
