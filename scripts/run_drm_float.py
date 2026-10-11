#!/usr/bin/env python3
"""Float semantics of fadd/fmul/fmadd (32- and 16-bit) on G14C through direct DRM.

Only known, round-tripping encodings are used (applegpu assembler); the inputs are
what vary, so no new encoding reaches the GPU. Each lane loads A, B, C from the
table (words 0, 64, 128 + lane) and stores op(A, B, C) as r2.

Every result is compared with exact host models (Fraction arithmetic, round to
nearest even): inputs as-is or flushed (DAZ), outputs as-is or flushed (FTZ: 1 = after rounding,
2 = when the exact result is below the smallest normal, before rounding), and
for fmadd fused (one rounding) or unfused (two roundings). The report lists which
models agree with every non-NaN lane, and the NaN bit patterns produced.
"""
import argparse, datetime, json, os, random, struct, subprocess, sys, time
from fractions import Fraction as Fr
from pathlib import Path

import agx_loop
import run_drm_compute as drm

REPO = Path(__file__).resolve().parents[1]
FMT = {32: (8, 23), 16: (5, 10)}
N = 64


def decode(bits, w):
    e, m = FMT[w]; bias = (1 << (e-1))-1
    s = bits >> (w-1) & 1; E = bits >> m & ((1 << e)-1); M = bits & ((1 << m)-1)
    if E == (1 << e)-1:
        return ('nan', bits) if M else ('inf', s)
    v = Fr(M, 1 << m) * Fr(2)**(1-bias) if E == 0 else (1+Fr(M, 1 << m)) * Fr(2)**(E-bias)
    return ('num', s, v)   # keep sign separately for zeros


def is_denorm(bits, w):
    e, m = FMT[w]; return (bits >> m & ((1 << e)-1)) == 0 and bits & ((1 << m)-1) != 0


def flush(bits, w):
    return bits & (1 << (w-1)) if is_denorm(bits, w) else bits


def round_rte(s, v, w):
    """Sign s, magnitude Fraction v >= 0 -> bits, RTE with subnormals and overflow to inf."""
    e, m = FMT[w]; bias = (1 << (e-1))-1; emin = 1-bias
    if v == 0: return s << (w-1)
    ex = v.numerator.bit_length()-v.denominator.bit_length()
    if Fr(2)**ex > v: ex -= 1
    ex = max(ex, emin)
    q = v / Fr(2)**(ex-m)                      # scaled so the integer part has m+1 bits (or fewer if subnormal)
    n = q.numerator // q.denominator; rem = q - n
    if rem > Fr(1, 2) or (rem == Fr(1, 2) and n & 1): n += 1
    if n >= 1 << (m+1): n >>= 1; ex += 1
    if ex > bias: return s << (w-1) | ((1 << e)-1) << m
    if n < 1 << m: return s << (w-1) | n              # subnormal (ex == emin)
    return s << (w-1) | (ex+bias) << m | (n - (1 << m))


def val(x):
    return x[2] if x[0] == 'num' else None


def signed(x):
    return -x[2] if x[1] else x[2]


def model(op, ins, w, daz, ftz, fused=True, sat=False):
    """Returns result bits or 'nan'."""
    ins = ins[:3 if op == 'fma' else 2]
    ins = [flush(b, w) if daz else b for b in ins]
    d = [decode(b, w) for b in ins]
    if any(x[0] == 'nan' for x in d): return 'nan'
    def to_bits(x):   # x: ('inf', s) | ('num', s, Fr)
        if x[0] == 'inf': return x[1] << (w-1) | ((1 << FMT[w][0])-1) << FMT[w][1]
        return round_rte(x[1], abs(x[2]), w)
    def add(x, y):
        if x[0] == 'inf' and y[0] == 'inf': return ('inf', x[1]) if x[1] == y[1] else 'nan'
        if x[0] == 'inf': return x
        if y[0] == 'inf': return y
        r = signed(x)+signed(y)
        if r == 0: return ('num', x[1] & y[1], Fr(0))      # RTE: +0 unless both negative
        return ('num', int(r < 0), abs(r))
    def mul(x, y):
        s = x[1] ^ y[1]
        if x[0] == 'inf' or y[0] == 'inf':
            if (x[0] == 'num' and x[2] == 0) or (y[0] == 'num' and y[2] == 0): return 'nan'
            return ('inf', s)
        return ('num', s, x[2]*y[2])
    def rnd(x):     # round an exact value to the format, as a decoded value
        if x == 'nan' or x[0] == 'inf': return x
        if ftz == 2 and 0 < x[2] < Fr(2)**(2-(1 << (FMT[w][0]-1))):   # flush on the exact value (tininess before rounding)
            return ('num', x[1], Fr(0))
        b = round_rte(x[1], x[2], w)
        if ftz: b = flush(b, w)
        return decode(b, w)
    if op == 'add': r = add(d[0], d[1])
    elif op == 'mul': r = mul(d[0], d[1])
    else:
        p = mul(d[0], d[1])
        if p == 'nan': return 'nan'
        if not fused: p = rnd(p)
        r = add(p, d[2])
    if r == 'nan': return 'nan'
    r = rnd(r)
    if sat:
        if r[0] == 'inf': return 0 if r[1] else to_bits(('num', 0, Fr(1)))
        v = signed(r)
        if v <= 0: return 0 if v < 0 or True else 0
        if v >= 1: return to_bits(('num', 0, Fr(1)))
    b = to_bits(r)
    return b


