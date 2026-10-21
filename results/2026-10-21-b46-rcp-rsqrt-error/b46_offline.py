#!/usr/bin/env python3
"""B46 offline: maximum error of the hardware rcp / rsqrt / rsqrt_special over every fp32 significand, from the tables
recorded on the M2 Max (AGX-Performance-Simulator testsuite/transcendental/<op>.bin.gz: int8 = hardware bits - bits of
the correctly rounded result, for x = 1.m (rcp) and 1.m, 2.m (rsqrt)). The results scale exactly with the exponent
(record_transcendentals.py checked 65,536 random normal inputs per op), so these figures hold for every normal input
with a normal result. The error is measured against the exact value with integer arithmetic (no float rounding)."""
import gzip, json, sys
from fractions import Fraction
from pathlib import Path
import numpy as np
T = Path('/save/workspace/AGX-Performance-Simulator/testsuite/transcendental')

def table(op):
    d = np.frombuffer(gzip.open(T / f'{op}.bin.gz').read(), dtype=np.int8).astype(np.int64)
    exps = [127] if op == 'rcp' else [127, 128]
    xs = np.concatenate([(np.uint32(e << 23) | np.arange(1 << 23, dtype=np.uint32)) for e in exps])
    x = xs.view(np.float32).astype(np.float64)
    ref = (1.0 / x if op == 'rcp' else 1.0 / np.sqrt(x)).astype(np.float32).view(np.uint32).astype(np.int64)
    return xs, (ref + d).astype(np.uint32), d

def ulp_err_f64(op, xs, hw):
    x = xs.view(np.float32).astype(np.float64); y = hw.view(np.float32).astype(np.float64)
    exact = 1.0 / x if op == 'rcp' else 1.0 / np.sqrt(x)
    ulp = np.ldexp(1.0, (np.frexp(exact)[1] - 24))       # ulp of the exact value's binade
    return (y - exact) / ulp, np.abs(y - exact) / exact

def exact_err(op, xb, hb):
    """ulp error and relative error, exact (Fractions)."""
    x = Fraction(np.float32(np.uint32(xb).view(np.float32)).item()); y = Fraction(np.float32(np.uint32(hb).view(np.float32)).item())
    if op == 'rcp':
        e = y - 1 / x; ex = 1 / x
    else:  # compare y^2 * x with 1 : y - 1/sqrt(x) = (y^2 x - 1) / (x (y + 1/sqrt x)) ~ use high-precision sqrt via integers
        from decimal import Decimal, getcontext
        getcontext().prec = 60
        s = Decimal(x.numerator) / Decimal(x.denominator); r = 1 / s.sqrt()
        ex = Fraction(r); e = y - ex
    k = 0
    while Fraction(2) ** (k + 1) <= abs(ex): k += 1
    while Fraction(2) ** k > abs(ex): k -= 1
    return float(e / Fraction(2) ** (k - 23)), float(abs(e) / ex)

res = {}
for op in ('rcp', 'rsqrt', 'rsqrt_special'):
    xs, hw, d = table(op)
    u, rel = ulp_err_f64(op, xs, hw)
    i = int(np.argmax(np.abs(u))); j = int(np.argmax(rel))
    eu, _ = exact_err(op, xs[i], hw[i]); _, er = exact_err(op, xs[j], hw[j])
    hist = {int(k): int(v) for k, v in zip(*np.unique(d, return_counts=True))}
    res[op] = {'inputs': int(len(xs)), 'max_ulp': round(abs(eu), 4), 'max_ulp_input': f'{int(xs[i]):08x}', 'max_ulp_result': f'{int(hw[i]):08x}',
               'max_rel': er, 'max_rel_log2': round(float(np.log2(er)), 3), 'max_rel_input': f'{int(xs[j]):08x}',
               'not_correctly_rounded': int((d != 0).sum()), 'delta_vs_correctly_rounded': hist,
               'within_2^-19.7_rel': bool(er < 2 ** -19.7)}
    print(op, json.dumps(res[op]), flush=True)
Path('offline.json').write_text(json.dumps(res, indent=1) + '\n')
