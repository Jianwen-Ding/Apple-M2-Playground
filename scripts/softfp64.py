#!/usr/bin/env python3
"""Software IEEE binary64 (fp64) from AGX 32-bit integer instructions: a small DSL, a Python interpreter with the exact
AGX integer semantics used, and an emitter to AGX assembly (safe-ops only: iadd/isub/imadd, bitops, extr, ffs, icmpsel,
mov_imm). Straight-line, branch-free code. round-to-nearest-even, subnormal inputs and outputs, +-inf, NaN.

  P = Prog(); r_hi, r_lo = fmul64(P, (a_hi, a_lo), (b_hi, b_lo))
  P.run({...}) interprets; P.emit(...) assigns registers (linear scan, pairs for imadd results) and returns instructions.
"""
import sys

M32 = 0xffffffff
S32 = 0x80000000


def s32(x):
    return x - (1 << 32) if x & S32 else x


class V:
    """A virtual register (32-bit) or a projection of a pair."""
    __slots__ = ('id', 'pair', 'half')

    def __init__(self, id, pair=None, half=None):
        self.id, self.pair, self.half = id, pair, half


class Prog:
    def __init__(self):
        self.ops = []          # (kind, dst V or None, args tuple)
        self.n = 0
        self.consts = {}

    def v(self, **kw):
        self.n += 1
        return V(self.n, **kw)

    def op(self, kind, *args, dst=True):
        d = self.v() if dst else None
        self.ops.append((kind, d, args))
        return d

    # ---- sources: python ints become immediates when small, constant registers otherwise
    def reg(self, x):
        if isinstance(x, V):
            return x
        x &= M32
        if x not in self.consts:
            self.consts[x] = self.op('imm', x)
        return self.consts[x]

    def src(self, x):
        if isinstance(x, V):
            return x
        x &= M32
        return x if x <= 0xff else self.reg(x)

    # ---- instructions
    def input(self, name):
        return self.op('input', name)

    def add(self, a, b): return self.op('add', self.reg(a), self.src(b))
    def sub(self, a, b): return self.op('sub', self.reg(a), self.src(b))
    def and_(self, a, b): return self.op('and', self.reg(a), self.src(b))
    def or_(self, a, b): return self.op('or', self.reg(a), self.src(b))
    def xor(self, a, b): return self.op('xor', self.reg(a), self.src(b))
    def mullo(self, a, b): return self.op('mullo', self.reg(a), self.src(b))

    def sel(self, cc, a, b, x, y):
        """D = (a cc b) ? x : y ; cc in ueq ult ugt slt sgt."""
        return self.op('sel', cc, self.reg(a), self.src(b), self.src(x), self.src(y))

    def extr(self, lo, hi, s):
        """((hi << 32 | lo) >> s) & 0xffffffff, s < 128."""
        return self.op('extr', self.reg(lo), self.src(hi), self.src(s))

    def ffs(self, a): return self.op('ffs', self.reg(a))

    def mulw(self, a, b):
        """32 x 32 -> 64 unsigned product: returns (lo, hi)."""
        p = self.op('mulw', self.reg(a), self.reg(b))
        lo, hi = self.v(pair=p, half=0), self.v(pair=p, half=1)
        return lo, hi

    # ---- helpers
    def lsr(self, a, s): return self.extr(a, 0, s)
    def flag(self, cc, a, b): return self.sel(cc, a, b, 1, 0)

    def clz32(self, a):
        return self.sub(31, self.ffs(a))       # ffs = index of the highest set bit, -1 for 0 -> clz 32

    def sel2(self, cc, a, b, x, y):
        return (self.sel(cc, a, b, x[0], y[0]), self.sel(cc, a, b, x[1], y[1]))

    def lsl64(self, hi, lo, d):
        """(hi:lo) << d for 0 <= d <= 63."""
        t = self.sub(32, d)
        small = self.flag('ult', d, 32)
        hi_s = self.extr(lo, hi, t)
        lo_s = self.extr(0, lo, t)
        t2 = self.sub(64, d)
        hi_l = self.extr(0, lo, t2)
        return (self.sel('ugt', small, 0, hi_s, hi_l), self.sel('ugt', small, 0, lo_s, 0))

    def lsr64(self, hi, lo, d):
        """(hi:lo) >> d for 0 <= d <= 63."""
        return (self.extr(hi, 0, d), self.extr(lo, hi, d))

    def add64(self, a, b):
        """(hi, lo) + (hi, lo), carry out dropped."""
        lo = self.add(a[1], b[1])
        c = self.flag('ult', lo, a[1])
        return (self.add(self.add(a[0], b[0]), c), lo)

    # ---- interpreter
    def run(self, inputs):
        val = {}
        pairs = {}

        def g(x):
            if isinstance(x, int):
                return x
            if x.pair is not None:
                return pairs[x.pair.id][x.half]
            return val[x.id]

        for kind, d, a in self.ops:
            if kind == 'input':
                val[d.id] = inputs[a[0]] & M32
            elif kind == 'imm':
                val[d.id] = a[0]
            elif kind == 'add':
                val[d.id] = (g(a[0]) + g(a[1])) & M32
            elif kind == 'sub':
                val[d.id] = (g(a[0]) - g(a[1])) & M32
            elif kind == 'and':
                val[d.id] = g(a[0]) & g(a[1])
            elif kind == 'or':
                val[d.id] = g(a[0]) | g(a[1])
            elif kind == 'xor':
                val[d.id] = g(a[0]) ^ g(a[1])
            elif kind == 'mullo':
                val[d.id] = (g(a[0]) * g(a[1])) & M32
            elif kind == 'mulw':
                p = g(a[0]) * g(a[1])
                pairs[d.id] = (p & M32, p >> 32)
            elif kind == 'sel':
                cc, x, y = a[0], g(a[1]), g(a[2])
                c = {'ueq': x == y, 'ult': x < y, 'ugt': x > y, 'slt': s32(x) < s32(y), 'sgt': s32(x) > s32(y)}[cc]
                val[d.id] = g(a[3]) if c else g(a[4])
            elif kind == 'extr':
                sh = g(a[2]) & 0x7f
                val[d.id] = (((g(a[1]) << 32) | g(a[0])) >> sh) & M32
            elif kind == 'ffs':
                x = g(a[0])
                val[d.id] = M32 if x == 0 else (x.bit_length() - 1)
            else:
                raise ValueError(kind)
        return g


