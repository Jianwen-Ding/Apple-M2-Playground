#!/usr/bin/env python3
"""Do stores of dispatch k reach the cached loads of dispatch k+1? (safe-10 step 7). Bounded, no loops, no spinning.

`drm_compute` submits the same program R times (one dispatch per SUBMIT, in order) over one persistent table.
Lane i (32-lane workgroups; partner p = i ^ 32, usually another workgroup and often another core) runs:
    c  = coherent load of its own counter v[i]     (authoritative: counts the dispatches that completed)
    pc = load of the partner's counter v[p]        (Mesa u4 = 4 cached, or coherent; optional f59d invalidate before it)
    v[i] = c + 1                                   (store with Mesa u4 = 4 or 7)
    stale += (pc < c)
pc may equal c + 1 (the partner already stored in this dispatch), never legitimately less than c. After R dispatches
v[i] must be R for every lane and `stale` counts the cached loads that returned a value older than the previous dispatch.
Table: words 0..n-1 counters (start 0), n..2n-1 stale counts, 2n..3n-1 SR20 core of the last dispatch.
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_opcode_describe import get_sr
from run_drm_litmus import FENCES, store

REPO = Path(__file__).resolve().parents[1]


def body(n, load_coh, store_coh, inval):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(12, 32), mov(21, 1), mov(22, 0), mov(23, n), mov(24, 2*n),
           e('xor r11, r1, r12'),
           load(4, 1, True), e('wait 0'),                      # c  (coherent)
           FENCES['f59d'] if inval else b'',
           load(6, 11, load_coh), e('wait 0'),                 # pc (partner)
           e('iadd r5, r4, 1'), store(5, 1, store_coh),        # v[i] = c + 1
           e('icmpsel ult, r20, r6, r4, r21, r22'),            # stale flag = pc < c
           e('iadd r16, r1, r23'), load(25, 16, True), e('wait 0'), e('iadd r25, r25, r20'), agx_loop.store(25, 8, 16),
           get_sr(20, 3), e('iadd r17, r1, r24'), agx_loop.store(3, 8, 17), e('wait 0'),
           e('iadd r2, r4, 0')]
    split = []
    for i in ins:
        if i[:1] == b'\xf5' and len(i) % 2 == 0:
            split += [i[j:j+2] for j in range(0, len(i), 2)]
        elif i:
            split.append(i)
    DA.decode_lengths(b''.join(split), [len(i) for i in split])
    return b''.join(split)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lanes', type=int, default=65536)
    p.add_argument('--dispatches', type=int, default=16)
    p.add_argument('--repeats', type=int, default=3, help='independent process runs per variant')
    p.add_argument('--loads', default='cached,coherent')
    p.add_argument('--stores', default='normal,coherent')
    p.add_argument('--invalidate', default='0,1')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/dispatch-visibility'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    n = a.lanes
    rec = {'lanes': n, 'dispatches': a.dispatches, 'results': []}
    for rep in range(a.repeats):
        for lc in a.loads.split(','):
            for sc in a.stores.split(','):
                for inv in map(int, a.invalidate.split(',')):
                    code = drm.build_main(body(n, lc == 'coherent', sc == 'coherent', inv))
                    (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(bytes(4*3*n))
                    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), str(a.dispatches), '64', str(out/'t.bin')],
                                       capture_output=True, timeout=60, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin'})
                    smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                    if r.returncode or len(smp) != a.dispatches:
                        sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
                    t = struct.unpack(f'<{3*n}I', (out/'t.out').read_bytes())
                    stale = t[n:2*n]
                    res = {'rep': rep, 'load': lc, 'store': sc, 'invalidate': inv, 'dispatches': a.dispatches,
                           'counters_ok': all(x == a.dispatches for x in t[:n]), 'stale_loads': sum(stale),
                           'lanes_with_stale': sum(1 for x in stale if x), 'max_stale_per_lane': max(stale),
                           'fw_ns': [s['fw_ts'][1]-s['fw_ts'][0] for s in smp]}
                    rec['results'].append(res)
                    print(json.dumps(res), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
