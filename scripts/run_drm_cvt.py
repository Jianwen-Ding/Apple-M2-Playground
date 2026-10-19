#!/usr/bin/env python3
"""Software fp64 conversions (softfp64.py cvt_*) on AGX: bit-exactness against IEEE/exact references and cost.
Operands: one input word-pair (f64) or word (f32/u32/s32), one output word-pair or word.
  run_drm_cvt.py offline|hardware --op OP [--round MODE] [--random N]
Needs the simulator repo for the offline replay (same layout as run_drm_softfp64.py).
"""
import argparse, json, math, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
import softfp64 as S
import run_drm_softfp64 as R

REPO = Path(__file__).resolve().parents[1]

# op -> (function, input kind, output kind); input/output kinds: 'f64' (hi/lo pair), 'f32'/'i32' (one word in lo)
BASE = {'cvt_f32_f64': (S.cvt_f32_f64, 'f32', 'f64'),
        'cvt_f64_f32': (S.cvt_f64_f32, 'f64', 'f32'),
        'cvt_s32_f64': (S.cvt_s32_f64, 'i32', 'f64'),
        'cvt_u32_f64': (S.cvt_u32_f64, 'i32', 'f64'),
        'cvt_f64_s32': (S.cvt_f64_s32, 'f64', 'i32'),
        'cvt_f64_u32': (S.cvt_f64_u32, 'f64', 'i32')}
MODES = {'cvt_f32_f64': ['rn'], 'cvt_f64_f32': ['rn', 'rz', 'rm', 'rp'],
         'cvt_s32_f64': ['rn'], 'cvt_u32_f64': ['rn'],
         'cvt_f64_s32': ['rn', 'rz', 'rm', 'rp'], 'cvt_f64_u32': ['rn', 'rz', 'rm', 'rp']}
OPS = {}
for _b, (_f, _i, _o) in BASE.items():
    for _m in MODES[_b]:
        OPS[f'{_b}_{_m}'] = (_f, _i, _o, _m)

F32_EDGE = [0.0, -0.0, 1.0, -1.0, 1.5, -2.5, 3.14159, 1e-30, 1e30, 1e38, 3.4028234663852886e+38,
            3.402823567391073e+38, 2.0**-149, -2.0**-149, 2.0**-126, -2.0**-126, float('inf'),
            float('-inf'), 0.1, 1.0000001, 16777217.0, 2.0**24, -2.0**24, 65536.0, 1e-10, 1e10]
INT_EDGE = [0, 1, -1, 2**31-1, -2**31, 2**31-1, 2**32-1, 123456789, -123456789, 2**24+1, -(2**24+1),
            2**30+77, 0x7fffffff, 0x80000000, 0xffffffff, 42, -42]


def f32bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def dataset(nrand, op, seed=1):
    rng = random.Random(seed)
    base = op.rsplit('_', 1)[0] if op.rsplit('_', 1)[-1] in ('rn', 'rz', 'rm', 'rp') else op
    ikind = BASE[[b for b in BASE if op.startswith(b)][0]][1]
    if ikind == 'f64':
        pool = list(R.EDGE)
    elif ikind == 'f32':
        pool = F32_EDGE
    else:
        pool = INT_EDGE
    tuples = [(x,) for x in pool]
    for _ in range(nrand):
        if ikind == 'f64':
            k = rng.random()
            if k < 0.3:
                tuples.append((struct.unpack('<d', struct.pack('<Q', rng.getrandbits(64)))[0],))
            else:
                tuples.append((math.ldexp(rng.random() + 0.5, rng.randint(-1074, 1023)) * rng.choice([1, -1]),))
        elif ikind == 'f32':
            k = rng.random()
            if k < 0.3:
                tuples.append((struct.unpack('<f', struct.pack('<I', rng.getrandbits(32)))[0],))
            else:
                tuples.append((math.ldexp(rng.random() + 0.5, rng.randint(-149, 127)) * rng.choice([1, -1]),))
        else:
            tuples.append((rng.getrandbits(32),))
    while len(tuples) % 32:
        tuples.append((1.0 if ikind != 'i32' else 1,))
    return tuples


def build(op, n, chain=1):
    fn, ikind, okind, mode = OPS[op]
    kw = {'mode': mode} if 'mode' in fn.__code__.co_varnames else {}
    P = S.Prog()
    ah, al = P.input('ah'), P.input('al')
    x = (ah, al)
    for _ in range(chain):
        # recompute from the original input each time: cvt changes type, so feeding the
        # output back would change domains (timing only; correctness uses chain = 1)
        x = fn(P, (ah, al), **kw) if kw else fn(P, (ah, al))
    hi, lo = x
    lines, loc, used = S.emit(P, {'ah': 8, 'al': 9}, [hi, lo], first=10)
    rh, rl = loc[hi.id], loc[lo.id]
    e = agx_loop.encode
    mov = chains.mov_imm
    # table layout mirrors _assemble: hi block then lo block; al (r9) holds the single input word
    if ikind == 'f64':
        ins = [R.load(8, 1, True), mov(6, n), e('iadd r7, r1, r6'), R.load(9, 7, True)]
    else:
        ins = [R.load(9, 1, True)]
    ins.append(e('wait 0'))
    body = [e(l) for l in lines]
    tail = [mov(6, 2 * n), e('iadd r7, r1, r6'), agx_loop.store(rh if okind == 'f64' else rl, 8, 7)]
    if okind == 'f64':
        tail += [mov(6, 3 * n), e('iadd r7, r1, r6'), agx_loop.store(rl, 8, 7)]
    tail += [e('wait 0'), mov(2, 0)]
    allb = ins + body + tail
    DA.decode_lengths(b''.join(allb), [len(i) for i in allb])
    return b''.join(allb), len(lines), used