def vectors(w, seed):
    r = random.Random(seed)
    if w == 32:
        E = [0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007fffff, 0x00800000, 0x00800001, 0x80800000,
             0x3f800000, 0xbf800000, 0x3f800001, 0x33800000, 0x7f7fffff, 0xff7fffff, 0x7f800000, 0xff800000,
             0x7fc00000, 0x7f800001, 0xffc12345, 0x7fa00000, 0x3f000000, 0x40000000, 0x1f800000, 0x20000000,
             0x3f801000, 0x3f802000, 0xbf801000, 0x00400000, 0x3e800000, 0x3fc00000]
    else:
        E = [0x0000, 0x8000, 0x0001, 0x8001, 0x03ff, 0x0400, 0x0401, 0x8400, 0x3c00, 0xbc00, 0x3c01, 0x1400,
             0x7bff, 0xfbff, 0x7c00, 0xfc00, 0x7e00, 0x7c01, 0xfe12, 0x7d00, 0x3800, 0x4000, 0x0200, 0x2000,
             0x3c20, 0x3c40, 0xbc20, 0x3e00, 0x3400, 0x3a00]
    M = (1 << w)-1
    out = []
    for a in E:
        for b in E:
            out.append((a, b, E[(E.index(a)*7+E.index(b)) % len(E)]))
    # targeted: sums/products/fma landing in denormal range, ties, fused-vs-unfused
    if w == 32:
        out += [(0x00800001, 0x80800000, 0), (0x00800000, 0x3f000000, 0), (0x00ffffff, 0x3f000000, 0),
                (0x3f801000, 0x3f801000, 0xbf802000), (0x3f800001, 0x3f800001, 0xbf800002), (0x33800000, 0x3f800000, 0x3f800000),
                (0x3f800000, 0x33800000, 0), (0x3f800001, 0x33800000, 0), (0x01000000, 0x3e800000, 0), (0x00800000, 0x3f7fffff, 0)]
    for _ in range(200):
        out.append(tuple(r.getrandbits(w) for _ in range(3)))
        x = r.getrandbits(w-1) | (r.getrandbits(1) << (w-1))
        out.append((x, x ^ (1 << (w-1)) ^ r.getrandbits(3), r.getrandbits(w)))   # near-cancellation
    return [tuple(v & M for v in t) for t in out]


OPS = {
    'fadd32': ('add', 32, 'fadd32 r2, r6, r7', False), 'fmul32': ('mul', 32, 'fmul32 r2, r6, r7', False),
    'fmadd32': ('fma', 32, 'fmadd32 r2, r6, r7, r8', False),
    'fadd32.sat': ('add', 32, 'fadd32.sat r2, r6, r7', True), 'fmul32.sat': ('mul', 32, 'fmul32.sat r2, r6, r7', True),
    'fmadd32.sat': ('fma', 32, 'fmadd32.sat r2, r6, r7, r8', True),
    'fadd16': ('add', 16, 'fadd16 r2l, r6l, r7l', False), 'fmul16': ('mul', 16, 'fmul16 r2l, r6l, r7l', False),
    'fmadd16': ('fma', 16, 'fmadd16 r2l, r6l, r7l, r8l', False),
}


