#!/usr/bin/env python3
"""Software fp64 (softfp64.py) on AGX: check bit-exactness against IEEE doubles and measure cost (safe-gap: fp64).

Each lane computes one double operation on operands from the table (hi/lo words) and stores hi/lo words. Operands: all
pairs of ~48 edge doubles (+-0, subnormals, smallest/largest normals, near 1, max finite, +-inf, NaN) plus random doubles
across the whole exponent range. Expected results come from the host's IEEE binary64 (round to nearest even); a NaN
result matches any NaN. Offline mode replays the generated program in the Rust simulator; hardware mode runs it on the GPU.
  run_drm_softfp64.py offline|hardware --op mul|add [--random N]
"""
import argparse, json, math, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
import softfp64 as S

REPO = Path(__file__).resolve().parents[1]
EDGE = [0.0, -0.0, 5e-324, -5e-324, 1e-310, -1e-310, 2.2250738585072009e-308, 2.2250738585072014e-308, -2.2250738585072014e-308,
        4.4501477170144028e-308, 1.0, -1.0, 1.0000000000000002, 0.9999999999999999, 1.5, 2.0, 3.0, 0.5, 0.1, 0.3, 1e-300, 1e300,
        1e154, 1e-154, 3.14159, 2.718281828459045, 1.7976931348623157e308, -1.7976931348623157e308, 8.98846567431158e307,
        float('inf'), -float('inf'), float('nan'), 2**-1022, 2**-1023, 2**-1074*3, 2**-1074*2**20, 2**-1074*(2**52-1), 2**52, 2**53,
        2**53+2, 4503599627370497.5, 1e16, 1e-16, 7.0, -7.5, 1.0e-5, 123456789.123, 6.02214076e23]
EDGE = [float(x) for x in EDGE]      # some entries are written as ints: the host reference must round in binary64 at every step
assert len(EDGE) == 48, len(EDGE)
OPS = {'mul': (2, S.fmul64), 'add': (2, S.fadd64), 'fma': (3, S.ffma64),
       'div': (2, S.fdiv64), 'sqrt': (1, S.fsqrt64), 'rcp': (1, S.frcp64)}
OPS.update(('c_'+n, (2, getattr(S, 'fcmp_'+n))) for n in S.FCMP_OPS)
MODES = {'div': ['rn', 'rz', 'rm', 'rp'], 'sqrt': ['rn', 'rz', 'rm', 'rp'], 'rcp': ['rn', 'rz', 'rm', 'rp']}
# edge operands beyond EDGE x EDGE: exact ties, near-1 quotients, over/underflow boundaries
DIV_EXTRA = [(2.0**53+1, 2.0**53), (2.0**53+3, 2.0**53), (1.0, 3.0), (2.0, 3.0), (1e16, 10.0),
             (0.30000000000000004, 0.1), (7.0, 3.0), (1.0, 10.0), (123456789.123, 0.1),
             (1.7976931348623157e308, 0.9999999999999999), (1.7976931348623157e308, 1.5),
             (5e-324, 3.0), (2.2250738585072014e-308, 1.5), (2.2250738585072014e-308, 0.5)]
SQRT_EDGE = [0.0, -0.0, 1.0, 4.0, 9.0, 2.0, 3.0, 0.25, 2.25, 1.5, -1.0, -4.0, -1e300,
             1e300, 1e-300, 5e-324, 1.7976931348623157e308, float('inf'), float('-inf'),
             2.0**52, (1+2**-26)**2, (1+2**-27)**2, 0.1, 123456789.123]
# baselines for the cost comparison (no IEEE check): 'null' returns the first operand, 'f32fma' is one native fmadd32
RAW = {'null': (3, []), 'f32fma': (3, ['fmadd32 r20, r8, r10, r12'])}


def rnd(rng):
    k = rng.random()
    if k < 0.3:
        return struct.unpack('<d', struct.pack('<Q', rng.getrandbits(64)))[0]
    e = rng.randint(-1074, 1023)
    return math.ldexp(rng.random()+0.5, e) * rng.choice([1, -1])


