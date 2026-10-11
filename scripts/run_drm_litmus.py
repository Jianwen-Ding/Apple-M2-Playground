#!/usr/bin/env python3
"""Cross-workgroup message-passing litmus (MP) on G14C, direct DRM. No loops, no spinning.

Every lane i (32-lane workgroups) writes data[i] = 1, then [writer fence], then
flag[i] = 1. It then reads, K times unrolled, the pair of lane i ^ 32 (the
neighbouring workgroup): [invalidate] flag, [reader fence], data. Counts:
  n1  = reads that saw flag = 1 (the message became visible at all)
  n10 = reads that saw flag = 1 but data = 0 (MP violation: reordering or staleness)
Output r2 = n1; table region 2 = SR20 (core) of each lane, region 3 = n10.

Variants: writer fence (none / memory_barrier f596 / Mesa's queue-family sequence),
store cache policy (Mesa u4 = 4 normal or 7 coherent), reader invalidate before each
flag load (device_barrier_1 f59d or none), reader fence between the two loads (f59d
or none, both after a wait; 'nowait' issues both loads before one wait). Loads are always Mesa's coherent form. Only Mesa-emitted encodings.
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_opcode_describe import get_sr

REPO = Path(__file__).resolve().parents[1]
H = bytes.fromhex
FENCES = {'none': b'', 'f596': H('f596'), 'mesa_qf': H('f596f533f59af59ef503f599f59d'), 'f59d': H('f59d')}
for _h in ('f533', 'f59a', 'f59e', 'f503', 'f599'):
    FENCES[_h] = H(_h)
for _h in ('f533', 'f59a', 'f59e', 'f503', 'f599', 'f59d'):
    FENCES['f596+'+_h] = H('f596'+_h)


def store(reg, idx_reg, coherent):
    b = agx_loop.store(reg, 8, idx_reg)
    x = int.from_bytes(b, 'little')
    if coherent: x = (x & ~(7 << 44)) | 7 << 44     # Mesa agx_pack.c: u4 = coherent ? 7 : 4 (loads and stores)
    return x.to_bytes(8, 'little')


def body(n, k, wfence, wcoh, rinv, rfence):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(14, n), mov(12, 32), mov(5, 1), mov(9, 0), mov(10, 0),
           e('iadd r15, r1, r14'),                      # flag index of own slot
           store(5, 1, wcoh), FENCES[wfence], store(5, 15, wcoh),
           e('xor r11, r1, r12'), e('iadd r13, r11, r14')]   # partner data / flag index
    for _ in range(k):
        mid = [] if rfence == 'nowait' else [e('wait 0'), FENCES[rfence]]
        ins += [FENCES['f59d'] if rinv else b'', load(6, 13, True), *mid, load(7, 11, True), e('wait 0'),
                e('and r8, r6, r7'), e('iadd r9, r9, r6'), e('iadd r10, r10, r6'), e('isub r10, r10, r8')]
    ins += [get_sr(20, 3), mov(16, 2*n), e('iadd r16, r1, r16'), agx_loop.store(3, 8, 16),     # core -> region 2
            mov(17, 3*n), e('iadd r17, r1, r17'), agx_loop.store(10, 8, 17), e('wait 0'),      # n10 -> region 3
            e('iadd r2, r9, 0')]                                                              # output = n1
    split = []
    for i in ins:     # fences are runs of 2-byte barriers: list each one for the length check
        if i[:1] == b'\xf5' and len(i) % 2 == 0 and all(i[j] == 0xf5 for j in range(0, len(i), 2)):
            split += [i[j:j+2] for j in range(0, len(i), 2)]
        elif i: split.append(i)
    ins = split
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lanes', type=int, default=65536)
    p.add_argument('--reads', type=int, default=16)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--writer-fences', help='comma list of writer fences (default: none,f596,mesa_qf)')
    p.add_argument('--reader', default='all', help="'all' or rinv,rfence e.g. 1,none")
    p.add_argument('--store-coherent', default='0,1')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/litmus'))
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    n = a.lanes
    wfs = a.writer_fences.split(',') if a.writer_fences else ['none', 'f596', 'mesa_qf']
    readers = [(ri, rf) for ri in (1, 0) for rf in ('none', 'f59d')] if a.reader == 'all' else [(int(a.reader.split(',')[0]), a.reader.split(',')[1])]
    variants = [(wf, wc, ri, rf) for wf in wfs for wc in map(int, a.store_coherent.split(',')) for ri, rf in readers]
    rec = {'lanes': n, 'reads': a.reads, 'results': []}
    for rep in range(a.repeats):
        for wf, wc, ri, rf in variants:
            code = drm.build_main(body(n, a.reads, wf, wc, ri, rf))
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(bytes(4*4*n))
            try:
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '48', str(out/'t.bin')],
                                   capture_output=True, timeout=20, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin'})
            except subprocess.TimeoutExpired:
                sys.exit('timeout; stopping')
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or not smp: sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
            w = struct.unpack(f'<{n+32}I', (out/'rb').read_bytes())[8:8+n]
            t = struct.unpack(f'<{4*n}I', (out/'t.out').read_bytes())
            core = t[2*n:3*n]
            n1 = list(w); n10 = list(t[3*n:4*n])
            same = [i for i in range(n) if core[i] == core[i ^ 32]]
            res = {'rep': rep, 'writer_fence': wf, 'store_coherent': wc, 'reader_invalidate': ri, 'reader_fence': rf,
                   'reads_total': n*a.reads, 'flag_seen': sum(n1), 'mp_violations': sum(n10),
                   'violations_same_core': sum(n10[i] for i in same), 'flag_seen_same_core': sum(n1[i] for i in same),
                   'pairs_same_core': len(same), 'final_data_ok': all(x == 1 for x in t[:2*n]), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}
            rec['results'].append(res)
            print(json.dumps(res), flush=True)
    (out/'record.json').write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
