#!/usr/bin/env python3
"""Software IEEE binary32 fused multiply-add with subnormals and all four rounding modes, from AGX 32-bit integer
instructions (the softfp64 DSL, interpreter and emitter). Covers what the fp32 ALU cannot do:
  - PTX default (non-.ftz) add / sub / mul / fma .f32 with subnormal inputs or results (the hardware flushes both;
    novel-results/2026-10-11-float-semantics): add = fma(a, 1, b), mul = fma(a, b, -0);
  - directed rounding add / mul / fma .rz / .rm / .rp .f32 (the hardware rounds to nearest even only).
Straight-line, branch-free. NaN results are the canonical 0x7fc00000, the same as the hardware fp32 unit.

  P = Prog(); r = ffma32(P, a, b, c, mode)        # a, b, c: 32-bit V (f32 bits); mode in rn rz rm rp
  ref_fma32(a, b, c, mode) is the exact host reference (Fractions).
"""
import struct
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from softfp64 import M32, S32, Prog, clz128, emit, lshift4, round_pack_f32, rshift4  # noqa: E402,F401

CANON_NAN = 0x7fc00000


def unpack32(P, x):
    """-> sign, e (biased, effective after normalising), m (24-bit, bit 23 set unless zero), zero / inf / nan flags."""
    sign = P.and_(x, S32)
    ex = P.and_(P.lsr(x, 23), 0xff)
    mn = P.and_(x, 0x7fffff)
    exp0 = P.flag('ueq', ex, 0)
    expmax = P.flag('ueq', ex, 0xff)
    mz = P.flag('ueq', mn, 0)
    zero = P.and_(exp0, mz)
    inf = P.and_(expmax, mz)
    nan = P.and_(expmax, P.sub(1, mz))
    # subnormal: shift = clz32(mn) - 8 puts the leading bit at 23; e = 1 - shift. Normal: hidden bit, shift 0.
    s = P.sel('ugt', exp0, 0, P.sub(P.clz32(mn), 8), 0)
    s = P.sel('sgt', s, 23, 23, s)                     # zero mantissa: keep the shift in range (value unused)
    m = P.sel('ugt', exp0, 0, P.extr(0, mn, P.sub(32, s)), P.or_(mn, 0x800000))
    m = P.sel('ugt', P.and_(exp0, P.flag('ueq', s, 0)), 0, mn, m)   # extr by 32 - 0 = 32 would drop the word
    e = P.sub(P.sel('ugt', exp0, 0, 1, ex), s)
    return dict(sign=sign, e=e, m=m, zero=zero, inf=inf, nan=nan)


