#!/usr/bin/env python3
"""MP / SB / LB litmus through threadgroup memory between the two SIMD groups of a 64-lane workgroup (safe-10 step 4).
Direct DRM. Straight-line, no loops, no spinning. One `threadgroup_barrier` 0x68 at the start (executed once by every
group) zeroes-and-aligns the groups; after it each lane i (local = i & 63, partner = local ^ 32, the other SIMD group):
  sb   data[local] = 1; [F]; r = data[partner]                    violation: r = 0 on both lanes of a pair
  lb   r = data[partner]; [F]; data[local] = 1                    violation: r = 1 on both lanes of a pair
  mp   data[local] = 1; [F]; flag[local] = 1; then 8 times: flag[partner]; [F]; data[partner]
       violation: flag = 1 with data = 0 (counted per lane in the table)
F: none | wait | f596 | f533 | f59d | mesa_qf | b68 (a full barrier, positive control) | b78 (4-group-block barrier, control).
Barriers are executed by every group at the same point, so nothing can deadlock. Table region 0 = r (sb/lb) or
n_flag_seen (mp), region 1 = mp violation count. Threadgroup memory is declared 32 KiB (Mesa Shared word).
"""
import argparse, json, os, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
from run_drm_opcode_describe import WAIT, get_sr
from run_drm_sync_probe import tg_mem, finish
from run_drm_litmus import FENCES

REPO = Path(__file__).resolve().parents[1]
mov, enc, H = agx_loop.chains.mov_imm, agx_loop.encode, bytes.fromhex
SHARED_32K = 0x4d | 1 << 8 | 0x24 << 10 | (32768 // 256) << 24
GPRS = 80
FS = {'none': b'', 'wait': WAIT, 'b68': H('6800'), 'b78': H('7809')}
SENT = 0xcdcdcdcd


def fb(spec):
    if spec in FS:
        return FS[spec]
    return FENCES[spec] if spec in FENCES else b''.join(FENCES[x] for x in spec.split('+'))


def pieces(kind, fence):
    st = lambda r, i: tg_mem(False, r, i)
    ld = lambda r, i: tg_mem(True, r, i)
    F = fb(fence)
    ins = [get_sr(80, 24), mov(23, 32), mov(22, 63), enc('and r25, r24, r22'), enc('xor r26, r25, r23'),
           mov(21, 64), enc('iadd r27, r25, r21'), enc('iadd r28, r26, r21'), mov(4, 0), mov(5, 1), mov(10, 0), mov(9, 0),
           st(4, 25), st(4, 27), WAIT, H('6800')]                    # zero both slots, align the groups
    if kind == 'sb':
        ins += [st(5, 25), F, ld(6, 26), WAIT]
        res0 = 6
    elif kind == 'lb':
        ins += [ld(6, 26), F, st(5, 25), WAIT]
        res0 = 6
    else:
        ins += [st(5, 25), F, st(5, 27)]
        for _ in range(8):
            ins += [ld(6, 28), F, ld(7, 26), WAIT, enc('and r8, r6, r7'), enc('iadd r9, r9, r6'), enc('iadd r10, r10, r6'), enc('isub r10, r10, r8')]
        res0 = 9
    return ins, res0


def body(kind, fence, total):
    ins, res0 = pieces(kind, fence)
    ins += [mov(20, total), enc('iadd r29, r24, r20'), agx_loop.store(10, 8, 29), agx_loop.store(res0, 8, 24), WAIT]
    ins2 = []
    for i in ins:
        if i[:1] == b'\xf5' and len(i) % 2 == 0:
            ins2 += [i[j:j+2] for j in range(0, len(i), 2)]
        elif i:
            ins2.append(i)
    # applegpu cannot decode 0x78: check the walk with a same-length wait in its place
    DA.decode_lengths(b''.join(WAIT if i == H('7809') else i for i in ins2), [len(i) for i in ins2])
    return b''.join(ins2)+finish()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--total', type=int, default=16384)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--kinds', default='sb,lb,mp')
    p.add_argument('--fences', default='none,wait,f596,f533,f59d,mesa_qf,b68,b78')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/litmus-tg'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    n = a.total
    rec = {'total': n, 'wg': 64, 'results': []}
    for rep in range(a.repeats):
        for kind in a.kinds.split(','):
            for fence in a.fences.split(','):
                code = drm.build_main(body(kind, fence, n))
                (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack('<I', SENT)*(2*n))
                env = {'PATH': '/usr/bin', 'AGX_LOCAL_X': '64', 'AGX_SHARED_WORD': str(SHARED_32K), 'AGX_TABLE_OUT': str(out/'t.out')}
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(GPRS), str(out/'t.bin')],
                                   capture_output=True, timeout=30, env=env)
                smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                    sys.exit(f'dispatch failed for {kind}/{fence}: '+r.stdout.decode()[-300:])
                t = struct.unpack(f'<{2*n}I', (out/'t.out').read_bytes())
                r0, r1 = t[:n], t[n:]
                if kind == 'sb':
                    viol = sum(1 for i in range(n) if i < (i ^ 32) and r0[i] == 0 and r0[i ^ 32] == 0)
                elif kind == 'lb':
                    viol = sum(1 for i in range(n) if i < (i ^ 32) and r0[i] == 1 and r0[i ^ 32] == 1)
                else:
                    viol = sum(r1)
                res = {'rep': rep, 'kind': kind, 'fence': fence, 'violations': viol, 'sum_r0': sum(x for x in r0 if x != SENT),
                       'unset': sum(1 for x in r0 if x == SENT), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}
                rec['results'].append(res)
                print(json.dumps(res), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
