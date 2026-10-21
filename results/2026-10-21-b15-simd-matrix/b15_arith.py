#!/usr/bin/env python3
"""B15 offline: which arithmetic simd_matrix_fmadd32 performs, from arith32.json (120 random A, B, C sets run on the
GPU). Layout (b15_map.py): element q = 2 lane + slot holds row ((q >> 2) & 3) + 4 (q >> 5), column (q & 3) + 4 ((q >> 4) & 1)
of A, B, C and D. Models of D[r][c] = sum_k A[r][k] B[k][c] + C[r][c], all with exact rational intermediates:
  fused      one rounding of the exact sum
  chain_up   acc = C; acc = fma(A[r][k], B[k][c], acc) for k = 0..7 (one rounding per step)
  chain_down the same for k = 7..0
  tree       products exact, pairwise sums (k0+k1, k2+k3, ...) rounded at each level, then + C rounded
  rounded_products  products rounded to f32, then summed in k order with C first, rounded each step"""
import json, struct
from fractions import Fraction as F
from pathlib import Path

def rc(q): return ((q >> 2) & 3) + 4 * (q >> 5), (q & 3) + 4 * ((q >> 4) & 1)
def f(w): return struct.unpack('<f', struct.pack('<I', w))[0]
def r32(x):
    """round a Fraction to the nearest binary32 (ties to even); flush below the normal range to 0"""
    if x == 0: return 0.0
    s = -1 if x < 0 else 1; x = abs(x)
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if F(2) ** e > x: e -= 1
    if e < -126: return 0.0 * s
    m = x / F(2) ** (e - 23)
    n = m.numerator // m.denominator; rem = m - n
    if rem > F(1, 2) or (rem == F(1, 2) and n & 1): n += 1
    return s * float(F(n) * F(2) ** (e - 23))

def mats(ws):
    m = [[0.0] * 8 for _ in range(8)]
    for q, w in enumerate(ws): r, c = rc(q); m[r][c] = f(w)
    return m

models = {
    'fused': lambda A, B, C, r, c: r32(sum(F(A[r][k]) * F(B[k][c]) for k in range(8)) + F(C[r][c])),
}
def chain(order):
    def m(A, B, C, r, c):
        acc = C[r][c]
        for k in order: acc = r32(F(A[r][k]) * F(B[k][c]) + F(acc))
        return acc
    return m
models['chain_up'] = chain(range(8)); models['chain_down'] = chain(range(7, -1, -1))
def tree(A, B, C, r, c):
    v = [F(A[r][k]) * F(B[k][c]) for k in range(8)]
    while len(v) > 1: v = [F(r32(v[i] + v[i + 1])) for i in range(0, len(v), 2)]
    return r32(v[0] + F(C[r][c]))
models['tree'] = tree
def rp(A, B, C, r, c):
    acc = C[r][c]
    for k in range(8): acc = r32(F(acc) + F(r32(F(A[r][k]) * F(B[k][c]))))
    return acc
models['rounded_products'] = rp

sets = json.load(open('arith32.json'))
score = {k: 0 for k in models}; total = 0; worst = {}
for s in sets:
    A, B, C, D = mats(s['a']), mats(s['b']), mats(s['c']), mats(s['d'])
    for r in range(8):
        for c in range(8):
            total += 1
            for k, m in models.items():
                if m(A, B, C, r, c) == D[r][c]: score[k] += 1
print(json.dumps({'elements': total, 'exact_match': score}))
Path('arith32_fit.json').write_text(json.dumps({'elements': total, 'exact_match': score}) + '\n')
