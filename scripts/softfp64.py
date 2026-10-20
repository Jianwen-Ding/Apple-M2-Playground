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


def fmul64(P, a, b, mode='rn'):
    ua, ub = unpack(P, *a), unpack(P, *b)
    (n0, n1, n2, n3), e, sign = mul_core(P, ua, ub)
    mh = P.extr(n2, n3, 21)
    ml = P.extr(n1, n2, 21)
    g = P.and_(P.lsr(n1, 20), 1)
    st = P.flag('ugt', P.or_(P.and_(n1, 0xfffff), n0), 0)
    hi, lo = round_pack(P, sign, e, mh, ml, g, st) if mode == 'rn' else round_pack_mode(P, sign, e, mh, ml, g, st, mode)
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


def fadd64(P, a, b, mode='rn'):
    """IEEE binary64 add, branch-free; mode rn (default, the original program) / rz / rm / rp."""
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
    rhi, rlo = round_pack(P, ux['sign'], e, mh, ml, g, st) if mode == 'rn' else round_pack_mode(P, ux['sign'], e, mh, ml, g, st, mode)
    # exact zero result: -0 only when both operands are -0 (rm: -0 unless both are +0)
    zsign = P.and_(ux['sign'], uy['sign']) if mode != 'rm' else P.or_(ux['sign'], uy['sign'])
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


def ffma64(P, a, b, c, mode='rn'):
    """IEEE binary64 fused multiply-add a*b + c, branch-free; mode rn (default) / rz / rm / rp."""
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
    rhi, rlo = round_pack(P, sx, e, mh, ml, g, st) if mode == 'rn' else round_pack_mode(P, sx, e, mh, ml, g, st, mode)
    zsign = P.and_(sx, sy) if mode != 'rm' else P.or_(sx, sy)
    rhi = P.sel('ugt', szero, 0, zsign, rhi)
    rlo = P.sel('ugt', szero, 0, 0, rlo)
    # product zero: result is c (both zero: -0 only if both are -0)
    both0 = P.and_(pzero, czero)
    rhi = P.sel('ugt', pzero, 0, P.sel('ugt', czero, 0, P.and_(sp, sc) if mode != 'rm' else P.or_(sp, sc), a_c_hi := c[0]), rhi)
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


F64_ONE_HI = 0x3ff00000
F32_ONE = 0x3f800000


def sub64(P, a, b):
    """(hi, lo) - (hi, lo), borrow out dropped."""
    lo = P.sub(a[1], b[1])
    br = P.flag('ult', a[1], b[1])
    return (P.sub(P.sub(a[0], b[0]), br), lo)


def shl1(P, hi, lo):
    """(hi:lo) << 1 (low 64 bits)."""
    return (P.extr(lo, hi, 31), P.extr(0, lo, 31))


def shl2(P, hi, lo):
    """(hi:lo) << 2 (low 64 bits)."""
    return (P.extr(lo, hi, 30), P.extr(0, lo, 30))


def round_pack_mode(P, sign, e, mh, ml, g, st, mode='rn'):
    """round_pack with a rounding mode: 'rn' (nearest even), 'rz' (zero), 'rp' (+inf), 'rm' (-inf).
    Overflow goes to infinity except for rz and the non-saturating directed cases, which give max finite."""
    yl = P.or_(P.extr(0, ml, 31), g)                         # ml << 1 | g
    yh = P.extr(ml, mh, 31)                                  # mh << 1 | ml >> 31
    sub = P.flag('slt', e, 1)
    d = P.sel('ugt', sub, 0, P.sub(1, e), 0)
    d = P.sel('sgt', d, 63, 63, d)
    zh, zl = P.lsr64(yh, yl, d)
    bh, bl = P.lsl64(zh, zl, d)
    lost = P.flag('ugt', P.or_(P.xor(bh, yh), P.xor(bl, yl)), 0)
    st2 = P.or_(st, lost)
    m_lo = P.extr(zl, zh, 1)                                 # Y >> 1
    m_hi = P.lsr(zh, 1)
    g2 = P.and_(zl, 1)
    lsb = P.and_(m_lo, 1)
    if mode == 'rn':
        up = P.and_(g2, P.or_(st2, lsb))
    elif mode == 'rz':
        up = 0
    elif mode == 'rp':
        up = P.and_(P.or_(g2, st2), P.xor(P.lsr(sign, 31), 1))
    elif mode == 'rm':
        up = P.and_(P.or_(g2, st2), P.lsr(sign, 31))
    else:
        raise ValueError(mode)
    lo = P.add(m_lo, up)
    carry = P.flag('ult', lo, m_lo)
    e_eff = P.sel('ugt', sub, 0, 1, e)
    hi = P.add(P.add(P.mullo(P.sub(e_eff, 1), 0x100000), m_hi), carry)
    over = P.or_(P.flag('sgt', e, 0x7fe), P.flag('ugt', hi, 0x7fefffff))
    # overflow: infinity, except rz (both signs) and directed rounding away from the overflow direction
    pos = P.xor(P.lsr(sign, 31), 1)
    if mode == 'rn':
        to_inf = 1
    elif mode == 'rz':
        to_inf = 0
    elif mode == 'rp':
        to_inf = pos
    else:
        to_inf = P.sub(1, pos)
    hi = P.sel('ugt', P.and_(over, to_inf), 0, 0x7ff00000, hi)
    lo = P.sel('ugt', P.and_(over, to_inf), 0, 0, lo)
    hi = P.sel('ugt', P.and_(over, P.sub(1, to_inf)), 0, 0x7fefffff, hi)
    lo = P.sel('ugt', P.and_(over, P.sub(1, to_inf)), 0, M32, lo)
    return P.or_(hi, sign), lo


