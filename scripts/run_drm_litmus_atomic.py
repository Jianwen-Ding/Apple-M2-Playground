#!/usr/bin/env python3
"""Cross-workgroup message passing where the flag is released by a device atomic (safe-10 step 5). No loops.

Same shape as run_drm_litmus.py: lane i writes data[i] = 1, [writer fence], then sets flag[i] by
  store      a coherent store of 1 (control),
  add        device atomic add 1, result unused,
  addret     device atomic add 1 with return (the old value lands in r4; a `wait 0` follows),
  xchg       device atomic exchange with 1 (returns the old value).
The reader (lane i ^ 32, a neighbouring workgroup) loads flag then, after a `wait 0` and an optional fence, data (coherent
loads), 16 times unrolled. n10 = reads with flag = 1 and data = 0 is the MP violation count. Only Mesa-named atomic ops
0 (add) and 2 (xchg) and Mesa-emitted barrier encodings.
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_opcode_describe import get_sr
from run_drm_litmus import FENCES, store

REPO = Path(__file__).resolve().parents[1]
MODES = {'store': None, 'add': (0, False), 'addret': (0, True), 'xchg': (2, True)}


def fence_bytes(spec):
    return FENCES[spec] if spec in FENCES else b''.join(FENCES[x] for x in spec.split('+'))


def body(n, k, wfence, mode, rfence):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(14, n), mov(12, 32), mov(5, 1), mov(9, 0), mov(10, 0),
           e('iadd r15, r1, r14'),
           store(5, 1, True), fence_bytes(wfence)]
    if MODES[mode] is None:
        ins.append(store(5, 15, True))
    else:
        op, ret = MODES[mode]
        ins.append(DA.atomic(op, 4, 15, 5, ret))
        if ret:
            ins.append(e('wait 0'))
    ins += [e('xor r11, r1, r12'), e('iadd r13, r11, r14')]
    for _ in range(k):
        ins += [load(6, 13, True), e('wait 0'), fence_bytes(rfence), load(7, 11, True), e('wait 0'),
                e('and r8, r6, r7'), e('iadd r9, r9, r6'), e('iadd r10, r10, r6'), e('isub r10, r10, r8')]
    ins += [get_sr(20, 3), mov(16, 2*n), e('iadd r16, r1, r16'), agx_loop.store(3, 8, 16),
            mov(17, 3*n), e('iadd r17, r1, r17'), agx_loop.store(10, 8, 17), e('wait 0'), e('iadd r2, r9, 0')]
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
    p.add_argument('--reads', type=int, default=16)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--writer-fences', default='none,f596,f533,mesa_qf')
    p.add_argument('--modes', default='store,add,addret,xchg')
    p.add_argument('--reader-fences', default='f59d,none')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/litmus-atomic'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    n = a.lanes
    variants = [(wf, m, rf) for wf in a.writer_fences.split(',') for m in a.modes.split(',') for rf in a.reader_fences.split(',')]
    rec = {'lanes': n, 'reads': a.reads, 'results': []}
    for rep in range(a.repeats):
        for wf, mode, rf in variants:
            code = drm.build_main(body(n, a.reads, wf, mode, rf))
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(bytes(4*4*n))
            try:
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '48', str(out/'t.bin')],
                                   capture_output=True, timeout=20, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin'})
            except subprocess.TimeoutExpired:
                sys.exit('timeout; stopping')
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or not smp:
                sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
            w = struct.unpack(f'<{n+32}I', (out/'rb').read_bytes())[8:8+n]
            t = struct.unpack(f'<{4*n}I', (out/'t.out').read_bytes())
            core = t[2*n:3*n]; n10 = t[3*n:4*n]
            same = [i for i in range(n) if core[i] == core[i ^ 32]]
            res = {'rep': rep, 'writer_fence': wf, 'flag_mode': mode, 'reader_fence': rf, 'reads_total': n*a.reads,
                   'flag_seen': sum(w), 'mp_violations': sum(n10), 'violations_same_core': sum(n10[i] for i in same),
                   'flags_final': sum(t[n:2*n]), 'data_final_ok': all(x == 1 for x in t[:n]),
                   'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}
            rec['results'].append(res)
            print(json.dumps(res), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