def dataset(nrand, op='mul', seed=1):
    """Tuples of operands (2 for mul/add/div, 3 for fma, 1 for sqrt/rcp)."""
    rng = random.Random(seed)
    if op == 'fma':
        sub = EDGE[:2]+EDGE[2:4]+EDGE[4:6]+EDGE[8:10]+EDGE[10:13]+EDGE[13:14]+EDGE[18:19]+EDGE[27:32]+EDGE[34:36]
        sub = sub[:24]
        tuples = [(x, y, z) for x in sub for y in sub for z in sub]
    elif op in ('sqrt', 'rcp'):
        tuples = [(x,) for x in SQRT_EDGE]
    else:
        tuples = [(x, y) for x in EDGE for y in EDGE]
    if op == 'div':
        tuples += DIV_EXTRA
    k = len(tuples[0])
    for _ in range(nrand):
        if op == 'sqrt':
            tuples.append((abs(rnd(rng)),))
        else:
            tuples.append(tuple(rnd(rng) for _ in range(k)))
    # near-cancellation and near-equal exponents: the addend (or second operand) nearly cancels the rest
    for _ in range(nrand // 2):
        x = rnd(rng)
        if k == 1:
            continue  # 1-operand ops use their edge lists plus uniform randoms
        if k == 2:
            if op == 'div':
                tuples.append((x, x*(1+rng.choice([1, -1])*2.0**-rng.randint(1, 60))))
            else:
                tuples.append((x, -x*(1+rng.choice([1, -1])*2.0**-rng.randint(1, 60))))
        else:
            y = rnd(rng)
            try:
                z = -x*y*(1+rng.choice([1, -1])*2.0**-rng.randint(1, 110))
            except OverflowError:
                continue
            tuples.append((x, y, z))
    while len(tuples) % 32:
        tuples.append((1.0,)*k)
    return tuples


def build(op, n, chain=1, mode='rn'):
    if op in RAW:
        k, lines = RAW[op]
        loc_hi, loc_lo = (8, 9) if op == 'null' else (20, 9)
        return _assemble(k, n, lines*chain, loc_hi, loc_lo, 21)
    k = OPS[op][0]
    P = S.Prog()
    names = [(P.input(f'{c}h'), P.input(f'{c}l')) for c in 'abc'[:k]]
    x = names[0]
    fn = OPS[op][1]
    kw = {'mode': mode} if 'mode' in fn.__code__.co_varnames else {}
    for _ in range(chain):                     # x = op(x, b[, c]) repeated: a dependent chain of `chain` operations per lane
        x = fn(P, x, *names[1:], **kw)
    hi, lo = x
    lines, loc, used = S.emit(P, {f'{c}{w}': 8+2*i+j for i, c in enumerate('abc'[:k]) for j, w in enumerate('hl')}, [hi, lo], first=8+2*k)
    rh, rl = loc[hi.id], loc[lo.id]
    return _assemble(k, n, lines, rh, rl, used)


def _assemble(k, n, lines, rh, rl, used):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = []
    for k_, r in enumerate(range(8, 8+2*k)):
        if k_:
            ins += [mov(6, k_*n), e('iadd r7, r1, r6'), load(r, 7, True)]
        else:
            ins += [load(r, 1, True)]
    ins.append(e('wait 0'))
    body = [e(l) for l in lines]
    tail = [mov(6, 2*k*n), e('iadd r7, r1, r6'), agx_loop.store(rh, 8, 7),
            mov(6, (2*k+1)*n), e('iadd r7, r1, r6'), agx_loop.store(rl, 8, 7), e('wait 0'), mov(2, 0)]
    allb = ins+body+tail
    DA.decode_lengths(b''.join(allb), [len(i) for i in allb])
    return b''.join(allb), len(lines), used


def table(tuples):
    n = len(tuples); k = len(tuples[0])
    words = []
    for j in range(k):
        words += [S.split(t[j])[0] for t in tuples]+[S.split(t[j])[1] for t in tuples]
    return words+[0xcdcdcdcd]*(2*n)


def check(op, tuples, t, first=None, chain=1, mode='rn'):
    n = len(tuples); k = len(tuples[0])
    bad = []
    for i, xs in enumerate(tuples[:first] if first else tuples):
        h, l = t[2*k*n+i], t[(2*k+1)*n+i]
        r = xs[0]
        for _ in range(chain):
            r = S.ref(op, r, *xs[1:], mode=mode)
        want = S.split(r)
        ok = math.isnan(S.join(h, l)) if math.isnan(r) else (h, l) == want
        if not ok:
            bad.append((xs, (h, l), want))
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--op', default='mul', choices=sorted(OPS)+sorted(RAW))
    p.add_argument('--round', default='rn', choices=['rn', 'rz', 'rm', 'rp'])
    p.add_argument('--random', type=int, default=8000)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--chain', type=int, default=1, help='dependent chain of this many operations per lane (cost slope)')
    p.add_argument('--lanes', type=int, default=0, help='repeat the dataset up to this many lanes (cost runs); IEEE check covers the first block')
    p.add_argument('--keeper', action='store_true', help='run the clock keeper during hardware runs')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/softfp64'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    pairs = dataset(a.random, a.op if a.op in OPS else 'fma')
    base = len(pairs)
    if a.lanes > base:
        pairs = (pairs*(a.lanes//base+1))[:a.lanes//32*32]
    n = len(pairs)
    prog, ninstr, used = build(a.op, n, a.chain, a.round)
    code = drm.build_main(prog)
    tb = table(pairs)
    regs = 2*used+8
    print(f'{a.op}: {n} lanes, {ninstr} instructions, registers up to r{used-1}', flush=True)
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        o, t = cov.simulate(code, n, 32, regs, 0, tb)
        bad = check(a.op, pairs, t, base, a.chain, a.round) if a.op in OPS else []
        print('simulator replay: %d lanes, %d differ from IEEE' % (n, len(bad)))
        for xs, got, want in bad[:10]:
            print('  ', xs, [hex(v) for v in got], [hex(v) for v in want])
        return 1 if bad else 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'op': a.op, 'round': a.round, 'lanes': n, 'instructions': ninstr, 'registers': used, 'checked_lanes': base, 'chain': a.chain, 'runs': []}
    keeper = None
    if a.keeper:
        import time
        stop = out/'keeper-stop'; stop.unlink(missing_ok=True)
        keeper = subprocess.Popen([sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '600', '--stop-file', str(stop)],
                                  cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
    for rep in range(a.repeats):
        (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(regs), str(out/'t.bin')],
                           capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        t = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
        bad = check(a.op, pairs, t, base, a.chain, a.round) if a.op in OPS else []
        rec['runs'].append({'rep': rep, 'bad': len(bad), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'first_bad': [[list(xs), list(g), list(w)] for xs, g, w in bad[:5]]})
        print('hardware run', rep, 'lanes differing from IEEE:', len(bad), 'fw_ns', rec['runs'][-1]['fw_ns'], flush=True)
    if keeper is not None:
        stop.touch()
        try:
            keeper.wait(timeout=60)
        except subprocess.TimeoutExpired:
            keeper.kill()
        rec['keeper_stopped'] = keeper.poll() is not None
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