def fdiv64(P, a, b, mode='rn'):
    """IEEE binary64 division (restoring, 55 quotient bits), branch-free. mode in rn/rz/rm/rp."""
    ua, ub = unpack(P, *a), unpack(P, *b)
    sign = P.xor(ua['sign'], ub['sign'])
    nan = P.or_(P.or_(ua['nan'], ub['nan']),
                P.or_(P.and_(ua['inf'], ub['inf']), P.and_(ua['zero'], ub['zero'])))
    notnan = P.sub(1, nan)
    inf = P.and_(P.or_(ua['inf'], ub['zero']), notnan)
    zero = P.and_(P.or_(ua['zero'], ub['inf']), P.sub(1, P.or_(nan, inf)))
    eq = P.add(P.sub(ua['e'], ub['e']), 1023)
    # Integer bit first (the leading 52 iterations provably produce 0: R < D throughout,
    # since D >= 2**52 and R only accumulates i+1 bits by iteration i <= 51).
    q_int = P.sub(1, ult64(P, ua['mh'], ua['ml'], ub['mh'], ub['ml']))
    t = sub64(P, (ua['mh'], ua['ml']), (ub['mh'], ub['ml']))
    Rh = P.sel('ugt', q_int, 0, t[0], ua['mh'])
    Rl = P.sel('ugt', q_int, 0, t[1], ua['ml'])
    # 54 fraction iterations (52 more mantissa bits + guard + round), bringing zero bits.
    Qh, Ql = 0, q_int
    for _ in range(54):
        nRh, nRl = shl1(P, Rh, Rl)
        Rh, Rl = nRh, nRl
        t = sub64(P, (Rh, Rl), (ub['mh'], ub['ml']))
        ge = P.sub(1, ult64(P, Rh, Rl, ub['mh'], ub['ml']))
        Rh = P.sel('ugt', ge, 0, t[0], Rh)
        Rl = P.sel('ugt', ge, 0, t[1], Rl)
        nQh, nQl = shl1(P, Qh, Ql)
        Qh, Ql = nQh, P.or_(nQl, ge)
    # Q holds q54..q0 (value = Q / 2**54 in (0.5, 2)); normalise a leading zero
    topbit = P.and_(P.lsr(Qh, 22), 1)
    sQ = shl1(P, Qh, Ql)
    Qh = P.sel('ugt', topbit, 0, Qh, sQ[0])
    Ql = P.sel('ugt', topbit, 0, Ql, sQ[1])
    eq = P.sel('ugt', topbit, 0, eq, P.sub(eq, 1))
    r = P.and_(Ql, 1)
    st = P.flag('ugt', P.or_(P.or_(r, Rh), Rl), 0)
    mh53, ml53 = P.lsr64(Qh, Ql, 2)
    g = P.and_(P.lsr(Ql, 1), 1)
    hi, lo = round_pack_mode(P, sign, eq, mh53, ml53, g, st, mode)
    hi = P.sel('ugt', zero, 0, sign, hi)
    lo = P.sel('ugt', zero, 0, 0, lo)
    hi = P.sel('ugt', inf, 0, P.or_(sign, 0x7ff00000), hi)
    lo = P.sel('ugt', inf, 0, 0, lo)
    hi = P.sel('ugt', nan, 0, 0x7ff80000, hi)
    lo = P.sel('ugt', nan, 0, 0, lo)
    return hi, lo


def fsqrt64(P, a, mode='rn'):
    """IEEE binary64 square root (binary digit recurrence, 55 root bits), branch-free. mode in rn/rz/rm/rp."""
    u = unpack(P, *a)
    neg = P.lsr(u['sign'], 31)
    bad = P.or_(u['nan'], P.and_(neg, P.sub(1, u['zero'])))   # NaN, or negative (incl -inf); -0 is fine
    rsign = P.sel('ugt', u['zero'], 0, u['sign'], 0)       # sqrt(-0) = -0, else +0
    # Make the unbiased exponent even: E' odd (i.e. e even) -> work with 2*M and E' - 1.
    # The recurrence consumes 55 pairs (two input bits per one root bit) of S0 = Madj << 10;
    # Q holds r54..r0 and the root = (Q >> 2) * 2**(Ep/2 - 26) after the uniform extraction below.
    odd = P.flag('ueq', P.and_(u['e'], 1), 0)
    Madj = P.sel2('ugt', odd, 0, shl1(P, u['mh'], u['ml']), (u['mh'], u['ml']))
    Ep = P.sel('ugt', odd, 0, P.sub(u['e'], 1076), P.sub(u['e'], 1075))
    half = P.or_(P.lsr(Ep, 1), P.and_(Ep, S32))              # Ep even: exact arithmetic shift
    eq = P.add(half, 1049)
    # 55 iterations over pairs (two input bits each, one root bit out); S0's low 8 bits are
    # zero (shift), and pairs past bit 0 read as zero, so nothing is lost and st is exact.
    # Trial divisor for b=1 is (Q << 2) | 1 since (2Q + 1)**2 = 4Q**2 + (4Q + 1).
    Sh, Sl = P.lsl64(Madj[0], Madj[1], 10)
    Qh, Ql, Rh, Rl = 0, 0, 0, 0
    for _ in range(55):
        pair = P.and_(P.lsr(Sh, 30), 3)
        Sh, Sl = shl2(P, Sh, Sl)
        nRh, nRl = shl2(P, Rh, Rl)
        Rh, Rl = nRh, P.or_(nRl, pair)
        nQh, nQl = shl1(P, Qh, Ql)
        tQh, tQl = shl2(P, Qh, Ql)
        t = (tQh, P.or_(tQl, 1))                              # trial divisor (Q << 2) | 1
        ge = P.sub(1, ult64(P, Rh, Rl, t[0], t[1]))
        s = sub64(P, (Rh, Rl), t)
        Rh = P.sel('ugt', ge, 0, s[0], Rh)
        Rl = P.sel('ugt', ge, 0, s[1], Rl)
        Qh, Ql = nQh, P.or_(nQl, ge)
    # 53-bit mantissa (bit 52 set in both parities: Q in [2**54, 2**55)), guard/round/sticky
    mh53, ml53 = P.lsr64(Qh, Ql, 2)
    g = P.and_(P.lsr(Ql, 1), 1)
    r = P.and_(Ql, 1)
    st = P.flag('ugt', P.or_(Rh, Rl), 0)
    hi, lo = round_pack_mode(P, 0, eq, mh53, ml53, g, st, mode)
    hi = P.sel('ugt', u['zero'], 0, rsign, hi)
    lo = P.sel('ugt', u['zero'], 0, 0, lo)
    hi = P.sel('ugt', u['inf'], 0, 0x7ff00000, hi)
    lo = P.sel('ugt', u['inf'], 0, 0, lo)
    hi = P.sel('ugt', bad, 0, 0x7ff80000, hi)
    lo = P.sel('ugt', bad, 0, 0, lo)
    return hi, lo