def body(asm):
    e = agx_loop.encode; mov = agx_loop.chains.mov_imm
    ins = [e('iadd r3, r1, 0'), e('device_load 0, i32, x, r6, u8_u9, r3, unsigned'),
           e('iadd r3, r1, 64'), e('device_load 0, i32, x, r7, u8_u9, r3, unsigned'),
           e('iadd r3, r1, 128'), e('device_load 0, i32, x, r8, u8_u9, r3, unsigned'), e('wait 0'),
           mov(2, 0), e(asm)]
    import run_drm_atomic as DA
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ops', default=','.join(OPS))
    p.add_argument('--seed', type=int, default=11)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/float')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    state = {'utc': stamp, 'ops': {}, 'complete': False}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')

    def submit(code, words):
        (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(words)}I', *words))
        if (out/'rb').exists(): (out/'rb').unlink()
        try:
            res = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(N), str(out/'rb'), '1', '32', str(out/'t.bin')],
                                 capture_output=True, timeout=20)
        except subprocess.TimeoutExpired:
            return None
        smp = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{') and '"rep"' in l]
        if res.returncode or not smp or not all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in smp):
            return None
        w = list(struct.unpack(f'<{N+32}I', (out/'rb').read_bytes()))
        if w[:8] != [0xcdcdcdcd]*8 or w[8+N+8:] != [0xa5a50000+j for j in range(16)]: return None
        return w[8:8+N]

    try:
        for name in a.ops.split(','):
            kind, w, asm, sat = OPS[name]
            code = drm.build_main(body(asm))
            vecs = vectors(w, a.seed)
            res = []
            for k in range(0, len(vecs), N):
                chunk = vecs[k:k+N]; chunk += [(0, 0, 0)]*(N-len(chunk))
                words = [t[0] for t in chunk]+[t[1] for t in chunk]+[t[2] for t in chunk]
                got = submit(code, words)
                if got is None:
                    state['fault'] = name; raise RuntimeError(f'fault on {name}; stopping')
                res += [(chunk[i], got[i]) for i in range(N) if k+i < len(vecs)]
            state['ops'][name] = analyse(kind, w, sat, asm, res)
            save()
            o = state['ops'][name]
            print(json.dumps({'op': name, 'vectors': len(res), 'matching': o['matching_models'],
                              'min_mismatch': min((v['mismatches'], k) for k, v in o['models'].items()),
                              'nan_out': {k: v['count'] for k, v in o['nan_outputs'].items()}}), flush=True)
        state['complete'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save(); print(json.dumps({'complete': state['complete'], 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['complete'] else 1


def analyse(kind, w, sat, asm, res):
    if True:
        if True:
            models = {}
            combos = [(daz, ftz, fu) for daz in (0, 1) for ftz in (0, 1, 2) for fu in ((1, 0) if kind == 'fma' else (1,))]
            nan_out = {}
            for daz, ftz, fu in combos:
                key = f"daz{daz}-ftz{ftz}" + (f"-fused{fu}" if kind == 'fma' else '')
                bad = []
                for (ins, g) in res:
                    g &= (1 << w)-1
                    m = model(kind, ins, w, daz, ftz, fu, sat)
                    if m == 'nan':
                        gd = decode(g, w)
                        if sat:
                            if g != 0 and gd[0] != 'nan': bad.append((ins, g, 'nan'))
                        elif gd[0] != 'nan': bad.append((ins, g, 'nan'))
                        continue
                    if g != m: bad.append((ins, g, m))
                models[key] = {'mismatches': len(bad), 'examples': [[f'{x:#x}' for x in b[0]]+[f'{b[1]:#x}', b[2] if b[2] == 'nan' else f'{b[2]:#x}'] for b in bad[:6]]}
            for (ins, g) in res:
                g &= (1 << w)-1
                if model(kind, ins, w, 0, 0, 1, sat) == 'nan':
                    nan_out.setdefault(f'{g:#x}', []).append([f'{x:#x}' for x in ins])
            best = [k for k, v in models.items() if v['mismatches'] == 0]
            return {'asm': asm, 'vectors': len(res), 'models': models, 'matching_models': best,
                    'nan_outputs': {k: {'count': len(v), 'examples': v[:4]} for k, v in nan_out.items()},
                    'raw': [[*t, g] for t, g in res]}


if __name__ == '__main__':
    sys.exit(main())
