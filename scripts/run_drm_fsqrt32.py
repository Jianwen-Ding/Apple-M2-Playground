#!/usr/bin/env python3
"""IEEE sqrt.rn.f32 on AGX, exhaustive over [1, 4): every f32 in [1, 4) (2^24 inputs: all mantissas at an even and an odd
exponent; correct rounding of sqrt depends only on these, results scale exactly by 2^k in the normal range) is run on
the GPU and compared with the exact correctly rounded square root (integer isqrt; sqrt has no rounding ties).
Sequences (native fp32 only):
  mesa   : s = x * rsqrt_special(x)                                                    (Mesa's lowering)
  one    : y = rsqrt_special(x); s = x*y; r = fma(-s, s, x); s = fma(r, 0.5*y, s)      (one correction)
  coupled: y = rsqrt_special(x); s = x*y; h = 0.5*y; e = fma(-s, h, 0.5); s = fma(s, e, s); h = fma(h, e, h);
           r = fma(-s, s, x); s = fma(r, h, s)                                         (Markstein-style coupled iteration)
Offline mode replays one 2^16-lane chunk in the Rust simulator (the safety gate) and checks it the same way.
  run_drm_fsqrt32.py offline|hardware --seq mesa|one|coupled [--chunks 16] [--result FILE]
"""
import argparse, json, math, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
BASE = 0x3f800000
CHUNK = 1 << 20
SEQ = {
    'mesa': ['rsqrt_special r12, r8', 'fmul32 r13, r8, r12'],
    'one': ['rsqrt_special r12, r8', 'fmul32 r13, r8, r12', 'fmul32 r14, r12, 0.5', 'fmadd32 r15, r13.neg, r13, r8',
            'fmadd32 r13, r15, r14, r13'],
    'coupled': ['rsqrt_special r12, r8', 'fmul32 r13, r8, r12', 'fmul32 r14, r12, 0.5', 'fmadd32 r15, r13.neg, r14, 0.5',
                'fmadd32 r13, r13, r15, r13', 'fmadd32 r14, r14, r15, r14', 'fmadd32 r15, r13.neg, r13, r8',
                'fmadd32 r13, r15, r14, r13'],
}


def program(seq):
    """Native sequences, or 'soft' (softfp32.fsqrt32) / 'hybrid' (sqrt_fast_ok ? one : soft under if); result in r13."""
    if seq in SEQ:
        return SEQ[seq]
    import softfp32 as S
    P = S.Prog(); a = P.input('a'); r = S.fsqrt32(P, a, 'rn')
    soft, loc, _ = S.emit(P, {'a': 8}, [r], first=16)
    soft = soft + [f'iadd r13, r{loc[r.id]}, 0']
    if seq == 'soft':
        return soft
    P = S.Prog(); a = P.input('a'); ok = S.sqrt_fast_ok(P, a)
    chk, loc, _ = S.emit(P, {'a': 8}, [ok], first=16)
    if seq == 'hybrid3':
        return (chk + [f'iadd r11, r{loc[ok.id]}, 0'] + SEQ['one'] + ['if_icmp r0l, ueq, r11, 0, 1', ('JANY', 'ool'), ('LABEL', 'ret'), 'pop_exec r0l, 1'],
                [('LABEL', 'ool')] + soft + [('JANY', 'ret')])
    return chk + [f'iadd r11, r{loc[ok.id]}, 0'] + SEQ['one'] + ['if_icmp r0l, ueq, r11, 0, 1', ('JMP', soft), 'pop_exec r0l, 1']


def exact_any(x):
    """Correctly rounded (rn) sqrt bits for any f32 (integer arithmetic; sqrt has no ties)."""
    ex, mn, sg = (x >> 23) & 0xff, x & 0x7fffff, x >> 31
    if ex == 255:
        return 0x7fc00000 if mn or sg else 0x7f800000
    if ex == 0 and mn == 0:
        return x
    if sg:
        return 0x7fc00000
    m, e = (mn, -149) if ex == 0 else (mn | 0x800000, ex - 150)      # x = m * 2^e
    if e & 1:
        m <<= 1; e -= 1
    # choose s with N = m << 2s in [2^48, 2^50): q = isqrt(N) in [2^24, 2^25)
    s = (49 - m.bit_length()) // 2 + 1
    while (m << 2*s).bit_length() > 50:
        s -= 1
    while (m << 2*s).bit_length() < 49:
        s += 1
    N = m << 2*s
    q = math.isqrt(N)
    st = q*q != N
    m24, g = q >> 1, q & 1
    m24 += g & (st | (m24 & 1))
    ee = e//2 - s + 1 + 23 + 127                                       # value = m24 * 2^(e/2 - s + 1)
    if m24 >> 24:
        m24 >>= 1; ee += 1
    return (ee << 23) | (m24 & 0x7fffff)


def sweep_inputs(chunk):
    """Chunk c of 16: exponents 16c .. 16c+15, 65,536 mantissas each (stride 128, offset varying with the exponent)."""
    xs = []
    for ex in range(16*chunk, 16*chunk+16):
        off = (ex*37) % 128
        xs += [(ex << 23) | (j*128 + off) for j in range(65536)]
    return xs


