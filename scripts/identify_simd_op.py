#!/usr/bin/env python3
"""Identify simd/quad reduction encodings from a run_drm_bitflip record (baseline simd_iadd r5, r6).

The 5-bit Mesa simd_op is rebuilt from bit 28, bits 38-40 and bit 47; kind from bits 29-30.
Each result is matched against reduce / inclusive-prefix / exclusive-prefix over quads and
SIMD groups for integer and float ops (floats: within 2 ulp of the sequential sum/product).
"""
import json
import struct
import sys

f32 = lambda u: struct.unpack('<f', struct.pack('<I', u & 0xffffffff))[0]
s32 = lambda u: u-(1 << 32) if u & 0x80000000 else u
U = 0xffffffff
OPS = {
    'and': (lambda a, b: a & b, U), 'or': (lambda a, b: a | b, 0), 'xor': (lambda a, b: a ^ b, 0),
    'iadd': (lambda a, b: (a+b) & U, 0), 'umin': (min, U), 'umax': (max, 0),
    'smin': (lambda a, b: a if s32(a) <= s32(b) else b, 0x7fffffff), 'smax': (lambda a, b: a if s32(a) >= s32(b) else b, 0x80000000),
    'fadd': ('f', lambda a, b: a+b, 0.0), 'fmul': ('f', lambda a, b: a*b, 1.0),
    'fmin': ('f', min, float('inf')), 'fmax': ('f', max, float('-inf')),
}


def expect(x, op, group, mode):
    spec = OPS[op]
    isf = spec[0] == 'f'
    fn, ident = (spec[1], spec[2]) if isf else spec
    vals = [f32(v) for v in x] if isf else x
    out = []
    for i in range(32):
        g0 = i//group*group
        lanes = list(range(g0, g0+group)) if mode == 'reduce' else list(range(g0, i+1)) if mode == 'incl' else list(range(g0, i))
        acc = ident
        for l in lanes:
            acc = fn(acc, vals[l])
        out.append(acc)
    return out, isf


def match(out, want, isf):
    if not isf:
        return all(o == w for o, w in zip(out, want))
    for o, w in zip(out, want):
        o = f32(o)
        if w in (float('inf'), float('-inf')) or o != o:
            if o != w: return False
            continue
        if abs(o-w) > 2*abs(w)*2**-23+1e-38: return False
    return True


def main(path):
    st = json.load(open(path))
    base = next(r for r in st['results'] if r['name'] == 'simd_iadd-base-A')
    x = base['table'][7]
    n0 = int.from_bytes(bytes.fromhex(base['cand'])[-6:], 'little')
    rows = []
    for r in st['results']:
        if r['layout'] != 'A' or r['key'] != 'simd_iadd' or r['fault']: continue
        n = int.from_bytes(bytes.fromhex(r['cand'])[-6:], 'little')
        op = (n >> 28 & 1) | (n >> 38 & 7) << 1 | (n >> 47 & 1) << 4
        kind = n >> 29 & 3
        other = (n ^ n0) & ~((1 << 28) | (7 << 38) | (1 << 47) | (3 << 29))
        hits = [f'{"quad" if g == 4 else "simd"}_{m}_{o}' for o in OPS for g in (4, 32) for m in ('reduce', 'incl', 'excl')
                if match(r['table'][6], *expect(x, o, g, m))]
        rows.append({'op': op, 'kind': kind, 'other_bits': hex(other), 'matches': hits, 'sample': [hex(v) for v in r['table'][6][:5]]})
    return rows


def combined(paths):
    """Intersect matches over several input sets (same encodings)."""
    sets = [main(p) for p in paths]
    out = []
    for rows in zip(*sets):
        assert len({(r['op'], r['kind'], r['other_bits']) for r in rows}) == 1
        m = set(rows[0]['matches'])
        for r in rows[1:]: m &= set(r['matches'])
        out.append({**rows[0], 'matches': sorted(m), 'samples': [r['sample'] for r in rows]})
    return out


if __name__ == '__main__':
    for row in combined(sys.argv[1:]):
        print(f"op={row['op']:05b} kind={row['kind']} other={row['other_bits']:>6} {row['matches'] or row['samples']}")


def model(op, kind):
    """Structural decoding of the 5-bit simd_op (bit0 = bit 28, bits1-3 = 38-40, bit4 = 47) and kind (bits 29-30)."""
    group = 4 if kind in (0, 2) else 32
    mode = 'reduce' if kind < 2 else 'excl'
    if op & 1:
        f = ('fadd', 'fmul', 'fmin', 'fmax')[op >> 1 & 3]
    elif not op & 16:
        f = ('and', 'or', 'xor', 'and' if mode == 'reduce' else 'zero')[op >> 1 & 3]
    elif not op >> 2 & 1:
        f = 'iadd' if not op >> 1 & 1 else 'or'
    else:
        f = ('u' if op >> 3 & 1 else 's')+('max' if op >> 1 & 1 else 'min')
    return f, group, mode


def model_expect(x, f, group, mode):
    if f == 'zero':
        return [0]*32, False
    if mode == 'excl' and f in ('fmin', 'fmax'):
        want, isf = expect(x, f, group, mode)
        return [float('nan') if i % group == 0 else w for i, w in enumerate(want)], isf
    return expect(x, f, group, mode)


def check_model(path_ints, path_flts):
    """Every encoding in both records must match the model (floats judged on the float set)."""
    res = []
    for path, isset in ((path_ints, 'ints'), (path_flts, 'flts')):
        st = json.load(open(path))
        base = next(r for r in st['results'] if r['name'] == 'simd_iadd-base-A')
        x = base['table'][7]
        for r in st['results']:
            if r['layout'] != 'A' or r['key'] != 'simd_iadd' or r['fault']: continue
            n = int.from_bytes(bytes.fromhex(r['cand'])[-6:], 'little')
            op = (n >> 28 & 1) | (n >> 38 & 7) << 1 | (n >> 47 & 1) << 4; kind = n >> 29 & 3
            f, g, m = model(op, kind)
            if f.startswith('f') and isset == 'ints': continue
            want, isf = model_expect(x, f, g, m)
            if isf:
                ok = all((f32(o) != f32(o)) if w != w else (abs(f32(o)-w) <= 4*abs(w)*2**-23+1e-38) for o, w in zip(r['table'][6], want))
            else:
                ok = r['table'][6] == want
            res.append((isset, op, kind, f, g, m, ok))
    return res
