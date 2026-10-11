#!/usr/bin/env python3
"""Identify convert modes (bits 16-21) from two run_drm_bitflip records (r6 = halves floats, r6 = hashed ints).
A candidate must reproduce every lane of both input sets bit-exactly (rte rounding of the base form)."""
import json
import math
import struct
import sys

f32 = lambda u: struct.unpack('<f', struct.pack('<I', u & 0xffffffff))[0]
F32 = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]


def f16bits(x):
    try:
        return struct.unpack('<H', struct.pack('<e', x))[0]
    except OverflowError:
        return 0x7c00 if x > 0 else 0xfc00


def rne(x):
    return float(round(x))  # Python round is half-to-even


def sat(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def tof(v):
    try:
        return F32(float(v))
    except OverflowError:
        return 0x7f800000


def sx(v, bits):
    v &= (1 << bits)-1
    return v-(1 << bits) if v >> (bits-1) else v


CANDS = {}
for bits in (8, 16, 32):
    CANDS[f'u{bits}_to_f'] = lambda u, b=bits: tof(u & ((1 << b)-1))
    CANDS[f's{bits}_to_f'] = lambda u, b=bits: tof(sx(u, b))
    CANDS[f'u{bits}h_to_f'] = lambda u, b=bits: tof((u >> 16) & ((1 << b)-1)) if b < 32 else None
    for rnd, fn in (('rtz', math.trunc), ('rte', rne)):
        def fu(u, b=bits, fn=fn):
            x = f32(u)
            if x != x: return 0
            return int(sat(fn(x), 0, (1 << b)-1)) & 0xffffffff
        def fs(u, b=bits, fn=fn):
            x = f32(u)
            if x != x: return 0
            return int(sat(fn(x), -(1 << (b-1)), (1 << (b-1))-1)) & 0xffffffff
        CANDS[f'f_to_u{bits}_{rnd}'] = fu
        CANDS[f'f_to_s{bits}_{rnd}'] = fs
def tof_rtz(v):
    v = int(v)
    if v == 0: return 0
    sign = v < 0; m = abs(v); e = m.bit_length()-1
    if e > 23: m = (m >> (e-23)) << (e-23)    # truncate to 24 significant bits
    return F32(-float(m) if sign else float(m))
for bits in (8, 16, 32):
    CANDS[f'u{bits}_to_f_rtz'] = lambda u, b=bits: tof_rtz(u & ((1 << b)-1))
    CANDS[f's{bits}_to_f_rtz'] = lambda u, b=bits: tof_rtz(sx(u, b))
CANDS['f32_to_f16'] = lambda u: f16bits(f32(u))
CANDS['f16_to_f32'] = lambda u: F32(struct.unpack('<e', struct.pack('<H', u & 0xffff))[0])
CANDS['identity'] = lambda u: u
CANDS['zero'] = lambda u: 0


def load(path):
    st = json.load(open(path))
    base = next(r for r in st['results'] if r['name'].endswith('-base-A'))
    x = base['table'][7]
    out = {}
    for r in st['results']:
        if r['layout'] != 'A' or r['key'] == 'ref': continue
        n = int.from_bytes(bytes.fromhex(r['cand'])[-6:], 'little')
        out[n] = ('FAULT' if r['fault'] else r['table'][6])
    return x, out


def main(p_h, p_i, mask16=False):
    xh, oh = load(p_h); xi, oi = load(p_i)
    rows = []
    for n in sorted(oh):
        mode, rnd = n >> 16 & 63, n >> 26 & 3
        extra = n & ((0xf << 22) | (3 << 38) | (3 << 42))
        if oh[n] == 'FAULT' or oi.get(n) == 'FAULT':
            rows.append((mode, rnd, extra, 'FAULT')); continue
        hits = []
        for name, fn in CANDS.items():
            ok = True
            for x, o in ((xh, oh[n]), (xi, oi[n])):
                for u, v in zip(x, o):
                    w = fn(u)
                    if w is None or (w & 0xffffffff) != v and not (name.endswith('f16') and (w & 0xffff) == (v & 0xffff)):
                        ok = False; break
                if not ok: break
            if ok: hits.append(name)
        rows.append((mode, rnd, extra, hits or [hex(v) for v in oh[n][:4]]))
    return rows


if __name__ == '__main__':
    for mode, rnd, extra, hits in main(sys.argv[1], sys.argv[2]):
        print(f'mode={mode:2d} ({mode:06b}) round={rnd} extra={extra:#x}: {hits}')


def model(mode, direction, u):
    """Structural convert model. mode bits: 0 signed, 1 rounding (0 rtz, 1 rte), 2-3 width (8/16/32/32-wrap),
    4-5 ignored. direction = encoding bit 26 (0 float->int, 1 int->float). Returns None where not modelled."""
    s, r, w = mode & 1, mode >> 1 & 1, mode >> 2 & 3
    if direction == 0:
        x = f32(u)
        if x != x or x in (float('inf'), float('-inf')): return None
        v = (rne(x) if w < 3 else math.floor(x+0.5)) if r else math.trunc(x)   # width 3 rounds half up
        if w < 3:
            bits = (8, 16, 32)[w]
            v = sat(v, -(1 << (bits-1)), (1 << (bits-1))-1) if s else sat(v, 0, (1 << bits)-1)
            return int(v) & ((1 << bits)-1)
        if not s and v < 0: return None              # unsigned wrap of negatives: see README
        if abs(x) >= 2**31: return None              # out-of-range pattern not modelled (not saturated)
        return int(v) & 0xffffffff
    if w < 3:
        bits = (8, 16, 32)[w]
        v = sx(u, bits) if s else u & ((1 << bits)-1)
    else:
        v = -(u & 0xffffffff) if (s and u >> 31 & 1) else u & 0xffffffff
    return (tof if r else tof_rtz)(v)


def check_model(paths):
    """paths: list of (record, direction). Returns (checked lanes, mismatches)."""
    n_ok = n_bad = 0; bad = []
    for path, d in paths:
        x, o = load(path)
        for n, out in o.items():
            if out == 'FAULT' or n & ((0xf << 22) | (3 << 38) | (3 << 42)) or (n >> 26 & 3) != d: continue
            mode = n >> 16 & 63
            for u, v in zip(x, out):
                w = model(mode, d, u)
                if w is None: continue
                if w == v: n_ok += 1
                else: n_bad += 1; bad.append((mode, d, hex(u), hex(v), hex(w)))
    return n_ok, n_bad, bad[:10]