def build(seq, n, chain=1):
    import agx_asm
    e = agx_loop.encode; mov = chains.mov_imm
    pr = program(seq)
    one, extra = (pr if isinstance(pr, tuple) else (pr, []))
    lines, ool = [], []
    for i in range(chain):
        rn = lambda l: (l[0], f'{l[1]}{i}') if isinstance(l, tuple) and l[0] in ('LABEL', 'JANY') else l
        lines += [rn(l) for l in one] + ['iadd r8, r13, 0']
        ool += [rn(l) for l in extra]
    if ool:
        lines += [('JANY', 'tail')] + ool + [('LABEL', 'tail')]
    ins = [load(8, 1, True), e('wait 0'), agx_asm.assemble(lines)]
    ins += [mov(6, n), e('iadd r7, r1, r6'), agx_loop.store(13, 8, 7), e('wait 0'), mov(2, 0)]
    return b''.join(ins)


def exact(xbits):
    """Correctly rounded sqrt bits for x in [1, 4)."""
    X = (xbits & 0x7fffff) | 0x800000
    if (xbits >> 23) & 1 == 0:          # exponent 128: x in [2, 4) = X * 2^-22
        X <<= 1
    N = X << 23                          # sqrt(x) * 2^23 = sqrt(X * 2^23) with x = X * 2^-23
    q = math.isqrt(N)
    if N - q*q > q:
        q += 1
    return BASE + (q - (1 << 23))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--seq', default='coupled', choices=sorted(SEQ)+['soft', 'hybrid', 'hybrid3'])
    p.add_argument('--data', default='binades', choices=['binades', 'sweep'], help='binades: every input in [1, 4); sweep: all 256 exponents x 65,536 mantissas')
    p.add_argument('--chunks', type=int, default=16)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fsqrt32'))
    p.add_argument('--result', type=Path)
    p.add_argument('--chain', type=int, default=0, help='cost mode: x = sqrt(x) chained K times over 131,072 lanes of x in [1, 4); output = timings only')
    p.add_argument('--repeats', type=int, default=5)
    a = p.parse_args()
    rec = {'seq': a.seq, 'data': a.data, 'instructions': None, 'by_exponent': {}, 'inputs': 0, 'wrong': 0, 'ulp_hist': {}, 'first_wrong': [], 'chunks': []}

    def tally(xs, outs):
        for x, g in zip(xs, outs):
            w = exact(x) if a.data == 'binades' else exact_any(x)
            rec['inputs'] += 1
            if g != w:
                rec['wrong'] += 1
                k = str((x >> 23) & 0xff)
                rec['by_exponent'][k] = rec['by_exponent'].get(k, 0)+1
                d = str(g - w)
                rec['ulp_hist'][d] = rec['ulp_hist'].get(d, 0)+1
                if len(rec['first_wrong']) < 20:
                    rec['first_wrong'].append([x, g, w])
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        n = 1 << 16
        xs = [BASE + i*256 for i in range(n)] if a.data == 'binades' else [x for c in range(16) for x in sweep_inputs(c)[::256]]
        o, t = cov.simulate(drm.build_main(build(a.seq, n)), n, 32, 80, 0, xs+[0xcdcdcdcd]*n)
        tally(xs, t[n:2*n])
        print(f'simulator {a.seq}: {rec["inputs"]} inputs, {rec["wrong"]} not correctly rounded, hist {rec["ulp_hist"]}')
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    if a.chain:
        n = 131072
        xs = [BASE + (i*127) % (1 << 24) for i in range(n)]
        (out/'c.bin').write_bytes(drm.build_main(build(a.seq, n, a.chain))+bytes(16))
        (out/'t.bin').write_bytes(struct.pack(f'<{2*n}I', *xs, *([0xcdcdcdcd]*n)))
        runs = []
        for rep in range(a.repeats):
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '80', str(out/'t.bin')],
                               capture_output=True, timeout=120, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
            t = struct.unpack(f'<{2*n}I', (out/'t.out').read_bytes())
            want = []
            for x in xs[:256]:
                for _ in range(a.chain):
                    x = exact_any(x)
                want.append(x)
            runs.append({'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'bad': sum(g != w for g, w in zip(t[n:n+256], want)) if a.seq != 'mesa' else None})
            print(a.seq, a.chain, runs[-1], flush=True)
        if a.result:
            a.result.write_text(json.dumps({'seq': a.seq, 'chain': a.chain, 'runs': runs})+'\n')
        return 0
    code = drm.build_main(build(a.seq, CHUNK))
    (out/'c.bin').write_bytes(code+bytes(16))
    for c in range(a.chunks):
        xs = list(range(BASE + c*CHUNK, BASE + (c+1)*CHUNK)) if a.data == 'binades' else sweep_inputs(c)
        (out/'t.bin').write_bytes(struct.pack(f'<{2*CHUNK}I', *xs, *([0xcdcdcdcd]*CHUNK)))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(CHUNK), str(out/'rb'), '1', '80', str(out/'t.bin')],
                           capture_output=True, timeout=120, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        t = struct.unpack(f'<{2*CHUNK}I', (out/'t.out').read_bytes())
        before = rec['wrong']
        tally(xs, t[CHUNK:])
        rec['chunks'].append({'chunk': c, 'wrong': rec['wrong']-before, 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]})
        print(f'chunk {c}: wrong {rec["wrong"]-before}', flush=True)
    print(f'hardware {a.seq}: {rec["inputs"]} inputs, {rec["wrong"]} not correctly rounded, hist {rec["ulp_hist"]}')
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
