"""Offline check of the device-atomic variant evidence (results/2026-10-17-atomic-variants).

Self-contained: the Mesa encoding formula, the 64-bit and float models are re-implemented here, not imported from
the probe (AGX-Performance-Simulator scripts/probe_atomics.py), so the claims are checked independently of it.
"""
import gzip, hashlib, json, pathlib, struct, sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT/'results/2026-10-17-atomic-variants'
N, S_WORD, M64 = 32, 2048, (1 << 64) - 1
GUARD = 0xcdcdcdcd


def mesa_atomic(op, R_, A, O, S, Rt):
    """agx_pack.c AGX_OPCODE_ATOMIC with uniform base, register index, unsigned, bit 45 clear (G14)"""
    raw = 0x15 | 1 << 26 | 1 << 31 | 5 << 44 | op << 6 | (R_ & 63) << 10 | (A & 15) << 16 | (O & 15) << 20 | 1 << 25 | 1 << 27
    return raw | ((O >> 4) & 15) << 32 | ((A >> 4) & 15) << 36 | (R_ >> 6) << 40 | (1 << 47 if Rt else 0) | S << 48


def mesa_local_atomic(op, R_, A, S, ret):
    """agx_pack.c AGX_OPCODE_LOCAL_ATOMIC: register base, immediate index 0, 10-byte form"""
    raw = 0x19 | 1 << 15 | 1 << 36 | 1 << 47 | (1 << 8 if ret else 0) | (R_ & 63) << 9 | (A & 63) << 16
    return raw | op << 24 | 1 << 34 | (1 << 38 if ret else 0) | (A >> 6) << 58 | (R_ >> 6) << 60 | S << 64


def u2f(x): return struct.unpack('<f', struct.pack('<I', x))[0]


def f32_round(q, neg_zero):
    if q == 0: return 0x80000000 if neg_zero else 0
    s = 1 if q < 0 else 0; q = abs(q)
    e = q.numerator.bit_length() - q.denominator.bit_length()
    while Fraction(2) ** e > q: e -= 1
    while Fraction(2) ** (e + 1) <= q: e += 1
    e = max(e, -126)
    m = q / Fraction(2) ** (e - 23)
    fl = m.numerator // m.denominator; rem = m - fl
    if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and fl & 1): fl += 1
    if fl == 1 << 24: fl >>= 1; e += 1
    if e > 127: return s << 31 | 0x7f800000
    return s << 31 | (fl if fl < 1 << 23 else (e + 127) << 23 | (fl - (1 << 23)))


def fadd(a, b, ftz):
    """float32 a + b, round to nearest even; ftz flushes denormal inputs and results to signed zero; None = NaN"""
    ea, eb = a >> 23 & 255, b >> 23 & 255
    if (ea == 255 and a & 0x7fffff) or (eb == 255 and b & 0x7fffff): return None
    if ftz:
        a, b = (a & 0x80000000 if ea == 0 else a), (b & 0x80000000 if eb == 0 else b)
    if ea == 255 or eb == 255:
        return None if ea == eb == 255 and (a ^ b) >> 31 else (a if ea == 255 else b)
    r = f32_round(Fraction(u2f(a)) + Fraction(u2f(b)), a >> 31 and b >> 31)
    return r & 0x80000000 if ftz and r >> 23 & 255 == 0 else r


def s32(x): return x - (1 << 32) if x >> 31 else x
def s64(x): return x - (1 << 64) if x >> 63 else x


OP32 = {'add': lambda o, v: (o + v) & 0xffffffff, 'sub': lambda o, v: (o - v) & 0xffffffff, 'xchg': lambda o, v: v,
        'umin': min, 'imin': lambda o, v: min(o, v, key=s32), 'umax': max, 'imax': lambda o, v: max(o, v, key=s32),
        'and': lambda o, v: o & v, 'or': lambda o, v: o | v, 'xor': lambda o, v: o ^ v}