def table(op, tuples):
    n = len(tuples)
    fn, ikind, okind, mode = OPS[op]
    base = [b for b in BASE if op.startswith(b)][0]
    words = []
    if ikind == 'f64':
        words += [S.split(t[0])[0] for t in tuples] + [S.split(t[0])[1] for t in tuples]
    elif ikind == 'f32':
        words += [f32bits(float(t[0])) for t in tuples]
    else:
        words += [t[0] & 0xffffffff for t in tuples]
    return words + [0xcdcdcdcd] * (3 * n)


def check(op, tuples, t, first=None, chain=1):
    # note: chains recompute from the original input (timing only), so the reference applies once
    n = len(tuples)
    fn, ikind, okind, mode = OPS[op]
    base = [b for b in BASE if op.startswith(b)][0]
    bad = []
    for i, xs in enumerate(tuples[:first] if first else tuples):
        r = xs[0]
        if base in ('cvt_f32_f64',):
            r = S.ref(base, float(struct.unpack('<f', struct.pack('<f', r))[0]), mode=mode)
        elif base in ('cvt_s32_f64', 'cvt_u32_f64'):
            r = S.ref(base, r & 0xffffffff, mode=mode)
        else:
            r = S.ref(base, r, mode=mode)
        if okind == 'f64':
            h, l = t[2 * n + i], t[3 * n + i]
            want = S.split(r)
            ok = math.isnan(S.join(h, l)) if math.isnan(r) else (h, l) == want
            if not ok:
                bad.append((xs, (h, l), want))
        else:
            l = t[2 * n + i]
            if base == 'cvt_f64_f32':
                if math.isnan(r):
                    ok = ((l >> 23) & 0xff) == 0xff and (l & 0x7fffff) != 0
                else:
                    ok = l == struct.unpack('<I', struct.pack('<f', r))[0]
                want = r
            else:
                want = r & 0xffffffff
                ok = l == want
            if not ok:
                bad.append((xs, l, want))
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--op', default='cvt_f64_f32_rn', choices=sorted(OPS))
    p.add_argument('--random', type=int, default=800)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--chain', type=int, default=1)
    p.add_argument('--lanes', type=int, default=0)
    p.add_argument('--keeper', action='store_true')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/softfp64cvt'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    pairs = dataset(a.random, a.op)
    base = len(pairs)
    if a.lanes > base:
        pairs = (pairs * (a.lanes // base + 1))[:a.lanes // 32 * 32]
    n = len(pairs)
    prog, ninstr, used = build(a.op, n, a.chain)
    code = drm.build_main(prog)
    tb = table(a.op, pairs)
    regs = 2 * used + 8
    print(f'{a.op}: {n} lanes, {ninstr} instructions, registers up to r{used-1}', flush=True)
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov  # noqa: E402
        o, t = cov.simulate(code, n, 32, regs, 0, tb)
        bad = check(a.op, pairs, t, base, a.chain)
        print('simulator replay: %d lanes, %d differ' % (n, len(bad)))
        for xs, got, want in bad[:10]:
            print('  ', xs, got, want)
        return 1 if bad else 0
    out = a.output
    out.mkdir(parents=True, exist_ok=True)
    exe = out / 'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO / 'tests/drm_compute.c'), '-o', str(exe)], check=True)
    fn, ikind, okind, _mode = OPS[a.op]
    rec = {'op': a.op, 'lanes': n, 'instructions': ninstr, 'registers': used, 'checked_lanes': base,
           'chain': a.chain, 'runs': []}
    keeper = None
    if a.keeper:
        import time
        stop = out / 'keeper-stop'
        stop.unlink(missing_ok=True)
        keeper = subprocess.Popen([sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '600',
                                   '--stop-file', str(stop)], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
    for rep in range(a.repeats):
        (out / 'c.bin').write_bytes(code + bytes(16))
        (out / 't.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out / 'c.bin'), str(n), str(out / 'rb'), '1',
                            str(regs), str(out / 't.bin')], capture_output=True, timeout=60,
                           env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out / 't.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: ' + r.stdout.decode()[-300:])
        t = struct.unpack(f'<{len(tb)}I', (out / 't.out').read_bytes())
        bad = check(a.op, pairs, t, base, a.chain)
        rec['runs'].append({'rep': rep, 'bad': len(bad), 'fw_ns': smp[0]['fw_ts'][1] - smp[0]['fw_ts'][0],
                            'first_bad': [[list(x) if isinstance(x, tuple) else x, g, w] for x, g, w in bad[:5]]})
        print('hardware run', rep, 'lanes differing:', len(bad), 'fw_ns', rec['runs'][-1]['fw_ns'], flush=True)
    if keeper is not None:
        stop.touch()
        try:
            keeper.wait(timeout=60)
        except subprocess.TimeoutExpired:
            keeper.kill()
        rec['keeper_stopped'] = keeper.poll() is not None
    if a.result:
        a.result.write_text(json.dumps(rec) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
