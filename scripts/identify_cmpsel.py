#!/usr/bin/env python3
"""Identify icmpsel/fcmpsel condition codes (bits 61-63) from run_drm_bitflip --sweep records.
Baselines select r8 (X) or r9 (Y) by cond(r6, r7). Prints the per-lane predicate as the
matching comparison(s)."""
import json
import struct
import sys

f32 = lambda u: struct.unpack('<f', struct.pack('<I', u & 0xffffffff))[0]
s32 = lambda u: u-(1 << 32) if u & 0x80000000 else u
PRED = {
    'ueq': lambda a, b: a == b, 'ult': lambda a, b: a < b, 'ugt': lambda a, b: a > b, 'ule': lambda a, b: a <= b, 'uge': lambda a, b: a >= b,
    'une': lambda a, b: a != b, 'true': lambda a, b: True, 'false': lambda a, b: False,
}


def main(path, kind):
    st = json.load(open(path))
    rows = []
    for r in st['results']:
        if r['layout'] != 'A' or r['key'] in ('ref',) or r['fault']: continue
        n = int.from_bytes(bytes.fromhex(r['cand'])[-10:], 'little')   # 10-byte long form
        t = r['table']; A, B, X, Y, D = t[7], t[8], t[9], t[10], t[6]
        sel = [True if d == x else False if d == y else None for d, x, y in zip(D, X, Y)]
        conv = (lambda u: u, s32) if kind == 'i' else (f32,)
        hits = []
        for c in conv:
            for name, p in PRED.items():
                if all(s == p(c(a), c(b)) for s, a, b in zip(sel, A, B)):
                    hits.append(name if name in ('true', 'false') else ('s' if c is s32 else 'f' if kind == 'f' else 'u')+name[1:])
        rows.append({'cc': (n >> 61) & 7, 'hits': sorted(set(hits)), 'undetermined_lanes': sel.count(None)})
    return rows


if __name__ == '__main__':
    for row in main(sys.argv[1], sys.argv[2]):
        print(row)