def unpack(P, hi, lo):
    """-> dict(sign, e, mh, ml, nan, inf, zero): e = effective biased exponent after normalising the 53-bit mantissa."""
    sign = P.and_(hi, S32)
    ex = P.and_(P.lsr(hi, 20), 0x7ff)
    mh0 = P.and_(hi, 0xfffff)
    nz_m = P.or_(mh0, lo)
    mant_zero = P.flag('ueq', nz_m, 0)
    exp_zero = P.flag('ueq', ex, 0)
    exp_max = P.flag('ueq', ex, 0x7ff)
    nan = P.and_(exp_max, P.sub(1, mant_zero))
    inf = P.and_(exp_max, mant_zero)
    zero = P.and_(exp_zero, mant_zero)
    mh = P.sel('ueq', ex, 0, mh0, P.or_(mh0, 0x100000))
    # leading zeros of the 64-bit (mh:lo); normals have 11 (hidden bit at 52), so the shift is 0 for them
    lz = P.sel('ueq', mh, 0, P.add(P.clz32(lo), 32), P.clz32(mh))
    s = P.sub(lz, 11)
    s = P.sel('slt', s, 0, 0, s)                 # zero mantissa / garbage lanes: keep the shift in range
    s = P.sel('sgt', s, 63, 63, s)
    nmh, nml = P.lsl64(mh, lo, s)
    e = P.sub(P.sel('ueq', ex, 0, 1, ex), s)
    return dict(sign=sign, e=e, mh=nmh, ml=nml, nan=nan, inf=inf, zero=zero)


