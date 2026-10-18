#!/usr/bin/env python3
"""fp32 compare semantics: fcmpsel with every named condition over edge-value pairs (safe-01 part 3). Direct DRM, no loops.

Lane i of an n = 48 x 48 dispatch compares A = vals[i // 48] with B = vals[i % 48] (raw fp32 bit patterns loaded from the
table): `fcmpsel CC, r20, r6, r7, r21, r22` with r21 = 1, r22 = 0, so the result word is 1 when the condition holds.
vals: +-0, subnormals (including the smallest, the largest and mid ones), the smallest normals, near 1, 2, max finite, +-inf
and eight NaNs (quiet / signalling / payloads, both signs). Conditions: eq lt gt ltn gte lte gtn.
Only encodings already recorded safe (the cc field changes among Mesa-named values).
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
CONDS = ['eq', 'lt', 'gt', 'ltn', 'gte', 'lte', 'gtn']      # fcmpsel has no negation field (the assembler refuses neq etc.)
BASES = [0x0, 0x1, 0x2, 0x10, 0x100, 0x1000, 0x100000, 0x200000, 0x400000, 0x7fffff, 0x800000, 0x800001, 0x3e800000,
         0x3f7fffff, 0x3f800000, 0x3f800001, 0x40000000, 0x41200000, 0x7f7fffff, 0x7f800000]
NANS = [0x7fc00000, 0xffc00000, 0x7f800001, 0xff800001, 0x7fc12345, 0x7fffffff, 0xffffffff, 0xffc12345]
VALS = [b for b in BASES] + [b | 0x80000000 for b in BASES if b] + NANS     # -0 included once via 0x80000000 below
VALS = [v for v in VALS]
VALS.insert(20, 0x80000000)
N = len(VALS)


def body(cond, n):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(12, n), mov(21, 1), mov(22, 0), e('iadd r13, r1, r12'),                 # B/A index bases: A at r1, B at n + r1
           load(6, 1, True), load(7, 13, True), e('wait 0'),
           e(f'fcmpsel {cond}, r20, r6, r7, r21, r22'),
           mov(14, 2*n), e('iadd r15, r1, r14'), agx_loop.store(20, 8, 15), e('wait 0'), e('iadd r2, r20, 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fcmp'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    assert N == 48, N
    n = N*N
    A = [VALS[i//N] for i in range(n)]; B = [VALS[i % N] for i in range(n)]
    table = A+B+[0xcdcdcdcd]*n
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        for cond in ('eq', 'lt', 'gt'):     # the simulator models these; the others differ only in the cc / invert bits
            out, tab = cov.simulate(drm.build_main(body(cond, n)), n, 32, 48, 0, table)
            assert all(x in (0, 1) for x in tab[2*n:]), cond
        print('gated: eq/lt/gt programs run in agx_run; other conditions differ only in the cc bits')
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'vals': VALS, 'conds': CONDS, 'results': []}
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
            print(cond, rep, sum(res['out']), res['inputs_intact'], flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
