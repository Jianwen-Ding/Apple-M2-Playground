#!/usr/bin/env python3
"""Offline check of the cross-lane width / scan-order finding (novel-results/2026-10-16-cross-lane-width).

Re-derives every claim from the retained hardware words in results/2026-10-16-cross-lane-width/cases.json.gz
(122 cases, 1024 lanes each: each lane's r6, r7 and the r14 the GPU wrote):

  1. 16-bit sources combine at 16 bits: integers wrap at 2^16, floats are fp16 (denormals kept, rounded each step);
     the high half of a 32-bit destination register is untouched.
  2. A 64-bit source (r6_r7) is read as its low 32 bits: min/max/fadd/... ignore r7.
  3. Reductions are a pairwise tree; quad prefix ops a lane-order chain; SIMD prefix ops a 32-lane Sklansky scan.
     Lane i receives the inclusive value of lane i-1 (exclusive scan), lane 0 the identity.

It also checks that the obvious alternatives do NOT fit: a genuine 64-bit reduction, and a Kogge-Stone SIMD scan.
Pure Python (no numpy). Exit status 1 on any failure.
"""
import gzip, json, struct, sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'results/2026-10-16-cross-lane-width/cases.json.gz'
NAN16, NAN32 = 0x7e00, 0x7fc00000


# ---- fp16 (exact: a sum or product of two halves is exact in a double, then one rounding) -------------------
def h(b):
    return struct.unpack('<e', struct.pack('<H', b & 0xffff))[0]


def to_h(x):
    if x != x:
        return NAN16
    try:
        return struct.unpack('<H', struct.pack('<e', x))[0]
    except OverflowError:
        return 0x7c00 if x > 0 else 0xfc00


def isnan16(b):
    return (b & 0x7c00) == 0x7c00 and (b & 0x3ff) != 0


# ---- fp32 with the hardware's denormal flush (inputs and outputs), exact rounding via Fraction ---------------
def f(b):
    if (b >> 23) & 0xff == 0:
        return -0.0 if b >> 31 else 0.0
    return struct.unpack('<f', struct.pack('<I', b))[0]


def isnan32(b):
    return (b >> 23) & 0xff == 0xff and b & 0x7fffff


def round32(x):
    """exact rational (or inf / signed zero float) -> fp32 bits, round to nearest even, flush denormal results"""
    if isinstance(x, float):
        return struct.unpack('<I', struct.pack('<f', x))[0]
    if x == 0:
        return 0
    neg, a = x < 0, abs(x)
    e = a.numerator.bit_length() - a.denominator.bit_length()
    if Fraction(2) ** e > a:
        e -= 1
    if e < -126:
        return 0x80000000 if neg else 0
    scale = Fraction(2) ** (e - 23)
    m = a / scale
    q, r = divmod(m.numerator, m.denominator)
    if 2 * r > m.denominator or (2 * r == m.denominator and q & 1):
        q += 1
    v = q * scale
    if v >= Fraction(2) ** 128:
        return 0xff800000 if neg else 0x7f800000
    return struct.unpack('<I', struct.pack('<f', float(-v if neg else v)))[0]


def fop32(op, x, y):
    a, b = f(x), f(y)
    if a != a or b != b or a in (float('inf'), float('-inf')) or b in (float('inf'), float('-inf')):
        r = a + b if op == 'fadd' else a * b
        return NAN32 if r != r else round32(r)
    if op == 'fadd':
        if a == 0 and b == 0:
            return round32(a + b)          # signed zero rules
        return round32(Fraction(a) + Fraction(b))
    if a == 0 or b == 0:
        return round32(a * b)
    return round32(Fraction(a) * Fraction(b))


# ---- one combining step at 16 or 32 bits ---------------------------------------------------------------------
def make(op, w16):
    m = 0xffff if w16 else 0xffffffff
    sb = 15 if w16 else 31
    s = lambda v: v - (1 << (sb + 1)) if v >> sb else v
    val = h if w16 else f
    isnan = isnan16 if w16 else isnan32

    def c(x, y):
        if x is None:
            return y
        if y is None:
            return x
        if op == 'iadd': return (x + y) & m
        if op == 'and': return x & y
        if op == 'or': return x | y
        if op == 'xor': return x ^ y
        if op == 'min-u': return min(x, y)
        if op == 'max-u': return max(x, y)
        if op == 'min-s': return y if s(y) < s(x) else x
        if op == 'max-s': return y if s(y) > s(x) else x
        if op in ('fadd', 'fmul'):
            if w16:
                r = h(x) + h(y) if op == 'fadd' else h(x) * h(y)
                return to_h(r)
            return fop32(op, x, y)
        # min-f / max-f: NaN loses (of two NaNs the left is kept); ties keep the left operand
        fx, fy = val(x), val(y)
        if isnan(x):
            return x if isnan(y) else y
        if isnan(y) or fx == fy:
            return x
        return x if (fx < fy) == (op == 'min-f') else y
    return c


def identity(op, w16):
    t = {'iadd': 0, 'or': 0, 'xor': 0, 'max-u': 0, 'and': -1, 'min-u': -1}
    if op in t:
        return t[op] & (0xffff if w16 else 0xffffffff)
    return {('min-s', 1): 0x7fff, ('max-s', 1): 0x8000, ('fadd', 1): 0x8000, ('fmul', 1): 0x3c00,
            ('min-s', 0): 0x7fffffff, ('max-s', 0): 0x80000000, ('fadd', 0): 0x80000000, ('fmul', 0): 0x3f800000,
            ('min-f', 1): NAN16, ('max-f', 1): NAN16, ('min-f', 0): NAN32, ('max-f', 0): NAN32}[(op, int(w16))]