def round_pack(P, sign, e, mh, ml, g, st):
    """Pack a 53-bit mantissa (mh:ml, bit 52 set) with guard / sticky bits and biased exponent e (signed, may be <= 0)
    into (hi, lo): subnormal shift, round to nearest even, overflow to inf. Does not look at NaN/inf/zero operands."""
    # Y = m53 << 1 | guard as a 54-bit value (yh:yl); shift right by d = 1 - e when e <= 0
    yl = P.or_(P.extr(0, ml, 31), g)                         # ml << 1 | g
    yh = P.extr(ml, mh, 31)                                  # mh << 1 | ml >> 31
    sub = P.flag('slt', e, 1)
    d = P.sel('ugt', sub, 0, P.sub(1, e), 0)
    d = P.sel('sgt', d, 63, 63, d)
    zh, zl = P.lsr64(yh, yl, d)
    # lost bits: Y != (Y >> d) << d
    bh, bl = P.lsl64(zh, zl, d)
    lost = P.flag('ugt', P.or_(P.xor(bh, yh), P.xor(bl, yl)), 0)
    st2 = P.or_(st, lost)
    m_lo = P.extr(zl, zh, 1)                                 # Y >> 1
    m_hi = P.lsr(zh, 1)
    g2 = P.and_(zl, 1)
    lsb = P.and_(m_lo, 1)
    up = P.and_(g2, P.or_(st2, lsb))
    lo = P.add(m_lo, up)
    carry = P.flag('ult', lo, m_lo)
    e_eff = P.sel('ugt', sub, 0, 1, e)
    hi = P.add(P.add(P.mullo(P.sub(e_eff, 1), 0x100000), m_hi), carry)
    over = P.or_(P.flag('sgt', e, 0x7fe), P.flag('ugt', hi, 0x7fefffff))
    hi = P.sel('ugt', over, 0, 0x7ff00000, hi)
    lo = P.sel('ugt', over, 0, 0, lo)
    return P.or_(hi, sign), lo


def mul_core(P, ua, ub):
    """Exact 106-bit product of two unpacked operands, normalised so that bit 105 is set (words w0..w3, little endian),
    with the biased exponent of its leading bit. Returns (words, e, sign)."""
    sign = P.xor(ua['sign'], ub['sign'])
    p0l, p0h = P.mulw(ua['ml'], ub['ml'])
    p1l, p1h = P.mulw(ua['ml'], ub['mh'])
    p2l, p2h = P.mulw(ua['mh'], ub['ml'])
    p3l, p3h = P.mulw(ua['mh'], ub['mh'])
    w0 = p0l
    s1 = P.add(p0h, p1l); c1 = P.flag('ult', s1, p0h)
    s1b = P.add(s1, p2l); c2 = P.flag('ult', s1b, s1)
    w1 = s1b
    s2 = P.add(p1h, p2h); c3 = P.flag('ult', s2, p1h)
    s2b = P.add(s2, p3l); c4 = P.flag('ult', s2b, s2)
    s2c = P.add(s2b, c1); c5 = P.flag('ult', s2c, s2b)
    s2d = P.add(s2c, c2); c6 = P.flag('ult', s2d, s2c)
    w2 = s2d
    w3 = P.add(P.add(P.add(p3h, c3), P.add(c4, c5)), c6)
    top = P.and_(P.lsr(w3, 9), 1)                           # bit 105 set?
    n3 = P.sel('ugt', top, 0, w3, P.extr(w2, w3, 31))
    n2 = P.sel('ugt', top, 0, w2, P.extr(w1, w2, 31))
    n1 = P.sel('ugt', top, 0, w1, P.extr(w0, w1, 31))
    n0 = P.sel('ugt', top, 0, w0, P.extr(0, w0, 31))
    e = P.add(P.sub(P.add(ua['e'], ub['e']), 1023), top)
    return [n0, n1, n2, n3], e, sign


def fmul64(P, a, b):
    ua, ub = unpack(P, *a), unpack(P, *b)
    (n0, n1, n2, n3), e, sign = mul_core(P, ua, ub)
    mh = P.extr(n2, n3, 21)
    ml = P.extr(n1, n2, 21)
    g = P.and_(P.lsr(n1, 20), 1)
    st = P.flag('ugt', P.or_(P.and_(n1, 0xfffff), n0), 0)
    hi, lo = round_pack(P, sign, e, mh, ml, g, st)
    # special operands
    nan = P.or_(P.or_(ua['nan'], ub['nan']), P.or_(P.and_(ua['inf'], ub['zero']), P.and_(ub['inf'], ua['zero'])))
    inf = P.or_(ua['inf'], ub['inf'])
    zero = P.or_(ua['zero'], ub['zero'])
    hi = P.sel('ugt', zero, 0, sign, hi)
    lo = P.sel('ugt', zero, 0, 0, lo)
    hi = P.sel('ugt', inf, 0, P.or_(sign, 0x7ff00000), hi)
    lo = P.sel('ugt', inf, 0, 0, lo)
    hi = P.sel('ugt', nan, 0, 0x7ff80000, hi)
    lo = P.sel('ugt', nan, 0, 0, lo)
    return hi, lo