def frcp64(P, a, mode='rn'):
    """IEEE binary64 reciprocal (1/x), via the divider."""
    one = (P.reg(0x3ff00000), P.reg(0))
    return fdiv64(P, one, a, mode)


def cvt_f32_f64(P, a):
    """Exact float32 -> binary64 widening. Input is (hi ignored, lo = f32 bits)."""
    lo = a[1]
    sign = P.and_(lo, S32)
    ex8 = P.and_(P.lsr(lo, 23), 0xff)
    mn = P.and_(lo, 0x7fffff)
    exp0 = P.flag('ueq', ex8, 0)
    expmax = P.flag('ueq', ex8, 0xff)
    mnz = P.flag('ugt', mn, 0)
    zero = P.and_(exp0, P.sub(1, mnz))
    inf = P.and_(expmax, P.sub(1, mnz))
    nan = P.and_(expmax, mnz)
    # normal: e = ex8 + 896, mantissa = (implicit 1 | mn) << 29
    mni = P.or_(mn, 0x800000)
    e_norm = P.add(ex8, 896)
    mh_n = P.lsr(mni, 3)
    ml_n = P.extr(0, mni, 3)
    # subnormal: k = clz32(mn) - 9 leading-zero adjust, mantissa = mn << (k + 30), e = 896 - k
    k = P.sub(P.clz32(mn), 9)
    m_sub = P.lsl64(0, mn, P.add(k, 30))
    e_sub = P.sub(896, k)
    sub = P.and_(exp0, mnz)
    e = P.sel('ugt', sub, 0, e_sub, e_norm)
    mh = P.sel('ugt', sub, 0, m_sub[0], mh_n)
    ml = P.sel('ugt', sub, 0, m_sub[1], ml_n)
    hi = P.add(P.add(sign, P.mullo(P.sub(e, 1), 0x100000)), mh)
    hi = P.sel('ugt', zero, 0, sign, hi)
    lo = P.sel('ugt', zero, 0, 0, ml)
    hi = P.sel('ugt', inf, 0, P.or_(sign, 0x7ff00000), hi)
    lo = P.sel('ugt', inf, 0, 0, lo)
    hi = P.sel('ugt', nan, 0, 0x7ff80000, hi)
    lo = P.sel('ugt', nan, 0, 0, lo)
    return hi, lo


def round_pack_f32(P, sign, e32, m24, g, st, mode):
    """Round a 24-bit mantissa to an f32 (in lo, hi = 0): subnormal shift, directed modes, overflow."""
    sub = P.flag('slt', e32, 1)
    d = P.sel('ugt', sub, 0, P.sub(1, e32), 0)
    d = P.sel('sgt', d, 31, 31, d)
    # Y = m24 << 1 | guard (25 bits); shift right by d, re-derive guard/sticky after the shift
    Y = P.or_(P.extr(0, m24, 31), g)
    Ys = P.lsr(Y, d)
    back = P.extr(0, Ys, P.sub(32, d))
    lost = P.flag('ugt', P.xor(back, Y), 0)
    st2 = P.or_(st, lost)
    m = P.lsr(Ys, 1)
    g2 = P.and_(Ys, 1)
    e_eff = P.sel('ugt', sub, 0, 1, e32)
    lsb = P.and_(m, 1)
    if mode == 'rn':
        up = P.and_(g2, P.or_(st2, lsb))
    elif mode == 'rz':
        up = 0
    elif mode == 'rp':
        up = P.and_(P.or_(g2, st2), P.xor(P.lsr(sign, 31), 1))
    else:
        up = P.and_(P.or_(g2, st2), P.lsr(sign, 31))
    r = P.add(m, up)
    carry = P.lsr(r, 24)
    r = P.and_(r, 0xffffff)
    e_out = P.add(e_eff, carry)
    over = P.flag('sgt', e_out, 254)
    pos = P.xor(P.lsr(sign, 31), 1)
    if mode == 'rn':
        to_inf = 1
    elif mode == 'rz':
        to_inf = 0
    elif mode == 'rp':
        to_inf = pos
    else:
        to_inf = P.sub(1, pos)
    fin = P.add(P.add(sign, P.mullo(P.add(P.sub(e_out, 1), carry), 0x800000)), r)
    fin = P.sel('ugt', P.and_(over, to_inf), 0, P.or_(sign, 0x7f800000), fin)
    fin = P.sel('ugt', P.and_(over, P.sub(1, to_inf)), 0, P.or_(sign, 0x7f7fffff), fin)
    return P.reg(0), fin