def ffma32(P, a, b, c, mode='rn'):
    """a*b + c in binary32 with one rounding in `mode`, subnormals in and out, IEEE zero signs, inf/NaN rules."""
    ua, ub, uc = unpack32(P, a), unpack32(P, b), unpack32(P, c)
    sp = P.xor(ua['sign'], ub['sign'])
    sc = uc['sign']
    # exact 48-bit product, normalised so that bit 47 is set; exponent ep of that representation
    lo, hi = P.mulw(ua['m'], ub['m'])
    top = P.and_(P.lsr(hi, 15), 1)
    plo = P.sel('ugt', top, 0, lo, P.extr(0, lo, 31))
    phi = P.sel('ugt', top, 0, hi, P.extr(lo, hi, 31))
    ep = P.add(P.sub(P.add(ua['e'], ub['e']), 127), top)
    pzero = P.or_(ua['zero'], ub['zero'])
    czero = uc['zero']
    # both mantissas as 128-bit words with the leading bit at 125 (product 47 + 14 + 64; addend 23 + 24 + 14 + 64)
    pw = [0, 0, P.extr(0, plo, 18), P.extr(plo, phi, 18)]
    cm = uc['m']
    cw = [0, 0, 0, P.extr(0, cm, 26)]                  # cm << 6: bits 102..125
    cw = [P.sel('ugt', czero, 0, 0, x) if not isinstance(x, int) else x for x in cw]
    pw = [P.sel('ugt', pzero, 0, 0, x) if not isinstance(x, int) else x for x in pw]
    ec = P.sel('ugt', czero, 0, -100000, uc['e'])
    ep = P.sel('ugt', pzero, 0, -100000, ep)
    # X = larger magnitude
    eq = P.flag('ueq', ep, ec)
    gtm = 0
    for k in (0, 1, 2, 3):
        gtm = P.sel('ugt', pw[k], cw[k], 1, P.sel('ult', pw[k], cw[k], 0, gtm))
    pbig = P.or_(P.flag('sgt', ep, ec), P.and_(eq, gtm))
    X = [P.sel('ugt', pbig, 0, pw[i], cw[i]) for i in range(4)]
    Y = [P.sel('ugt', pbig, 0, cw[i], pw[i]) for i in range(4)]
    ex = P.sel('ugt', pbig, 0, ep, ec)
    ey = P.sel('ugt', pbig, 0, ec, ep)
    sx = P.sel('ugt', pbig, 0, sp, sc)
    sy = P.sel('ugt', pbig, 0, sc, sp)
    d = P.sub(ex, ey)
    big = P.flag('ugt', d, 127)
    dc = P.sel('ugt', big, 0, 127, d)
    Ys, lost = rshift4(P, Y, dc, big)
    Ys = [P.or_(Ys[0], lost)] + Ys[1:]
    sd = P.flag('ugt', P.xor(sx, sy), 0)
    msk = P.sel('ugt', sd, 0, M32, 0)
    carry = sd
    S = []
    for k in range(4):
        t = P.add(X[k], P.xor(Ys[k], msk)); c1 = P.flag('ult', t, X[k])
        t2 = P.add(t, carry); c2 = P.flag('ult', t2, t)
        S.append(t2)
        carry = P.or_(c1, c2)
    szero = P.flag('ueq', P.or_(P.or_(S[0], S[1]), P.or_(S[2], S[3])), 0)
    lz = clz128(P, S)
    lzc = P.sel('ugt', lz, 127, 127, lz)
    N = lshift4(P, S, lzc)
    e = P.sub(P.add(ex, 2), lzc)
    m24 = P.lsr(N[3], 8)
    g = P.and_(P.lsr(N[3], 7), 1)
    st = P.flag('ugt', P.or_(P.or_(P.and_(N[3], 0x7f), N[2]), P.or_(N[1], N[0])), 0)
    _, r = round_pack_f32(P, sx, e, m24, g, st, mode)
    # exact zero sum of non-zero terms: +0, or -0 in rm
    zs = S32 if mode == 'rm' else 0
    r = P.sel('ugt', szero, 0, zs, r)
    # zero terms: both zero -> the IEEE sign rule; product zero -> c; addend zero -> rounded product (already r)
    both0 = P.and_(pzero, czero)
    zz = P.and_(sp, sc) if mode != 'rm' else P.or_(sp, sc)
    r = P.sel('ugt', P.and_(pzero, P.sub(1, czero)), 0, c, r)
    r = P.sel('ugt', both0, 0, zz, r)
    # inf / NaN
    pinf = P.or_(ua['inf'], ub['inf'])
    cinf = uc['inf']
    nan = P.or_(P.or_(P.or_(ua['nan'], ub['nan']), uc['nan']),
                P.or_(P.or_(P.and_(ua['inf'], ub['zero']), P.and_(ub['inf'], ua['zero'])),
                      P.and_(P.and_(pinf, cinf), P.flag('ugt', P.xor(sp, sc), 0))))
    infv = P.sel('ugt', pinf, 0, P.or_(sp, 0x7f800000), P.or_(sc, 0x7f800000))
    r = P.sel('ugt', P.or_(pinf, cinf), 0, infv, r)
    r = P.sel('ugt', nan, 0, CANON_NAN, r)
    return r