def fadd64(P, a, b):
    """IEEE binary64 add (round to nearest even), branch-free."""
    # order by magnitude (raw bits are monotonic for non-NaN): x = larger, y = smaller
    ma_h, mb_h = P.and_(a[0], 0x7fffffff), P.and_(b[0], 0x7fffffff)
    gt = P.or_(P.flag('ugt', ma_h, mb_h), P.and_(P.flag('ueq', ma_h, mb_h), P.flag('ugt', a[1], b[1])))
    xh = P.sel('ugt', gt, 0, a[0], b[0]); xl = P.sel('ugt', gt, 0, a[1], b[1])
    yh = P.sel('ugt', gt, 0, b[0], a[0]); yl = P.sel('ugt', gt, 0, b[1], a[1])
    ux, uy = unpack(P, xh, xl), unpack(P, yh, yl)
    d = P.sub(ux['e'], uy['e'])                                  # >= 0
    big = P.flag('ugt', d, 63)
    dc = P.sel('ugt', big, 0, 63, d)
    # X = mx << 9, Y = my << 9 as 64-bit values; align Y right by d with a sticky bit
    Xh, Xl = P.extr(ux['ml'], ux['mh'], 23), P.extr(0, ux['ml'], 23)
    Yh, Yl = P.extr(uy['ml'], uy['mh'], 23), P.extr(0, uy['ml'], 23)
    zh, zl = P.lsr64(Yh, Yl, dc)
    bh, bl = P.lsl64(zh, zl, dc)
    lost = P.flag('ugt', P.or_(P.xor(bh, Yh), P.xor(bl, Yl)), 0)
    nz = P.flag('ugt', P.or_(Yh, Yl), 0)
    zh = P.sel('ugt', big, 0, 0, zh)
    zl = P.sel('ugt', big, 0, 0, zl)
    lost = P.sel('ugt', big, 0, nz, lost)
    zl = P.or_(zl, lost)
    # S = X +- Y'
    sd = P.flag('ueq', P.xor(ux['sign'], uy['sign']), S32)
    m = P.sel('ugt', sd, 0, M32, 0)
    yl2, yh2 = P.xor(zl, m), P.xor(zh, m)
    lo = P.add(Xl, yl2); c1 = P.flag('ult', lo, Xl)
    lo2 = P.add(lo, sd); c2 = P.flag('ult', lo2, lo)
    hi = P.add(P.add(P.add(Xh, yh2), c1), c2)
    szero = P.flag('ueq', P.or_(hi, lo2), 0)
    lz = P.sel('ueq', hi, 0, P.add(P.clz32(lo2), 32), P.clz32(hi))
    lzc = P.sel('ugt', lz, 63, 63, lz)
    nh, nl = P.lsl64(hi, lo2, lzc)
    e = P.sub(P.add(ux['e'], 2), lzc)
    mh = P.lsr(nh, 11)
    ml = P.extr(nl, nh, 11)
    g = P.and_(P.lsr(nl, 10), 1)
    st = P.flag('ugt', P.and_(nl, 0x3ff), 0)
    rhi, rlo = round_pack(P, ux['sign'], e, mh, ml, g, st)
    # exact zero result: -0 only when both operands are -0
    zsign = P.and_(ux['sign'], uy['sign'])
    rhi = P.sel('ugt', szero, 0, zsign, rhi)
    rlo = P.sel('ugt', szero, 0, 0, rlo)
    # inf / NaN operands (the larger operand carries them)
    nan = P.or_(P.or_(ux['nan'], uy['nan']), P.and_(P.and_(ux['inf'], uy['inf']), P.flag('ugt', P.xor(ux['sign'], uy['sign']), 0)))
    inf = P.or_(ux['inf'], uy['inf'])
    rhi = P.sel('ugt', inf, 0, P.or_(ux['sign'], 0x7ff00000), rhi)
    rlo = P.sel('ugt', inf, 0, 0, rlo)
    rhi = P.sel('ugt', nan, 0, 0x7ff80000, rhi)
    rlo = P.sel('ugt', nan, 0, 0, rlo)
    return rhi, rlo


