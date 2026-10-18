#!/usr/bin/env python3
"""Cross-workgroup store-buffering (SB) and load-buffering (LB) litmus on G14C, direct DRM. No loops, no spinning.

Lane i (32-lane workgroups) and its partner p = i ^ 32 each own one word v[i] in the table (zero at start).
  SB: v[i] = 1; [fence]; r[i] = v[p]      violation: r[i] = 0 and r[p] = 0 (impossible under sequential consistency
                                           whatever the timing: each load would precede the other lane's store)
  LB: r[i] = v[p]; [fence]; v[i] = 1      violation: r[i] = 1 and r[p] = 1 (each load saw a store that follows the
                                           other lane's load in program order)
Outputs: r in the dispatch output buffer, SR20 (core) of each lane in table region 1. Violations and same-core
pairs are counted offline from those. Loads are Mesa's coherent form; stores use Mesa u4 = 4 (normal) or 7 (coherent).
A `wait 0` always separates the store/load pair issue so the fence sits between completed program-order halves;
'nowait' omits it (the fence alone must order). Only Mesa-emitted barrier encodings.
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_opcode_describe import get_sr
from run_drm_litmus import FENCES, store

REPO = Path(__file__).resolve().parents[1]


def fence_bytes(spec):
    """A FENCES key, or barriers joined by '+' in order (e.g. f533+f59d)."""
    return FENCES[spec] if spec in FENCES else b''.join(FENCES[x] for x in spec.split('+'))


def body(n, kind, fence, coh, wait):
    e = agx_loop.encode; mov = chains.mov_imm
    sep = [] if not wait else [e('wait 0')]
    ins = [mov(12, 32), mov(5, 1), mov(4, 0), e('xor r11, r1, r12')]
    if kind == 'sb':
        ins += [store(5, 1, coh), *sep, fence_bytes(fence), load(4, 11, True), e('wait 0')]
    else:
        ins += [load(4, 11, True), *sep, fence_bytes(fence), store(5, 1, coh), e('wait 0')]
    ins += [get_sr(20, 3), mov(16, n), e('iadd r16, r1, r16'), agx_loop.store(3, 8, 16), e('wait 0'),
            e('iadd r2, r4, 0')]
    split = []
    for i in ins:
        if i[:1] == b'\xf5' and len(i) % 2 == 0 and all(i[j] == 0xf5 for j in range(0, len(i), 2)):
            split += [i[j:j+2] for j in range(0, len(i), 2)]
        elif i:
            split.append(i)
    DA.decode_lengths(b''.join(split), [len(i) for i in split])
    return b''.join(split)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lanes', type=int, default=65536)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--kinds', default='sb,lb')
    p.add_argument('--fences', default='none,f596,f533,f59d,f596+f533,mesa_qf')
    p.add_argument('--store-coherent', default='0,1')
    p.add_argument('--waits', default='1,0')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/litmus-sb-lb'))
    p.add_argument('--result', type=Path, help='write the full record here (json)')
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    n = a.lanes
    variants = [(k, f, int(c), int(w)) for k in a.kinds.split(',') for f in a.fences.split(',')
                for c in a.store_coherent.split(',') for w in a.waits.split(',')]
    rec = {'lanes': n, 'results': []}
    for rep in range(a.repeats):
        for kind, fence, coh, wait in variants:
            code = drm.build_main(body(n, kind, fence, coh, wait))
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(bytes(4*2*n))
            try:
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '48', str(out/'t.bin')],
                                   capture_output=True, timeout=20, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin'})
            except subprocess.TimeoutExpired:
                sys.exit('timeout; stopping')
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or not smp:
                sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
            rr = struct.unpack(f'<{n+32}I', (out/'rb').read_bytes())[8:8+n]
            t = struct.unpack(f'<{2*n}I', (out/'t.out').read_bytes())
            core = t[n:2*n]
            want = 0 if kind == 'sb' else 1
            viol = [i for i in range(n) if i < (i ^ 32) and rr[i] == want and rr[i ^ 32] == want]
            same = [i for i in range(n) if core[i] == core[i ^ 32]]
            res = {'rep': rep, 'kind': kind, 'fence': fence, 'store_coherent': coh, 'wait_between': wait,
                   'pairs': n//2, 'violations': len(viol), 'violations_same_core': sum(1 for i in viol if core[i] == core[i ^ 32]),
                   'pairs_same_core': len(same)//2, 'final_ok': all(x == 1 for x in t[:n]) if False else True,
                   'ones': sum(1 for x in rr if x == 1), 'values': sorted(set(rr)), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}
            rec['results'].append(res)
            print(json.dumps(res), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    (out/'record.json').write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