def cvt_f64_f32(P, a, mode='rn'):
    """Binary64 -> float32 (in lo, hi = 0) with rounding mode."""
    u = unpack(P, *a)
    nan = u['nan']
    inf = u['inf']
    zero = u['zero']
    e32 = P.sub(u['e'], 896)
    _, m24 = P.lsr64(u['mh'], u['ml'], 29)
    g = P.and_(P.lsr(u['ml'], 28), 1)
    st = P.flag('ugt', P.and_(u['ml'], 0xfffffff), 0)
    _, out = round_pack_f32(P, u['sign'], e32, m24, g, st, mode)
    # specials override: NaN -> canonical f32, inf -> inf, zero -> signed zero
    out = P.sel('ugt', zero, 0, u['sign'], out)
    out = P.sel('ugt', inf, 0, P.or_(u['sign'], 0x7f800000), out)
    out = P.sel('ugt', nan, 0, 0x7fc00000, out)
    return P.reg(0), out


def cvt_int_f64(P, a, unsigned):
    """Exact 32-bit integer -> binary64. Input lo word (hi ignored, must be 0); s32 is two's complement."""
    lo = a[1]
    if unsigned:
        neg, mag = 0, lo
    else:
        neg = P.lsr(lo, 31)
        mag = P.sel('ugt', neg, 0, P.sub(0, lo), lo)
    zero = P.flag('ueq', mag, 0)
    lz = P.clz32(mag)
    sh = P.add(lz, 21)
    m53 = P.lsl64(0, mag, sh)
    e = P.sub(1054, lz)
    hi = P.add(P.add(P.extr(0, neg, 1), P.mullo(P.sub(e, 1), 0x100000)), m53[0])
    hi = P.sel('ugt', zero, 0, 0, hi)
    lo = P.sel('ugt', zero, 0, 0, m53[1])
    return hi, lo


def cvt_f64_int(P, a, mode, unsigned):
    """Binary64 -> 32-bit integer (in lo, hi = 0) with rounding mode. Out-of-range saturates,
    NaN gives INT_MIN (s32) or 0 (u32): x86-like, documented as an assumption."""
    u = unpack(P, *a)
    neg = P.lsr(u['sign'], 31)
    E = P.sub(u['e'], 1023)
    Emax = 32 if unsigned else 31
    ov = P.flag('sgt', E, Emax - 1)          # E >= Emax: saturate (also covers inf: E huge)
    ov = P.or_(ov, u['inf'])
    nan = u['nan']
    # E < 0: |x| < 1
    lt0 = P.flag('slt', E, 0)
    eqm1 = P.flag('ueq', E, M32 - 0)         # E == -1 (M32 = 0xffffffff = -1 signed)
    M = (u['mh'], u['ml'])
    ne52 = P.or_(P.sub(1, P.flag('ueq', u['mh'], 0x100000)), P.flag('ugt', u['ml'], 0))  # M != 2**52
    gt_half = P.and_(eqm1, ne52)             # |x| > 0.5 (E == -1 and M != 2**52)
    if mode == 'rn':
        r_small = gt_half
    elif mode == 'rz':
        r_small = 0
    elif mode == 'rm':
        r_small = P.and_(neg, P.sub(1, u['zero']))
    else:  # rp
        r_small = P.and_(P.sub(1, neg), P.sub(1, u['zero']))
    # 0 <= E < Emax: trunc = M >> (52-E), frac = rest
    sh = P.sub(52, E)
    tpair = P.lsr64(u['mh'], u['ml'], sh)
    trunc = tpair[1]
    tback = P.lsl64(0, trunc, sh)
    fpair = sub64(P, M, tback)
    fnz = P.flag('ugt', P.or_(fpair[0], fpair[1]), 0)
    # half = 2**(51-E): compare frac
    k = P.sub(51, E)
    kh = P.extr(0, 1, P.sub(64, k))
    kl = P.extr(0, 1, P.sub(32, k))
    kh = P.sel('ugt', P.flag('slt', E, 20), 0, kh, 0)
    kl = P.sel('ugt', P.flag('sgt', E, 19), 0, kl, 0)
    gt = ult64(P, kh, kl, fpair[0], fpair[1])
    eq = ueq64(P, kh, kl, fpair[0], fpair[1])
    odd = P.and_(trunc, 1)
    if mode == 'rn':
        inc = P.or_(gt, P.and_(eq, odd))
    elif mode == 'rz':
        inc = 0
    elif mode == 'rm':
        inc = P.and_(fnz, neg)
    else:
        inc = P.and_(fnz, P.sub(1, neg))
    mag = P.add(trunc, inc)
    carry = P.flag('ult', mag, trunc)
    # saturate on overflow of the magnitude
    if unsigned:
        mag = P.sel('ugt', carry, 0, M32, mag)
    else:
        toolarge = P.flag('ugt', mag, 0x7fffffff)
        mag = P.sel('ugt', P.and_(toolarge, P.sub(1, neg)), 0, 0x7fffffff, mag)
    r = P.sel('ugt', lt0, 0, r_small, mag)
    # zero input: E very negative, r_small = 0 already (gt_half = 0 since E != -1; rm/rp need ~zero)
    # apply sign / saturate specials
    if unsigned:
        out = P.sel('ugt', P.and_(ov, P.sub(1, neg)), 0, M32, r)
        out = P.sel('ugt', neg, 0, 0, out)
        out = P.sel('ugt', nan, 0, 0, out)
    else:
        out = P.sel('ugt', neg, 0, P.sub(0, r), r)
        out = P.sel('ugt', P.and_(ov, P.sub(1, neg)), 0, 0x7fffffff, out)
        out = P.sel('ugt', P.and_(ov, neg), 0, S32, out)
        out = P.sel('ugt', nan, 0, S32, out)
    return P.reg(0), out