def pick(P, q, vals):
    """vals[q] for q in 0..3 (ints or V), as a select chain."""
    r = vals[3]
    for i in (2, 1, 0):
        r = P.sel('ueq', q, i, vals[i], r)
    return r


def rshift4(P, w, d, big):
    """128-bit right shift of words w (little endian) by d (0..127; `big` = d >= 128 -> all lost). Returns (words, lost flag)."""
    q = P.lsr(d, 5)
    r = P.and_(d, 31)
    W = list(w)+[0, 0, 0, 0]
    out = []
    for k in range(4):
        lo = pick(P, q, [W[k], W[k+1], W[k+2], W[k+3]])
        hi = pick(P, q, [W[k+1], W[k+2], W[k+3], W[k+4]])
        out.append(P.extr(lo, hi, r))
    lost = 0
    for k in range(3):
        lost = P.or_(lost, P.sel('ugt', q, k, w[k], 0)) if k else P.sel('ugt', q, 0, w[0], 0)
    wq = pick(P, q, [w[0], w[1], w[2], w[3]])
    mask = P.extr(M32, 0, P.sub(32, r))
    lost = P.flag('ugt', P.or_(lost, P.and_(wq, mask)), 0)
    nz = P.flag('ugt', P.or_(P.or_(w[0], w[1]), P.or_(w[2], w[3])), 0)
    out = [P.sel('ugt', big, 0, 0, o) for o in out]
    lost = P.sel('ugt', big, 0, nz, lost)
    return out, lost


def lshift4(P, w, sh):
    """128-bit left shift by sh (0..127)."""
    q = P.lsr(sh, 5)
    r = P.and_(sh, 31)
    t = P.sub(32, r)
    W = [0, 0, 0, 0]+list(w)           # W[4+i] = w[i]; index k-q+4
    out = []
    for k in range(4):
        hi = pick(P, q, [W[4+k], W[3+k], W[2+k], W[1+k]])
        lo = pick(P, q, [W[3+k], W[2+k], W[1+k], W[k]])
        out.append(P.extr(lo, hi, t))
    return out


def clz128(P, w):
    c = [P.clz32(x) for x in w]
    r = P.add(c[0], 96)
    for k, base in ((1, 64), (2, 32), (3, 0)):
        r = P.sel('ueq', w[k], 0, r, P.add(c[k], base) if base else c[k])
    return r