def tree(vs, c):
    while len(vs) > 1:
        vs = [c(vs[i], vs[i + 1]) for i in range(0, len(vs), 2)]
    return vs[0]


def sklansky(x, c):
    inc, b = list(x), 1
    while b < len(x):
        inc = [c(inc[(i // b) * b - 1], inc[i]) if (i // b) % 2 else inc[i] for i in range(len(x))]
        b *= 2
    return inc


def kogge_stone(x, c):
    inc, d = list(x), 1
    while d < len(x):
        inc = [c(inc[i - d], inc[i]) if i >= d else inc[i] for i in range(len(x))]
        d *= 2
    return inc


def chain(x, c):
    out, acc = [], None
    for v in x:
        acc = c(acc, v)
        out.append(acc)
    return out


def predict(case, scan=sklansky, wide64=False):
    scope, rest = case['name'].split('_', 1)
    prefix = rest.startswith('prefix_')
    op = rest[len('prefix_'):] if prefix else rest
    op = op.split('_r14')[0]
    w16 = case['name'].endswith('r14l_r6l')
    masked = case['area'] == 'alu_masked'
    width = 4 if scope == 'quad' else 32
    float_op = op in ('fadd', 'fmul')
    c = make(op, w16)
    if wide64 and not w16:          # alternative: a genuine 64-bit integer reduction, low half written
        c64 = make(op, False)
        sh = lambda v: v - (1 << 64) if v >> 63 else v
        c = {'iadd': lambda x, y: x if y is None else y if x is None else (x + y) & (2**64 - 1),
             'min-u': lambda x, y: x if y is None else y if x is None else min(x, y),
             'max-u': lambda x, y: x if y is None else y if x is None else max(x, y),
             'min-s': lambda x, y: x if y is None else y if x is None else (y if sh(y) < sh(x) else x),
             'max-s': lambda x, y: x if y is None else y if x is None else (y if sh(y) > sh(x) else x)}.get(op, c64)
    out = {}
    n = len(case['r6'])
    for g0 in range(0, n, width):
        lanes = range(g0, g0 + width)
        act = [not (masked and (l & 3) == 3) for l in lanes]
        x = []
        for l, a in zip(lanes, act):
            if not a:
                x.append((NAN16 if w16 else NAN32) if op in ('min-f', 'max-f') else None)
                continue
            v = case['r6'][l] & 0xffff if w16 else case['r6'][l]
            if wide64 and not w16:
                v |= case['r7'][l] << 32
            if float_op and not w16 and (v >> 23) & 0xff == 0:
                v &= 0x80000000
            x.append(v)
        if not prefix:
            res = [tree(x, c)] * width
        else:
            inc = chain(x, c) if scope == 'quad' else scan(x, c)
            res = [identity(op, w16)] + [identity(op, w16) if v is None else v for v in inc[:-1]]
        for i, l in enumerate(lanes):
            if act[i] and res[i] is not None:
                v = res[i] & 0xffffffff
                if float_op and (isnan16(v) if w16 else isnan32(v)):
                    v = NAN16 if w16 else NAN32
                out[l] = v
    return out


def mismatches(case, **kw):
    pred = predict(case, **kw)
    bad = 0
    for l, v in pred.items():
        hw = case['r14'][l]
        want = (0xdead0000 | v) if case['name'].endswith('r14l_r6l') else v
        bad += hw != want
    return bad


def main():
    d = json.load(gzip.open(DATA, 'rt'))
    cases = d['cases']
    fails = 0

    def check(ok, msg):
        nonlocal fails
        print(('ok   ' if ok else 'FAIL ') + msg)
        fails += not ok

    check(len(cases) == 122, f'{len(cases)} retained cases (61 forms x alu / alu_masked)')
    check(all(c['r15'] == [0xdeadbeef] * len(c['r15']) for c in cases), 'r15 untouched in every case (no 64-bit destination write)')
    bad = {c['area'] + '/' + c['name']: mismatches(c) for c in cases}
    worst = [k for k, v in bad.items() if v]
    check(not worst, f'claimed model: {sum(1 for v in bad.values() if not v)}/122 cases exact on every executing lane {worst[:5]}')
    h16 = [c for c in cases if c['name'].endswith('r14l_r6l')]
    check(all(all(w >> 16 == 0xdead for w in c['r14']) for c in h16), 'r14h preserved by every 16-bit form')
    w64 = [c for c in cases if c['name'].endswith('r14_r6_r7') and c['name'].split('_', 1)[1].split('_r14')[0] in ('iadd', 'min-u', 'max-u', 'min-s', 'max-s')]
    alt = sum(mismatches(c, wide64=True) for c in w64)
    check(alt > 0, f'genuine 64-bit reduction does not fit: {alt} mismatching words over {len(w64)} integer cases')
    sp = [c for c in cases if c['name'].startswith('simd_prefix_f')]
    ks = sum(mismatches(c, scan=kogge_stone) for c in sp)
    check(ks > 0, f'Kogge-Stone SIMD scan does not fit the fp16 prefix cases: {ks} mismatching words')
    print(f'{fails} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
