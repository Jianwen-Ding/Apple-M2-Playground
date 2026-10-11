#!/usr/bin/env python3
"""Identify funop op values from run_drm_bitflip --sweep records (input r6 = 0.37*lane - 3.3).

For each non-faulting op value, compare r5 on every lane with candidate functions
(computed in float64, rounded to float32) and report the best match: exact lanes
and worst relative error. Usage: identify_funop.py record.json [record.json ...]
"""
import json
import math
import struct
import sys

f32 = lambda u: struct.unpack('<f', struct.pack('<I', u & 0xffffffff))[0]
r32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
X = [r32(r32(i*r32(0.37))+r32(-3.3)) for i in range(32)]   # fmadd of the prefix (fused: one rounding)
X = [r32(i*r32(0.37)+r32(-3.3)) for i in range(32)]


def safe(fn):
    def g(x):
        try:
            return fn(x)
        except (ValueError, ZeroDivisionError, OverflowError):
            return float('nan')
    return g


CANDS = {
    'x': lambda x: x, '-x': lambda x: -x, '|x|': abs, 'floor': math.floor, 'ceil': math.ceil, 'trunc': math.trunc,
    'rint': lambda x: float(round(x)), 'rcp': safe(lambda x: 1/x), 'rsqrt': safe(lambda x: 1/math.sqrt(x)),
    'sqrt': safe(math.sqrt), 'log2': safe(math.log2), 'exp2': safe(lambda x: 2**x), 'frac': lambda x: x-math.floor(x),
    'sin(x*pi/2)': lambda x: math.sin(x*math.pi/2), 'cos(x*pi/2)': lambda x: math.cos(x*math.pi/2),
    'rsqrt|x|': safe(lambda x: 1/math.sqrt(abs(x))), 'log2|x|': safe(lambda x: math.log2(abs(x))),
    'rcp|x|': safe(lambda x: 1/abs(x)), '0': lambda x: 0.0,
}
QUAD = {'dfdx(lane^1)': lambda i: X[i ^ 1]-X[i] if i & 1 == 0 else X[i]-X[i ^ 1],
        'dfdy(lane^2)': lambda i: X[i ^ 2]-X[i] if i & 2 == 0 else X[i]-X[i ^ 2]}


def score(out, want):
    exact = 0; worst = 0.0
    for o, w in zip(out, want):
        if math.isnan(w):
            if math.isnan(o): exact += 1
            continue
        if o == r32(w): exact += 1
        else:
            worst = max(worst, abs(o-w)/max(abs(w), 1e-30))
    return exact, worst


def main(paths):
    rows = []
    for path in paths:
        st = json.load(open(path))
        for r in st['results']:
            if r['layout'] != 'A' or not r['flip'] or r['fault']: continue
            out = [f32(v) for v in r['table'][6]]
            best = []
            for n, fn in CANDS.items():
                best.append((score(out, [fn(x) for x in X]), n))
            for n, fn in QUAD.items():
                best.append((score(out, [fn(i) for i in range(32)]), n))
            best.sort(key=lambda t: (-t[0][0], t[0][1]))
            (ex, worst), name = best[0]
            label = r['flip'].get('value', r['flip'].get('mask'))
            rows.append({'value': label, 'best': name, 'exact_lanes': ex, 'worst_rel_err': worst,
                         'second': best[1][1], 'sample': [round(v, 5) for v in out[:6]]})
    return rows


if __name__ == '__main__':
    for row in main(sys.argv[1:]):
        v = row['value']
        print(f"{(format(v, '06b') if isinstance(v, int) else v):>14} {row['best']:14s} exact {row['exact_lanes']:2d}/32 worst {row['worst_rel_err']:.2e}  (2nd {row['second']}) {row['sample']}")