def ffma64(P, a, b, c):
    """IEEE binary64 fused multiply-add a*b + c, round to nearest even, branch-free."""
    ua, ub, uc = unpack(P, *a), unpack(P, *b), unpack(P, *c)
    pw, ep, sp = mul_core(P, ua, ub)
    czero = uc['zero']
    pzero = P.or_(ua['zero'], ub['zero'])
    # addend as a 106-bit mantissa (mc << 53) with its exponent; a zero addend gets a very small exponent
    u0 = P.extr(0, uc['ml'], 11)
    u1 = P.extr(uc['ml'], uc['mh'], 11)
    u2 = P.lsr(uc['mh'], 11)
    cw = [0, u0, u1, u2]
    cw = [P.sel('ugt', czero, 0, 0, x) if not isinstance(x, int) else x for x in cw]
    ec = P.sel('ugt', czero, 0, -100000, uc['e'])
    sc = uc['sign']
    # larger exponent (then larger mantissa) is X
    eq = P.flag('ueq', ep, ec)
    gtm = 0
    for k in (0, 1, 2, 3):                                  # lexicographic compare from the lowest word up
        gtm = P.sel('ugt', pw[k], cw[k], 1, P.sel('ult', pw[k], cw[k], 0, gtm))
    pbig = P.or_(P.flag('sgt', ep, ec), P.and_(eq, gtm))
    sel_w = lambda x, y: [P.sel('ugt', pbig, 0, x[i], y[i]) for i in range(4)]
    xw, yw = sel_w(pw, cw), sel_w(cw, pw)
    ex = P.sel('ugt', pbig, 0, ep, ec)
    ey = P.sel('ugt', pbig, 0, ec, ep)
    sx = P.sel('ugt', pbig, 0, sp, sc)
    sy = P.sel('ugt', pbig, 0, sc, sp)
    # X, Y <<= 20: top bit at 125
    def up20(w):
        return [P.extr(0, w[0], 12), P.extr(w[0], w[1], 12), P.extr(w[1], w[2], 12), P.extr(w[2], w[3], 12)]
    X, Y = up20(xw), up20(yw)
    d = P.sub(ex, ey)
    big = P.flag('ugt', d, 127)
    dc = P.sel('ugt', big, 0, 127, d)
    Ys, lost = rshift4(P, Y, dc, big)
    Ys = [P.or_(Ys[0], lost)]+Ys[1:]
    sd = P.flag('ugt', P.xor(sx, sy), 0)
    m = P.sel('ugt', sd, 0, M32, 0)
    carry = sd
    S = []
    for k in range(4):
        t = P.add(X[k], P.xor(Ys[k], m)); c1 = P.flag('ult', t, X[k])
        t2 = P.add(t, carry); c2 = P.flag('ult', t2, t)
        S.append(t2)
        carry = P.or_(c1, c2)
    szero = P.flag('ueq', P.or_(P.or_(S[0], S[1]), P.or_(S[2], S[3])), 0)
    lz = clz128(P, S)
    lzc = P.sel('ugt', lz, 127, 127, lz)
    N = lshift4(P, S, lzc)
    e = P.sub(P.add(ex, 2), lzc)
    mh = P.lsr(N[3], 11)
    ml = P.extr(N[2], N[3], 11)
    g = P.and_(P.lsr(N[2], 10), 1)
    st = P.flag('ugt', P.or_(P.or_(P.and_(N[2], 0x3ff), N[1]), N[0]), 0)
    rhi, rlo = round_pack(P, sx, e, mh, ml, g, st)
    zsign = P.and_(sx, sy)
    rhi = P.sel('ugt', szero, 0, zsign, rhi)
    rlo = P.sel('ugt', szero, 0, 0, rlo)
    # product zero: result is c (both zero: -0 only if both are -0)
    both0 = P.and_(pzero, czero)
    rhi = P.sel('ugt', pzero, 0, P.sel('ugt', czero, 0, P.and_(sp, sc), a_c_hi := c[0]), rhi)
    rlo = P.sel('ugt', pzero, 0, P.sel('ugt', czero, 0, 0, c[1]), rlo)
    # inf / NaN
    pinf = P.or_(ua['inf'], ub['inf'])
    cinf = uc['inf']
    nan = P.or_(P.or_(P.or_(ua['nan'], ub['nan']), uc['nan']),
                P.or_(P.or_(P.and_(ua['inf'], ub['zero']), P.and_(ub['inf'], ua['zero'])),
                      P.and_(P.and_(pinf, cinf), P.flag('ugt', P.xor(sp, sc), 0))))
    inf_hi = P.sel('ugt', pinf, 0, P.or_(sp, 0x7ff00000), P.or_(sc, 0x7ff00000))
    rhi = P.sel('ugt', P.or_(pinf, cinf), 0, inf_hi, rhi)
    rlo = P.sel('ugt', P.or_(pinf, cinf), 0, 0, rlo)
    rhi = P.sel('ugt', nan, 0, 0x7ff80000, rhi)
    rlo = P.sel('ugt', nan, 0, 0, rlo)
    return rhi, rlo


def split(x):
    import struct
    b = struct.unpack('<Q', struct.pack('<d', x))[0]
    return b >> 32, b & M32


def join(hi, lo):
    import struct
    return struct.unpack('<d', struct.pack('<Q', (hi << 32) | lo))[0]


