#!/usr/bin/env python3
"""fp16 compare semantics: fcmpsel on 16-bit halves over edge-value pairs (safe-01 part 3). Direct DRM, no loops.

Lane i of an n = len(VALS16)^2 dispatch compares A = vals[i // M] with B = vals[i % M] (half
bit patterns in the low half of the loaded word, upper half zero):
`fcmpsel CC, r20l, r6l, r7l, r21l, r22l` with r21 = 1, r22 = 0 and r20 pre-zeroed, so the result
word is exactly 1 when the condition holds. vals: +-0, subnormal halves, the smallest normals,
near 1 and 2, max finite, +-inf and seven NaNs. Conditions: eq lt gt ltn gte lte gtn.
The rXl fcmpsel form is recorded safe in the coverage catalog; only the cc field changes.
Host oracle: exact IEEE from struct '<e' (half->float is exact) with bit-pattern NaN checks.
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
CONDS = ['eq', 'lt', 'gt', 'ltn', 'gte', 'lte', 'gtn']
VALS16 = [0x0000, 0x8000,
          0x0001, 0x0002, 0x0010, 0x0100, 0x0200, 0x03ff, 0x8001, 0x83ff,
          0x0400, 0x8400,
          0x1000, 0x2000, 0x3800, 0x3bff, 0x3c00, 0x3c01, 0x4000, 0xbc00,
          0x7bff, 0xfbff, 0x7c00, 0xfc00,
          0x7e00, 0xfe00, 0x7c01, 0xfc01, 0x7e12, 0x7fff, 0xffff]
M = len(VALS16)


def h16(b):
    return struct.unpack('<e', struct.pack('<H', b))[0]


def isnh(b):
    return (b & 0x7c00) == 0x7c00 and (b & 0x03ff)


def ieee(cond, a, b):
    na, nb = isnh(a), isnh(b)
    if cond in ('ltn', 'gtn'):
        if na and nb:
            return 0
        if nb:
            return 1
        if na:
            return 0
    elif na or nb:
        return 0
    x, y = h16(a), h16(b)
    return int({'eq': x == y, 'lt': x < y, 'gt': x > y, 'ltn': x < y,
                'gte': x >= y, 'lte': x <= y, 'gtn': x > y}[cond])


def body(cond, n):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(12, n), mov(20, 0), mov(21, 1), mov(22, 0), e('iadd r13, r1, r12'),
           load(6, 1, True), load(7, 13, True), e('wait 0'),
           e(f'fcmpsel {cond}, r20l, r6l, r7l, r21l, r22l'),
           mov(14, 2*n), e('iadd r15, r1, r14'), agx_loop.store(20, 8, 15), e('wait 0'), e('iadd r2, r20, 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fcmp16'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    n = M*M
    A = [VALS16[i//M] for i in range(n)]; B = [VALS16[i % M] for i in range(n)]
    table = A+B+[0xcdcdcdcd]*n
    want = {c: [ieee(c, x, y) for x, y in zip(A, B)] for c in CONDS}
    if a.mode == 'offline':
        for cond in CONDS:
            body(cond, n)
        assert all(v in (0, 1) for vs in want.values() for v in vs)
        assert M == 31, M
        print(f'gated: all 7 f16 bodies decode; host oracle has exact subnormal ordering')
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'vals': VALS16, 'conds': CONDS, 'results': []}
    for rep in range(a.repeats):
        for cond in CONDS:
            code = drm.build_main(body(cond, n))
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{3*n}I', *table))
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '48', str(out/'t.bin')],
                               capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                sys.exit(f'dispatch failed for {cond}: '+r.stdout.decode()[-300:])
            t = struct.unpack(f'<{3*n}I', (out/'t.out').read_bytes())
            res = {'rep': rep, 'cond': cond, 'out': list(t[2*n:]), 'inputs_intact': list(t[:n]) == A and list(t[n:2*n]) == B}
            rec['results'].append(res)
            match = sum(1 for g, w in zip(res['out'], want[cond]) if g == w)
            print(cond, rep, f'{match}/{n} exact vs IEEE', res['inputs_intact'], flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
