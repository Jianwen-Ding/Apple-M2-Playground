#!/usr/bin/env python3
"""B15 offline, fp16: which arithmetic simd_matrix_fmadd16 performs (arith16.json; same layout as fp32, element q is
half q % 2 of lane q // 2's register). Models (exact rational intermediates):
  chain16    acc = C; acc = round16(A B + acc) for k = 0..7 (fp16 fma chain, denormals kept)
  chain32    the same chain rounded to fp32 at each step, rounded to fp16 at the end
  fused16    one rounding to fp16 of the exact sum"""
import json, struct
from fractions import Fraction as F
from pathlib import Path
from b15_arith import rc

def h(bits): return struct.unpack('<e', struct.pack('<H', bits))[0]
def rnd(x, mbits, emin):
    """round a Fraction to the nearest float with mbits fraction bits and minimum normal exponent emin (gradual underflow)"""
    if x == 0: return 0.0
    s = -1 if x < 0 else 1; x = abs(x)
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if F(2) ** e > x: e -= 1
    e = max(e, emin)
    m = x / F(2) ** (e - mbits); n = m.numerator // m.denominator; rem = m - n
    if rem > F(1, 2) or (rem == F(1, 2) and n & 1): n += 1
    return s * float(F(n) * F(2) ** (e - mbits))
def r16(x):
    v = rnd(x, 10, -14)
    return v if abs(v) <= 65504 else (float('inf') if v > 0 else float('-inf'))      # overflow -> inf (round to nearest)
r32 = lambda x: rnd(x, 23, -126)

def mats(words):
    m = [[0.0] * 8 for _ in range(8)]
    for q in range(64):
        r, c = rc(q); m[r][c] = h((words[q // 2] >> (16 * (q % 2))) & 0xffff)
    return m
def chain(rr, final):
    def m(A, B, C, r, c):
        acc = C[r][c]
        for k in range(8):
            if acc != acc or acc in (float('inf'), float('-inf')):
                acc = acc + A[r][k] * B[k][c]        # inf / NaN propagate (products of finite fp16 values are finite)
            else:
                acc = rr(F(A[r][k]) * F(B[k][c]) + F(acc))
        return acc if acc != acc or abs(acc) == float('inf') else final(F(acc))
    return m
models = {'chain16': chain(r16, r16), 'chain32': chain(r32, r16),
          'fused16': lambda A, B, C, r, c: r16(sum(F(A[r][k]) * F(B[k][c]) for k in range(8)) + F(C[r][c]))}
score = {k: 0 for k in models}; total = 0
for s in json.load(open('arith16.json')):
    A, B, C, D = mats(s['a']), mats(s['b']), mats(s['c']), mats(s['d'])
    for r in range(8):
        for c in range(8):
            total += 1
            for k, m in models.items():
                v = m(A, B, C, r, c)
                if v == D[r][c] or (v != v and D[r][c] != D[r][c]): score[k] += 1
print(json.dumps({'elements': total, 'exact_match': score}))
Path('arith16_fit.json').write_text(json.dumps({'elements': total, 'exact_match': score}) + '\n')