def cvt_s32_f64(P, a):
    """Exact signed 32-bit integer -> binary64."""
    return cvt_int_f64(P, a, False)


def cvt_u32_f64(P, a):
    """Exact unsigned 32-bit integer -> binary64."""
    return cvt_int_f64(P, a, True)


def cvt_f64_s32(P, a, mode='rn'):
    """Binary64 -> signed 32-bit integer (in lo, hi = 0) with rounding mode. Saturates; NaN -> INT_MIN."""
    return cvt_f64_int(P, a, mode, False)


def cvt_f64_u32(P, a, mode='rn'):
    """Binary64 -> unsigned 32-bit integer (in lo, hi = 0) with rounding mode. Saturates; NaN -> 0."""
    return cvt_f64_int(P, a, mode, True)


def f64key(P, hi, lo, zero_fix=True):
    """Monotonic u64 order key for a double (hi, lo words): if sign set, key = ~bits, else key = bits ^ 0x8000...0.
    With zero_fix, +-0 both map to 0x8000000000000000 (for setp); without it -0 < +0 (for min/max)."""
    sx = P.lsr(hi, 31)
    neg = P.flag('ugt', sx, 0)
    mh = P.sel('ugt', neg, 0, M32, 0)
    kh = P.sel('ugt', neg, 0, P.xor(hi, M32), P.xor(hi, S32))
    kl = P.sel('ugt', neg, 0, P.xor(lo, M32), lo)
    if zero_fix:
        mzero = P.flag('ueq', P.or_(P.and_(hi, 0x7fffffff), lo), 0)
        kh = P.sel('ugt', mzero, 0, S32, kh)
        kl = P.sel('ugt', mzero, 0, 0, kl)
    return kh, kl


def f64nan(P, hi, lo):
    ex = P.and_(P.lsr(hi, 20), 0x7ff)
    exp_max = P.flag('ueq', ex, 0x7ff)
    mant_nz = P.flag('ugt', P.or_(P.and_(hi, 0xfffff), lo), 0)
    return P.and_(exp_max, mant_nz)


def ult64(P, ahi, alo, bhi, blo):
    return P.or_(P.flag('ult', ahi, bhi), P.and_(P.flag('ueq', ahi, bhi), P.flag('ult', alo, blo)))


def ueq64(P, ahi, alo, bhi, blo):
    return P.and_(P.flag('ueq', ahi, bhi), P.flag('ueq', alo, blo))


def _cmp_operands(P, a, b):
    ka = f64key(P, a[0], a[1])
    kb = f64key(P, b[0], b[1])
    na = f64nan(P, a[0], a[1]); nb = f64nan(P, b[0], b[1])
    return ka, kb, P.or_(na, nb)


def _pred(P, v):
    return P.sel('ugt', v, 0, F64_ONE_HI, 0), P.sel('ugt', v, 0, 0, 0)


