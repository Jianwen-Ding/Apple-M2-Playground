#!/usr/bin/env python3
"""IEEE div.rn.f32 (and .rz/.rm/.rp) on AGX: soft restoring division, the native rcp + Newton + Markstein fast
sequence, the hybrid (fast sequence where div_fast_ok, soft elsewhere) and Mesa's rcp * a lowering as a baseline.

Fast sequence (all native fp32, round to nearest):
  y0 = rcp(b); e = fma(-b, y0, 1); y1 = fma(e, y0, y0)      y1 == RN(1/b) for every mantissa (exhaustive, rcp table)
  q0 = a * y1; r = fma(-b, q0, a); q1 = fma(r, y1, q0)       Markstein: correctly rounded when y1 = RN(1/b)
  result = (a == +-0) ? sign(a ^ b) : q1
Each lane computes one quotient of operands from the table. Datasets: 'edge' (edge pairs + exponent-biased randoms),
'fast' (random normal operands drawn inside the fast-path domain, to test the fast sequence there), 'normal' / 'sparse'
(cost data). Offline mode = Rust simulator (the safety gate).
  run_drm_fdiv32.py offline|hardware --op soft|fast|hybrid|mesa [--round MODE] [--data edge|fast|normal|sparse]
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
import softfp32 as S
from run_drm_softfp32 import EDGE

REPO = Path(__file__).resolve().parents[1]
FAST = ['rcp r12, r9', 'fmadd32 r13, r9.neg, r12, 1.0', 'fmadd32 r12, r13, r12, r12',
        'fmul32 r13, r8, r12', 'fmadd32 r14, r9.neg, r13, r8', 'fmadd32 r13, r14, r12, r13']   # q1 in r13


def zero_fix(first):
    """Integer tail: r13 = (a == +-0) ? (a ^ b) & sign : r13."""
    P = S.Prog()
    a, b, q = P.input('a'), P.input('b'), P.input('q')
    az = P.flag('ueq', P.and_(a, 0x7fffffff), 0)
    r = P.sel('ugt', az, 0, P.and_(P.xor(a, b), S.S32), q)
    lines, loc, used = S.emit(P, {'a': 8, 'b': 9, 'q': 13}, [r], first=first)
    return lines + [f'iadd r13, r{loc[r.id]}, 0'], used


def soft_lines(mode, first):
    P = S.Prog()
    a, b = P.input('a'), P.input('b')
    r = S.fdiv32(P, a, b, mode)
    lines, loc, used = S.emit(P, {'a': 8, 'b': 9}, [r], first=first)
    return lines + [f'iadd r13, r{loc[r.id]}, 0'], used


def program(op, mode):
    if op == 'mesa':
        return ['rcp r12, r9', 'fmul32 r13, r8, r12'], 16
    if op == 'soft':
        return soft_lines(mode, 16)
    zl, u1 = zero_fix(16)
    if op == 'fast':
        return FAST + zl, max(16, u1)
    P = S.Prog()
    a, b = P.input('a'), P.input('b')
    ok = S.div_fast_ok(P, a, b)
    chk, loc, u2 = S.emit(P, {'a': 8, 'b': 9}, [ok], first=16)
    soft, u3 = soft_lines('rn', 16)
    L = chk + [f'iadd r15, r{loc[ok.id]}, 0'] + FAST + zl
    if op == 'hybrid3':                         # out-of-line soft path: the common case falls through an untaken jump
        L += ['if_icmp r0l, ueq, r15, 0, 1', ('JANY', 'ool'), ('LABEL', 'ret'), 'pop_exec r0l, 1']
        return L, max(u1, u2, u3), [('LABEL', 'ool')] + soft + [('JANY', 'ret')]
    L += ['if_icmp r0l, ueq, r15, 0, 1', ('JMP', soft), 'pop_exec r0l, 1']
    return L, max(u1, u2, u3)


def build(op, n, mode, chain=1):
    import agx_asm
    pr = program(op, mode)
    one, used = pr[0], pr[1]
    lines, ool = [], []
    for i in range(chain):                     # x = x / b: the quotient (r13) becomes the next numerator (r8)
        rn = lambda l: (l[0], f'{l[1]}{i}') if isinstance(l, tuple) and l[0] in ('LABEL', 'JANY') else l
        lines += [rn(l) for l in one] + ['iadd r8, r13, 0']
        if len(pr) > 2:
            ool += [rn(l) for l in pr[2]]
    if ool:
        lines += [('JANY', 'tail')] + ool + [('LABEL', 'tail')]
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [load(8, 1, True), mov(6, n), e('iadd r7, r1, r6'), load(9, 7, True), e('wait 0'), agx_asm.assemble(lines)]
    ins += [mov(6, 2*n), e('iadd r7, r1, r6'), agx_loop.store(13, 8, 7), e('wait 0'), mov(2, 0)]
    ninstr = agx_asm.count(lines)
    return b''.join(ins), ninstr, used


def dataset(kind, n=0, seed=4):
    rng = random.Random(seed)
    f = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
    if kind == 'edge':
        def rf():
            e = rng.choice([0, 0, 1, 2, 3, rng.randint(0, 254), rng.randint(100, 140), rng.randint(200, 254), rng.randint(40, 60)])
            return (rng.getrandbits(1) << 31) | (e << 23) | rng.getrandbits(23)
        t = [(x, y) for x in EDGE for y in EDGE] + [(rf(), rf()) for _ in range(20000)]
        # quotients near 1 with all-ones / all-zeros mantissa neighbours (the hardest Newton cases)
        for _ in range(2000):
            m = rng.choice([0x7fffff, 0x7ffffe, 0, 1, rng.getrandbits(23)])
            t.append(((127 << 23) | rng.getrandbits(23), (127 << 23) | m))
    elif kind == 'fast':
        t = []
        while len(t) < n:
            ea, eb = rng.randint(48, 254), rng.randint(1, 252)
            if not 2 <= ea-eb+127 <= 252:
                continue
            m = rng.choice([rng.getrandbits(23), 0x7fffff, 0, 1, 0x7ffffe])
            t.append(((rng.getrandbits(1) << 31) | (ea << 23) | rng.getrandbits(23), (rng.getrandbits(1) << 31) | (eb << 23) | m))
    else:
        t = [(f(rng.uniform(-100, 100)), f(rng.uniform(0.999, 1.001)*rng.choice([1, -1]))) for _ in range(n)]
        if kind == 'sparse':
            for i in range(0, n, 32):
                t[i] = (rng.randint(1, 0x7fffff), t[i][1])                 # one subnormal numerator per SIMD group
    while len(t) % 32:
        t.append((0x3f800000, 0x3f800000))
    return t


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--op', default='hybrid', choices=['soft', 'fast', 'hybrid', 'hybrid3', 'mesa'])
    p.add_argument('--round', default='rn', choices=['rn', 'rz', 'rm', 'rp'])
    p.add_argument('--data', default='edge', choices=['edge', 'fast', 'normal', 'sparse'])
    p.add_argument('--lanes', type=int, default=131072)
    p.add_argument('--check', type=int, default=0, help='check only the first N lanes (0 = all)')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--chain', type=int, default=1, help='dependent chain x = x / b of this length (the check follows the chain)')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fdiv32'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    t = dataset(a.data, a.lanes)
    n = len(t)
    base = a.check or n
    prog, ninstr, used = build(a.op, n, a.round, a.chain)
    code = drm.build_main(prog)
    tb = [x for x, _ in t]+[y for _, y in t]+[0xcdcdcdcd]*n
    regs = 2*used+8
    md = a.round if a.op == 'soft' else 'rn'

    def chained(x, y):
        for _ in range(a.chain):
            x = S.ref_div32(x, y, md)
        return x
    exp = [chained(x, y) for x, y in t[:base]]
    print(f'{a.op} {a.round} {a.data}: {n} lanes, {ninstr} instructions, registers up to r{used-1}', flush=True)
    rec = {'op': a.op, 'round': a.round, 'data': a.data, 'chain': a.chain, 'lanes': n, 'checked': base, 'instructions': ninstr, 'runs': []}
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        o, tt = cov.simulate(code, n, 32, regs, 0, tb)
        got = list(tt[2*n:2*n+base])
        bad = sum(g != x for g, x in zip(got, exp))
        print('simulator replay:', base, 'lanes checked,', bad, 'differ from the exact reference')
        rec['sim_out'] = got
        if a.result:
            a.result.write_text(json.dumps(rec)+'\n')
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    for rep in range(a.repeats):
        (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(regs), str(out/'t.bin')],
                           capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        tt = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
        got = list(tt[2*n:2*n+base])
        bad = [i for i in range(base) if got[i] != exp[i]]
        if rep == 0:
            rec['out'] = got
        rec['runs'].append({'rep': rep, 'bad': len(bad), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0],
                            'first_bad': [[t[i][0], t[i][1], got[i], exp[i]] for i in bad[:5]]})
        print('hardware run', rep, 'lanes differing:', len(bad), 'fw_ns', rec['runs'][-1]['fw_ns'], flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