def fdiv32(P, a, b, mode='rn'):
    """a / b in binary32 with one rounding in `mode`, subnormals in and out, inf/NaN/zero rules; restoring division
    (26 quotient bits plus a sticky remainder), branch-free."""
    ua, ub = unpack32(P, a), unpack32(P, b)
    sign = P.xor(ua['sign'], ub['sign'])
    x, y = ua['m'], ub['m']
    # x < y: take one more quotient bit from x << 1 (exponent one lower)
    lt = P.flag('ult', x, y)
    x = P.sel('ugt', lt, 0, P.add(x, x), x)
    e = P.sub(P.add(P.sub(ua['e'], ub['e']), 127), lt)
    q = P.reg(0)
    for _ in range(26):
        ge = P.sel('ult', x, y, 0, 1)
        x = P.sel('ugt', ge, 0, P.sub(x, y), x)
        q = P.or_(P.add(q, q), ge)
        x = P.add(x, x)
    m24 = P.lsr(q, 2)
    g = P.and_(P.lsr(q, 1), 1)
    st = P.or_(P.and_(q, 1), P.flag('ugt', x, 0))
    _, r = round_pack_f32(P, sign, e, m24, g, st, mode)
    nan = P.or_(P.or_(ua['nan'], ub['nan']), P.or_(P.and_(ua['zero'], ub['zero']), P.and_(ua['inf'], ub['inf'])))
    inf = P.or_(ua['inf'], ub['zero'])
    zero = P.or_(ua['zero'], ub['inf'])
    r = P.sel('ugt', zero, 0, sign, r)
    r = P.sel('ugt', inf, 0, P.or_(sign, 0x7f800000), r)
    r = P.sel('ugt', nan, 0, CANON_NAN, r)
    return r


def div_fast_ok(P, a, b):
    """1 when the native rcp + Newton + Markstein sequence is exact (non-ftz rn): a normal with biased exponent >= 48 or
    a == +-0; b normal with exponent <= 252; quotient exponent estimate ea - eb + 127 in [2, 252] (a == 0: any normal b)."""
    ea = P.and_(P.lsr(a, 23), 0xff)
    eb = P.and_(P.lsr(b, 23), 0xff)
    az = P.flag('ueq', P.and_(a, 0x7fffffff), 0)
    okb = P.flag('ult', P.sub(eb, 1), 252)                 # 1 <= eb <= 252
    oka = P.flag('ult', P.sub(ea, 48), 255-48)             # 48 <= ea <= 254
    eq = P.sub(P.add(ea, 127), eb)
    okq = P.flag('ult', P.sub(eq, 2), 251)                 # 2 <= eq <= 252 (unsigned: wraps when negative)
    return P.and_(okb, P.or_(az, P.and_(oka, okq)))


def needs_ieee(P, a, b, c, r):
    """1 when the native fmadd32 result r may differ from IEEE non-ftz round-to-nearest: an operand is subnormal
    (the unit reads it as zero), or r is +-0 although neither factor is zero (an exact result below 2^-126 is
    flushed). Zero results of zero factors and every other case are exact on the native unit."""
    ta, tb, tc, tr = (P.and_(x, 0x7fffffff) for x in (a, b, c, r))
    da, db, dc = (P.sub(x, 1) for x in (ta, tb, tc))        # subnormal <=> |x| - 1 < 0x7fffff (unsigned); zero -> 0xffffffff
    mab = P.sel('ult', da, db, da, db)
    m = P.sel('ult', mab, dc, mab, dc)
    sub = P.flag('ult', m, 0x7fffff)
    abnz = P.flag('ugt', P.sel('ult', ta, tb, ta, tb), 0)     # min(|a|, |b|) != 0
    rz = P.sel('ueq', tr, 0, abnz, 0)
    return P.or_(sub, rz)


# ---- exact host reference ------------------------------------------------------------------------------------