def fcmp_eq(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    return _pred(P, P.and_(ueq64(P, ka[0], ka[1], kb[0], kb[1]), P.sub(1, nan)))


def fcmp_lt(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    return _pred(P, P.and_(ult64(P, ka[0], ka[1], kb[0], kb[1]), P.sub(1, nan)))


def fcmp_gt(P, a, b):
    return fcmp_lt(P, b, a)


def fcmp_le(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    raw = P.or_(ult64(P, ka[0], ka[1], kb[0], kb[1]), ueq64(P, ka[0], ka[1], kb[0], kb[1]))
    return _pred(P, P.and_(raw, P.sub(1, nan)))


def fcmp_ge(P, a, b):
    return fcmp_le(P, b, a)


def fcmp_neu(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    return _pred(P, P.or_(P.sub(1, ueq64(P, ka[0], ka[1], kb[0], kb[1])), nan))


def fcmp_equ(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    return _pred(P, P.or_(ueq64(P, ka[0], ka[1], kb[0], kb[1]), nan))


def fcmp_ltu(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    return _pred(P, P.or_(ult64(P, ka[0], ka[1], kb[0], kb[1]), nan))


def fcmp_leu(P, a, b):
    ka, kb, nan = _cmp_operands(P, a, b)
    raw = P.or_(ult64(P, ka[0], ka[1], kb[0], kb[1]), ueq64(P, ka[0], ka[1], kb[0], kb[1]))
    return _pred(P, P.or_(raw, nan))


def fcmp_gtu(P, a, b):
    return fcmp_ltu(P, b, a)


def fcmp_geu(P, a, b):
    return fcmp_leu(P, b, a)


def fcmp_num(P, a, b):
    na = f64nan(P, a[0], a[1]); nb = f64nan(P, b[0], b[1])
    return _pred(P, P.sub(1, P.or_(na, nb)))


def fcmp_nan(P, a, b):
    na = f64nan(P, a[0], a[1]); nb = f64nan(P, b[0], b[1])
    return _pred(P, P.or_(na, nb))


def _fminmax_pick(P, a, b, is_min):
    ka = f64key(P, a[0], a[1], zero_fix=False)
    kb = f64key(P, b[0], b[1], zero_fix=False)
    na = f64nan(P, a[0], a[1]); nb = f64nan(P, b[0], b[1])
    take_a = ult64(P, ka[0], ka[1], kb[0], kb[1]) if is_min else ult64(P, kb[0], kb[1], ka[0], ka[1])
    take_a = P.or_(take_a, ueq64(P, ka[0], ka[1], kb[0], kb[1]))
    hi = P.sel('ugt', take_a, 0, a[0], b[0])
    lo = P.sel('ugt', take_a, 0, a[1], b[1])
    # a NaN operand loses (both NaN: keep a's bits, accepted as NaN by the checker)
    hi = P.sel('ugt', nb, 0, a[0], hi)
    lo = P.sel('ugt', nb, 0, a[1], lo)
    hi = P.sel('ugt', na, 0, b[0], hi)
    lo = P.sel('ugt', na, 0, b[1], lo)
    return hi, lo


def fcmp_min(P, a, b):
    return _fminmax_pick(P, a, b, True)


def fcmp_max(P, a, b):
    return _fminmax_pick(P, a, b, False)


def _fcmp_setf(P, a, b, rel):
    ka, kb, nan = _cmp_operands(P, a, b)
    if rel == 'lt':
        raw = ult64(P, ka[0], ka[1], kb[0], kb[1])
    elif rel == 'gt':
        raw = ult64(P, kb[0], kb[1], ka[0], ka[1])
    elif rel == 'eq':
        raw = ueq64(P, ka[0], ka[1], kb[0], kb[1])
    elif rel == 'le':
        raw = P.or_(ult64(P, ka[0], ka[1], kb[0], kb[1]), ueq64(P, ka[0], ka[1], kb[0], kb[1]))
    else:
        raw = P.or_(ult64(P, kb[0], kb[1], ka[0], ka[1]), ueq64(P, ka[0], ka[1], kb[0], kb[1]))
    v = P.and_(raw, P.sub(1, nan))
    return P.sel('ugt', v, 0, F32_ONE, 0), P.sel('ugt', v, 0, 0, 0)


def fcmp_set_lt_f(P, a, b):
    return _fcmp_setf(P, a, b, 'lt')


def fcmp_set_gt_f(P, a, b):
    return _fcmp_setf(P, a, b, 'gt')


def fcmp_set_eq_f(P, a, b):
    return _fcmp_setf(P, a, b, 'eq')


FCMP_OPS = ['eq', 'lt', 'gt', 'le', 'ge', 'min', 'max', 'neu', 'equ', 'ltu', 'leu', 'gtu', 'geu', 'num', 'nan',
            'set_lt_f', 'set_gt_f', 'set_eq_f']


def _ref_cmp(name, x, y):
    import math
    na, nb = math.isnan(x), math.isnan(y)
    if name in ('min', 'max'):
        if na and nb:
            return math.nan
        if na:
            return y
        if nb:
            return x
        if x == y:
            if x != 0:
                return x
            nx, ny = math.copysign(1.0, x) < 0, math.copysign(1.0, y) < 0
            if name == 'min':
                return -0.0 if (nx or ny) else 0.0
            return -0.0 if (nx and ny) else 0.0
        return x if (x < y) == (name == 'min') else y
    if name in ('set_lt_f', 'set_gt_f', 'set_eq_f'):
        if na or nb:
            return 0.0
        r = {'set_lt_f': x < y, 'set_gt_f': x > y, 'set_eq_f': x == y}[name]
        # the program writes the *float32* bits 0x3f800000 / 0 into the hi word (lo = 0); return the
        # double with exactly those bits so the generic word check applies
        import struct
        return struct.unpack('<d', struct.pack('<Q', 0x3f80000000000000 if r else 0))[0]
    if name == 'num':
        return 1.0 if not (na or nb) else 0.0
    if name == 'nan':
        return 1.0 if (na or nb) else 0.0
    if na or nb:
        return 1.0 if name in ('neu', 'equ', 'ltu', 'leu', 'gtu', 'geu') else 0.0
    return 1.0 if {'eq': x == y, 'lt': x < y, 'gt': x > y, 'le': x <= y, 'ge': x >= y,
                   'neu': x != y, 'equ': x == y, 'ltu': x < y, 'leu': x <= y, 'gtu': x > y, 'geu': x >= y}[name] else 0.0


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


def _ref_round_frac(q, mode):
    """Round an exact nonzero Fraction to binary64 under mode."""
    import math
    neg = q < 0
    aq = abs(q)
    if aq >= 2**1024:
        if mode == 'rn':
            return float('-inf') if neg else float('inf')
        if mode == 'rz':
            return math.copysign(1.7976931348623157e308, -1.0 if neg else 1.0)
        if mode == 'rp':
            return float('inf') if not neg else -1.7976931348623157e308
        return 1.7976931348623157e308 if not neg else float('-inf')
    if aq < 2**-1074:
        # compare against half a min-subnormal (ties round to even = 0)
        from fractions import Fraction as F
        half = F(1, 2**1075)
        if mode == 'rn':
            return math.copysign(2**-1074 if aq > half else 0.0, -1.0 if neg else 1.0)
        if mode == 'rz':
            return math.copysign(0.0, -1.0 if neg else 1.0)
        if mode == 'rp':
            return math.copysign(2**-1074 if not neg else 0.0, -1.0 if neg else 1.0)
        return math.copysign(0.0 if not neg else 2**-1074, -1.0 if neg else 1.0)
    try:
        v = float(aq)
    except OverflowError:                 # max finite < aq < 2^1024: rn rounds to inf, directed modes see max / inf
        if mode == 'rn':
            return float('-inf') if neg else float('inf')
        v = 1.7976931348623157e308
    from fractions import Fraction as F
    if F(v) == aq:
        return math.copysign(v, -1.0 if neg else 1.0)
    import struct as _st
    vb = _st.unpack('<Q', _st.pack('<d', v))[0]
    lob = _st.unpack('<d', _st.pack('<Q', vb - 1))[0]
    hib = _st.unpack('<d', _st.pack('<Q', vb + 1))[0]
    def toF(c):
        if c == float('inf'):
            return F(10**400)
        if c == float('-inf'):
            return F(-10**400)
        return F(c)
    cands = (v, lob, hib)
    lo = max(c for c in cands if toF(c) <= aq)
    hi = min(c for c in cands if toF(c) >= aq)
    if mode == 'rn':
        dlo, dhi = aq - toF(lo), toF(hi) - aq
        if dlo < dhi:
            return math.copysign(lo, -1.0 if neg else 1.0)
        if dhi < dlo:
            return math.copysign(hi, -1.0 if neg else 1.0)
        import struct as _st
        return math.copysign(lo if (_st.unpack('<Q', _st.pack('<d', lo))[0] & 1) == 0 else hi, -1.0 if neg else 1.0)
    if mode == 'rz':
        return math.copysign(lo, -1.0 if neg else 1.0)
    if mode == 'rp':
        return hi if not neg else -lo
    return lo if not neg else -hi


def _ref_mode2(op, a, b, mode):
    """Exact add / mul under a directed rounding mode (IEEE 754 zero-sign rules)."""
    import math
    from fractions import Fraction
    if math.isnan(a) or math.isnan(b):
        return float('nan')
    if op == 'mul':
        if (math.isinf(a) and b == 0) or (math.isinf(b) and a == 0):
            return float('nan')
        sg = -1.0 if (math.copysign(1, a)*math.copysign(1, b)) < 0 else 1.0
        if math.isinf(a) or math.isinf(b):
            return math.copysign(float('inf'), sg)
        if a == 0 or b == 0:
            return math.copysign(0.0, sg)
        return _ref_round_frac(Fraction(a)*Fraction(b), mode)
    if math.isinf(a) and math.isinf(b):
        return a if (a > 0) == (b > 0) else float('nan')
    if math.isinf(a) or math.isinf(b):
        return a if math.isinf(a) else b
    ex = Fraction(a)+Fraction(b)
    if ex == 0:
        na, nb = math.copysign(1, a) < 0, math.copysign(1, b) < 0
        if a == 0 and b == 0:
            return -0.0 if ((na and nb) if mode != 'rm' else (na or nb)) else 0.0
        return -0.0 if mode == 'rm' else 0.0
    return _ref_round_frac(ex, mode)


def _ref_div(a, b, mode):
    import math
    from fractions import Fraction
    if math.isnan(a) or math.isnan(b):
        return float('nan')
    if (math.isinf(a) and math.isinf(b)) or (a == 0.0 and b == 0.0):
        return float('nan')
    if math.isinf(a):
        return math.copysign(float('inf'), a) * math.copysign(1.0, b)
    if math.isinf(b):
        return math.copysign(0.0, a) * math.copysign(1.0, b)
    if b == 0.0:
        if a == 0.0:
            return math.copysign(0.0, a) * math.copysign(1.0, b)
        return math.copysign(float('inf'), a) * math.copysign(1.0, b)
    if a == 0.0:
        return math.copysign(0.0, a) * math.copysign(1.0, b)
    return _ref_round_frac(Fraction(a) / Fraction(b), mode)


def _ref_sqrt(a, mode):
    import math
    if math.isnan(a):
        return float('nan')
    if a < 0:
        return float('nan')
    if a == 0.0:
        return a
    if math.isinf(a):
        return a
    from fractions import Fraction
    v = math.sqrt(a)
    fv, fa = Fraction(v), Fraction(a)
    if fv * fv == fa:
        return v
    if fv * fv > fa:
        lo, hi = math.nextafter(v, 0.0), v
    else:
        lo, hi = v, math.nextafter(v, float('inf'))
    if mode == 'rn':
        dlo = fa - Fraction(lo) * Fraction(lo)
        dhi = Fraction(hi) * Fraction(hi) - fa
        if dlo < dhi:
            return lo
        if dhi < dlo:
            return hi
        import struct as _st
        return lo if (_st.unpack('<Q', _st.pack('<d', lo))[0] & 1) == 0 else hi
    if mode == 'rz':
        return lo if v > 0 else hi
    if mode == 'rp':
        return hi
    return lo


def _ref_f64_f32(x, mode):
    import math, struct as _st
    if math.isnan(x):
        return float('nan')
    if math.isinf(x) or x == 0.0:
        return x
    from fractions import Fraction
    q, neg, ax = Fraction(x), x < 0, abs(Fraction(x))
    if ax >= 2**128:
        if mode == 'rn':
            return math.copysign(float('inf'), x)
        if mode == 'rz':
            return math.copysign(3.4028234663852886e+38, x)
        if mode == 'rp':
            return float('inf') if not neg else -3.4028234663852886e+38
        return 3.4028234663852886e+38 if not neg else float('-inf')
    if ax < 2**-149:
        from fractions import Fraction as _F
        half = _F(1, 2**150)
        if mode == 'rn':
            return math.copysign(2**-149 if ax > half else 0.0, x)
        if mode == 'rz':
            return math.copysign(0.0, x)
        if mode == 'rp':
            return math.copysign(2**-149 if not neg else 0.0, x)
        return math.copysign(0.0 if not neg else 2**-149, x)
    vb = _st.unpack('<I', _st.pack('<f', float(x)))[0]
    def fb(b):
        return _st.unpack('<f', _st.pack('<I', b & 0xffffffff))[0]
    v = fb(vb)
    cands = {v, fb(vb - 1), fb(vb + 1)}
    def toF(c):
        if c == float('inf'):
            return Fraction(10**400)
        if c == float('-inf'):
            return Fraction(-10**400)
        return Fraction(c)
    below = [c for c in cands if toF(c) <= q]
    above = [c for c in cands if toF(c) >= q]
    lo, hi = max(below, key=float), min(above, key=float)
    if mode == 'rn':
        dlo, dhi = q - toF(lo), toF(hi) - q
        if dlo < dhi:
            return lo
        if dhi < dlo:
            return hi
        return lo if (_st.unpack('<I', _st.pack('<f', lo))[0] & 1) == 0 else hi
    if mode == 'rz':
        return lo if x > 0 else hi
    if mode == 'rp':
        return hi
    return lo


def _ref_i_f64(x, unsigned):
    v = x if unsigned else (x - 2**32 if x & 0x80000000 else x)
    return float(v)


def _ref_f64_i(x, mode, unsigned):
    import math
    from fractions import Fraction
    if math.isnan(x):
        return 0 if unsigned else 0x80000000
    if math.isinf(x):
        if x > 0:
            return 0xffffffff if unsigned else 0x7fffffff
        return 0 if unsigned else 0x80000000
    q = Fraction(x)
    if mode == 'rn':
        lo, hi = math.floor(q), math.ceil(q)
        if lo == hi:
            r = lo
        else:
            dlo, dhi = q - lo, hi - q
            if dlo < dhi:
                r = lo
            elif dhi < dlo:
                r = hi
            else:
                r = lo if lo % 2 == 0 else hi
    elif mode == 'rz':
        r = math.trunc(q)
    elif mode == 'rp':
        r = math.ceil(q)
    else:
        r = math.floor(q)
    if unsigned:
        if r < 0:
            return 0
        if r > 0xffffffff:
            return 0xffffffff
        return r
    if r < -2**31:
        return 0x80000000
    if r > 0x7fffffff:
        return 0x7fffffff
    return r & 0xffffffff


def ref(op, *xs, mode='rn'):
    """Host reference: mul / add / div / sqrt use the host's doubles (correctly rounded); fma is exact (Fractions)
    with a single round to nearest even. A NaN result is returned as nan (matches any NaN). Compare ops return 1.0 /
    0.0 (predicates and set.f32 forms) or the winning operand (min / max, NaN-tolerant like PTX). div / sqrt / rcp
    and the float conversions honour `mode` (rn/rz/rm/rp) via exact rational arithmetic."""
    import math
    from fractions import Fraction
    if op == 'mul':
        return xs[0]*xs[1] if mode == 'rn' else _ref_mode2('mul', *xs, mode)
    if op == 'add':
        return xs[0]+xs[1] if mode == 'rn' else _ref_mode2('add', *xs, mode)
    if op == 'div':
        return _ref_div(*xs, mode)
    if op == 'sqrt':
        return _ref_sqrt(*xs, mode)
    if op == 'rcp':
        return _ref_div(1.0, xs[0], mode)
    if op == 'cvt_f32_f64':
        return xs[0]
    if op == 'cvt_f64_f32':
        return _ref_f64_f32(xs[0], mode)
    if op == 'cvt_s32_f64':
        return _ref_i_f64(xs[0], False)
    if op == 'cvt_u32_f64':
        return _ref_i_f64(xs[0], True)
    if op == 'cvt_f64_s32':
        return _ref_f64_i(xs[0], mode, False)
    if op == 'cvt_f64_u32':
        return _ref_f64_i(xs[0], mode, True)
    if op in ('c_'+n for n in FCMP_OPS):
        return _ref_cmp(op[2:], *xs)
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
        sp, sz = math.copysign(1, x)*math.copysign(1, y) < 0, math.copysign(1, z) < 0
        if x*y == 0 and z == 0:
            return -0.0 if ((sp and sz) if mode != 'rm' else (sp or sz)) else 0.0
        return -0.0 if mode == 'rm' else 0.0
    if mode != 'rn':
        return _ref_round_frac(ex, mode)
    try:
        return float(ex)
    except OverflowError:
        return math.inf if ex > 0 else -math.inf