def emit(P, inputs, outputs, first=16, limit=120):
    """Linear-scan register allocation + AGX assembly text.
    inputs: {name: physical 32-bit register index} (already loaded by the caller); outputs: list of V to keep live to the end.
    Returns (lines, {V.id: physical register}, registers_used)."""
    ops = P.ops
    last = {}

    def key(x):
        return x.pair.id if x.pair is not None else x.id
    for i, (kind, d, a) in enumerate(ops):
        for x in a:
            if isinstance(x, V):
                last[key(x)] = i
    for o in outputs:
        last[key(o)] = len(ops)
    free = list(range(first, limit))
    loc = {}
    live = []        # (last_use, regs)
    lines = []
    used = 0

    def alloc(n):
        nonlocal used
        if n == 1:
            r = free.pop(0)
        else:
            r = next(x for x in free if x % 2 == 0 and x+1 in free)
            free.remove(r); free.remove(r+1)
        used = max(used, r+n)
        return r

    def R(x):
        if isinstance(x, int):
            return str(x)
        if x.pair is not None:
            return f'r{loc[x.pair.id]+x.half}'
        return f'r{loc[x.id]}'

    for i, (kind, d, a) in enumerate(ops):
        if kind == 'input':
            loc[d.id] = inputs[a[0]]
            continue
        if kind == 'mulw':
            loc[d.id] = alloc(2)
            width = 2
        else:
            loc[d.id] = alloc(1)
            width = 1
        D = R(d) if kind != 'mulw' else f'r{loc[d.id]}_r{loc[d.id]+1}'
        if kind == 'imm':
            lines.append(f'mov_imm {D}, {a[0]}, 0b0')
        elif kind in ('add', 'sub', 'and', 'or', 'xor'):
            m = {'add': 'iadd', 'sub': 'isub'}.get(kind, kind)
            lines.append(f'{m} {D}, {R(a[0])}, {R(a[1])}')
        elif kind == 'mullo':
            lines.append(f'imadd {D}, {R(a[0])}, {R(a[1])}, 0')
        elif kind == 'mulw':
            lines.append(f'imadd {D}, {R(a[0])}, {R(a[1])}, 0')
        elif kind == 'sel':
            lines.append(f'icmpsel {a[0]}, {D}, {R(a[1])}, {R(a[2])}, {R(a[3])}, {R(a[4])}')
        elif kind == 'extr':
            lines.append(f'extr {D}, {R(a[0])}, {R(a[1])}, {R(a[2])}')
        elif kind == 'ffs':
            lines.append(f'ffs {D}, {R(a[0])}')
        else:
            raise ValueError(kind)
        # free registers whose last use is this op (after emitting, so a dest never aliases a live source)
        for vid, lu in list(last.items()):
            pass
        live.append((last.get(d.id, i), loc[d.id], width))
        still = []
        for lu, r, w in live:
            if lu <= i and not (lu == i and False):
                free.extend(range(r, r+w))
            else:
                still.append((lu, r, w))
        live = still
        free.sort()
    return lines, loc, used


if __name__ == '__main__':
    P = Prog()
    a = (P.input('ah'), P.input('al')); b = (P.input('bh'), P.input('bl'))
    hi, lo = fmul64(P, a, b)
    lines, loc, used = emit(P, {'ah': 8, 'al': 9, 'bh': 10, 'bl': 11}, [hi, lo])
    print(len(P.ops), 'ops,', len(lines), 'instructions, registers up to r%d' % (used-1))


def ref(op, *xs):
    """Host reference with IEEE binary64 semantics: mul / add use the host's doubles; fma is exact (Fractions) with a single
    round to nearest even. A NaN result is returned as nan (matches any NaN)."""
    import math
    from fractions import Fraction
    if op == 'mul':
        return xs[0]*xs[1]
    if op == 'add':
        return xs[0]+xs[1]
    x, y, z = xs
    if any(math.isnan(v) for v in (x, y, z)):
        return math.nan
    if math.isinf(x) or math.isinf(y):
        if x == 0 or y == 0:
            return math.nan
        p = math.copysign(math.inf, x)*math.copysign(1, y)
        if math.isinf(z) and (z > 0) != (p > 0):
            return math.nan
        return p
    if math.isinf(z):
        return z
    ex = Fraction(x)*Fraction(y)+Fraction(z)
    if ex == 0:
        if x*y == 0 and z == 0:
            return -0.0 if (math.copysign(1, x)*math.copysign(1, y) < 0 and math.copysign(1, z) < 0) else 0.0
        return 0.0
    try:
        return float(ex)
    except OverflowError:
        return math.inf if ex > 0 else -math.inf