OPN = ['add', 'sub', 'xchg', 'cmpxchg', 'umin', 'imin', 'umax', 'imax', 'and', 'or', 'xor']


def main():
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ') + name)
        if not ok: fails.append(name)

    for line in (R/'sources.sha256').read_text().splitlines():
        h, f = line.split()
        check(f'{f} matches the recorded hash', hashlib.sha256((ROOT/f).read_bytes()).hexdigest() == h)
    recs = {r['name']: r for r in json.load(gzip.open(R/'records.json.gz', 'rt'))['records']}
    check('74 recorded dispatch pairs, none faulted', len(recs) == 74 and not any('fault' in r for r in recs.values()))
    check('every pair deterministic except the two contention runs',
          {k for k, r in recs.items() if not r['deterministic']} == {'H_fadd_contend_ones', 'H_fadd_contend_mixed'})

    # encodings: every variant is a Mesa-formula surrogate with only the op field (bits 6-9) or bits 45-46 changed
    enc_ok = True
    for k, r in recs.items():
        v, s = int.from_bytes(bytes.fromhex(r['variant_hex']), 'little'), int.from_bytes(bytes.fromhex(r['surrogate_hex']), 'little')
        if k[0] == 'T':     # threadgroup atomic: Mesa's local_atomic formula plus one gap bit
            enc_ok &= (bin(v ^ s).count('1') == 1 and s == mesa_local_atomic(1, 10, 44, 12, True)
                       and bytes.fromhex(r['code']).find(bytes.fromhex(r['variant_hex'])) >= 0 and r['code'].endswith('8800'))
            continue
        mask = 0xf << 6 if k[0] in 'BDE' else 3 << 45
        f = dict(op=s >> 6 & 15, R_=(s >> 10 & 63) | (s >> 40 & 3) << 6, A=(s >> 16 & 15) | (s >> 36 & 15) << 4,
                 O=(s >> 20 & 15) | (s >> 32 & 15) << 4 | (s >> 56) << 8, S=s >> 48 & 255, Rt=s >> 47 & 1)
        enc_ok &= (v ^ s) & ~mask == 0 and f['A'] == 16 and s == mesa_atomic(**f)
        enc_ok &= bytes.fromhex(r['code']).find(bytes.fromhex(r['variant_hex'])) >= 0 and r['code'].endswith('8800')
    check('each variant = Mesa atomic formula (bit 45 clear, bit 46 set) with only op or bits 45-46 changed; whole program ends in stop', enc_ok)

    pair = lambda t, w: t[w + 1] << 32 | t[w]
    src = lambda t, i: pair(t, S_WORD + 2 * i)

    # Family A: op 3 (cmpxchg) with bit 45 set: 64-bit unsigned min (bit 46 clear) / max (bit 46 set), word index
    for u5, f, name in ((1, min, 'umin64'), (3, max, 'umax64')):
        for rt in (0, 1):
            r = recs[f'A_op3_u5{u5}_rt{rt}']; t0, t1, lanes = r['table_in'], r['table_after'], r['out'][8:8 + N]
            tw = list(t0)
            for i in range(N):
                x = f(pair(t0, 2 * i), src(t0, i)); tw[2 * i], tw[2 * i + 1] = x & 0xffffffff, x >> 32
            mem_ok = tw == t1
            ret = lanes == [0xdeadbeef] * N if rt == 0 else lanes == [int(pair(t0, 2 * i) != pair(t1, 2 * i)) for i in range(N)]
            signed_differs = sum(f(pair(t0, 2 * i), src(t0, i)) != f(pair(t0, 2 * i), src(t0, i), key=s64) for i in range(N))
            check(f'op 3 + u5 = {u5}, Rt = {rt}: {name} on the 64-bit word at base + 4 x index, all 32 lanes '
                  f'({signed_differs} lanes where the signed order would differ); '
                  + ('no register written' if rt == 0 else 'register = 1 if memory changed, else 0'), mem_ok and ret and signed_differs > 0)
    r = recs['I_op3_u50_cas']; t0, t1 = r['table_in'], r['table_after']
    cas32 = all((t1[2 * i], t1[2 * i + 1]) == ((t0[2048 + 4 * i] if t0[2 * i] == t0[2048 + 4 * i + 1] else t0[2 * i]), t0[2 * i + 1]) for i in range(N))
    hit64 = sum((t0[2 * i], t0[2 * i + 1]) == (t0[2048 + 4 * i + 2], t0[2048 + 4 * i + 3]) and t0[2 * i] != t0[2048 + 4 * i + 1] for i in range(N))
    check(f'op 3 + u5 = 0 is the 32-bit cmpxchg (new r6, compare r7) on all 32 lanes; the {hit64} lanes set up for a '
          f'64-bit compare on r8_r9 were not swapped; old low word returned',
          cas32 and hit64 >= 6 and [t1[3100 + i] for i in range(N)] == [t0[2 * i] for i in range(N)])

    # Family F: every other Mesa op ignores bits 45-46, except sub, which becomes float add with bit 45
    f_ok, sub_ok = True, True
    for op in OPN:
        if op == 'cmpxchg': continue
        for u5 in (0, 1, 3):
            r = recs[f'F_{op}_u5{u5}']; t0, t1 = r['table_in'], r['table_after']
            rets = [t1[3100 + i] for i in range(N)]
            fl = op == 'sub' and u5 & 1
            want = [fadd(t0[2 * i], t0[S_WORD + 2 * i], True) if fl else OP32[op](t0[2 * i], t0[S_WORD + 2 * i]) for i in range(N)]
            ok = ([t1[2 * i] for i in range(N)] == want and all(t1[2 * i + 1] == t0[2 * i + 1] for i in range(N))
                  and rets == [t0[2 * i] for i in range(N)] and [t1[3200 + i] for i in range(N)] == [0xdeadbeef] * N)
            if op == 'sub': sub_ok &= ok
            else: f_ok &= ok
    check('add, xchg, umin, imin, umax, imax, and, or, xor with u5 = 0 / 1 / 3: the plain 32-bit op returning the old word (27 variants)', f_ok)
    check('sub with u5 = 0: integer sub; with u5 = 1 or 3: float32 add (old + value, nearest even, denormals flushed), old word returned', sub_ok)

    # Family G: float add edges, 2 x 1024 lanes
    lanes_total = ftz_ok = ieee_bad = nan_ok = ret_ok = 0
    for part in (0, 1):
        r = recs[f'G_fadd_edges{part}']; t0, t1, out = r['table_in'], r['table_after'], r['out'][8:8 + 1024]
        for i in range(1024):
            a, b, got = t0[i], t0[S_WORD + 2 * i], t1[i]
            lanes_total += 1; ret_ok += out[i] == a
            w = fadd(a, b, True)
            if w is None: nan_ok += got == 0x7fc00000; ftz_ok += got == 0x7fc00000
            else: ftz_ok += got == w
            ieee_bad += fadd(a, b, False) != got and w is not None
    check(f'float add over {lanes_total} edge / rounding pairs: all match round-to-nearest-even with denormal inputs and '
          f'results flushed to signed zero ({nan_ok} NaN results, all 0x7fc00000); {ieee_bad} lanes contradict the '
          f'denormal-preserving model; the old word is returned', ftz_ok == lanes_total == ret_ok == 2048 and ieee_bad > 0 and nan_ok > 0)

    # Family H: contention, 1024 lanes on one word
    r = recs['H_fadd_contend_ones']; rets = r['out'][8:8 + 1024]
    check('1024 lanes add 1.0 to one word: final 1024.0, returns are exactly {0.0, 1.0, ..., 1023.0}',
          r['table_after'][0] == 0x44800000 and sorted(u2f(x) for x in rets) == [float(k) for k in range(1024)])
    r = recs['H_fadd_contend_mixed']; t0 = r['table_in']; rets = r['out'][8:8 + 1024]
    pool = {}
    for i, x in enumerate(rets): pool.setdefault(x, []).append(i)
    cur, used = t0[0], 0
    while used < 1024 and pool.get(cur):
        i = pool[cur].pop(); used += 1; cur = fadd(rets[i], t0[S_WORD + 2 * i], True)
    check('1024 lanes add mixed values to one word: the returns form one serial chain from 1.0 to the final value (atomic)',
          used == 1024 and cur == r['table_after'][0])

    # Families B, D, E: ops 11-15
    b_ok = all(recs[f'B_op{op}_rt1']['table_after'] == recs[f'B_op{op}_rt1']['table_in']
               and recs[f'B_op{op}_rt1']['out'][8:8 + N] == [GUARD] * N for op in range(11, 16))
    check('ops 11-15: memory unchanged and the harness store after them never runs (5 ops)', b_ok)
    d_ok = True
    for op in range(11, 16):
        t1 = recs[f'D_op{op}_rt1']['table_after']
        d_ok &= ([t1[3000 + i] for i in range(N)] == [0x11110000 + i for i in range(N)]
                 and all(t1[o + i] == 0 for o in (3100, 3200, 3300) for i in range(N)))
    check('ops 11-15: a store before the op lands in all 32 lanes; nothing after it runs, even after mov_imm r0l, 0', d_ok)

    def groups(name):
        r = recs[name]; t1, out = r['table_after'], r['out'][8:8 + 128]
        g = {}
        for i in range(128):
            k = (i // 64, (i % 64) // 32)
            g.setdefault(k, []).append(t1[3100 + i] == 0x22220000 + i and out[i] != GUARD)
        return {k: (all(v), any(v)) for k, v in g.items()}
    e0, e1, e2 = groups('E_op11_scope'), groups('E_op11_scope_before'), groups('E_op11_scope_before_skip')
    t1b = recs['E_op11_scope_before_skip']['table_after']
    check('op 11 inside an if without jmp_exec_none: every SIMD group issues it and none continues (2 workgroups x 2 groups)',
          all(not a for a, _ in e0.values()) and all(not a for a, _ in e1.values()))
    check("op 11 inside Mesa's if (jmp_exec_none): groups with no active lane finish; the issuing groups end, inactive lanes included",
          all(e2[(w, 0)][0] and not e2[(w, 1)][1] for w in (0, 1)) and all(t1b[3300 + i] == 0x11110000 + i for i in range(128)))
    # Family T: threadgroup atomic sub with one gap bit set
    inert, bit6 = [], None
    for b in [6, 7, 35, 37, 40, 41, 42, 43, 44, 45, 46] + list(range(72, 80)):
        r = recs[f'T_sub_bit{b}']; t0, t1, lanes = r['table_in'], r['table_after'], r['out'][8:8 + N]
        sub = [t1[192 + i] == (t0[i] - t0[64 + i]) & 0xffffffff for i in range(N)]
        if all(sub) and lanes == t0[:N]: inert.append(b)
        if b == 6: bit6 = (t1[192:192 + N] == t0[:N], lanes == [0] * N)
    check(f'threadgroup atomic sub: 18 single gap bits (6-7, 35, 37, 40-46, 72-79 except 6) leave the integer sub and its '
          f'return unchanged: no threadgroup float add among them', inert == [7, 35, 37, 40, 41, 42, 43, 44, 45, 46] + list(range(72, 80)))
    r = recs['T2_sub_bit6_tgdump']; dump = r['table_after'][256:768]; t0 = r['table_in']
    want = [t0[w] if w < N else 0x5a5a0000 + w for w in range(512)]
    check('threadgroup atomic bit 6: returns 0 and no word of the 2 KiB threadgroup memory changes (the access is suppressed)',
          bit6 == (True, True) and dump == want and r['out'][8:8 + N] == [0] * N)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