def f32val(x):
    """Fraction value of finite f32 bits, or 'inf' / 'nan' markers."""
    ex = (x >> 23) & 0xff; mn = x & 0x7fffff; s = -1 if x >> 31 else 1
    if ex == 0xff:
        return 'nan' if mn else ('inf', s)
    v = Fraction(mn, 1 << 149) if ex == 0 else Fraction(mn | 0x800000, 1) * Fraction(2)**(ex-150)
    return s*v


def round32(v, mode, sign_if_zero):
    """Round a non-zero Fraction (or exact zero with the given sign) to f32 bits in mode."""
    if v == 0:
        return sign_if_zero
    s = S32 if v < 0 else 0
    a = abs(v)
    e = a.numerator.bit_length() - a.denominator.bit_length()
    if Fraction(2)**e > a:
        e -= 1
    e = max(e, -126)
    q = Fraction(2)**(e-23)                      # quantum at this binade (subnormal quantum 2^-149)
    n = a / q
    fl = n.numerator // n.denominator
    rem = n - fl
    if mode == 'rn':
        up = rem > Fraction(1, 2) or (rem == Fraction(1, 2) and fl & 1)
    elif mode == 'rz':
        up = False
    elif mode == 'rp':
        up = rem > 0 and not s
    else:
        up = rem > 0 and bool(s)
    k = fl + up
    val = k*q
    if val >= Fraction(2)**128:
        to_inf = mode == 'rn' or (mode == 'rp' and not s) or (mode == 'rm' and s)
        return s | (0x7f800000 if to_inf else 0x7f7fffff)
    bits = struct.unpack('<I', struct.pack('<f', float(val)))[0]   # exact: val is representable
    return s | bits


def ref_fma32(a, b, c, mode='rn'):
    va, vb, vc = f32val(a), f32val(b), f32val(c)
    if 'nan' in (va, vb, vc) or isinstance(va, str) or isinstance(vb, str) or isinstance(vc, str):
        if va == 'nan' or vb == 'nan' or vc == 'nan':
            return CANON_NAN
    ia, ib, ic = isinstance(va, tuple), isinstance(vb, tuple), isinstance(vc, tuple)
    sa, sb, sc = a >> 31, b >> 31, c >> 31
    za = not ia and va == 0; zb = not ib and vb == 0
    if (ia and zb) or (ib and za):
        return CANON_NAN
    if ia or ib:
        sp = sa ^ sb
        if ic and vc[1] != (-1 if sp else 1):
            return CANON_NAN
        return (sp << 31) | 0x7f800000
    if ic:
        return c & S32 | 0x7f800000
    p = va*vb
    exact = p + vc
    if exact == 0:
        pz = va == 0 or vb == 0
        if pz and vc == 0:
            sp = sa ^ sb
            zs = (sp & sc) if mode != 'rm' else (sp | sc)
            return zs << 31
        return S32 if mode == 'rm' else 0
    return round32(exact, mode, 0)


def ref_div32(a, b, mode='rn'):
    va, vb = f32val(a), f32val(b)
    sign = (a ^ b) & S32
    if va == 'nan' or vb == 'nan':
        return CANON_NAN
    ia, ib = isinstance(va, tuple), isinstance(vb, tuple)
    if ia and ib:
        return CANON_NAN
    if ia:
        return sign | 0x7f800000
    if ib:
        return sign
    if vb == 0:
        return CANON_NAN if va == 0 else sign | 0x7f800000
    if va == 0:
        return sign
    return round32(va/vb, mode, 0)


def run1(P, ins, outs, values):
    g = P.run(values)
    return [g(o) for o in outs]


if __name__ == '__main__':
    P = Prog()
    a, b, c = P.input('a'), P.input('b'), P.input('c')
    r = ffma32(P, a, b, c, 'rn')
    lines, loc, used = emit(P, {'a': 8, 'b': 9, 'c': 10}, [r])
    print(len(P.ops), 'ops,', len(lines), 'instructions, registers up to r%d' % (used-1))
