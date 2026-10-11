#!/usr/bin/env python3
"""Identify simd_shuf_op encodings (op1 bit 47, op2 bits 38-39, op3 bits 26-27) from two runs:
B = per-lane index (7*lane+3)&31 and B = uniform 3. A = r6 identifies the source lane.
Prints, per encoding, the source lane each lane read (or '-' when the value is not an r6 value)."""
import json
import sys

BASE = 0x5a000606


def src_lanes(out):
    return [(v-BASE)//16 if (v-BASE) % 16 == 0 and 0 <= (v-BASE)//16 < 32 else '-' for v in out]


def cands(B, group):
    g = lambda i: i//group*group
    return {
        'idx': [g(i)+(B[i] % group) for i in range(32)],
        'up': [i-B[i] if (i-B[i]) >= g(i) else None for i in range(32)],
        'down': [i+B[i] if (i+B[i]) < g(i)+group else None for i in range(32)],
        'xor': [g(i)+((i ^ B[i]) % group) for i in range(32)],
        'rot_up': [g(i)+((i-B[i]) % group) for i in range(32)],
        'rot_down': [g(i)+((i+B[i]) % group) for i in range(32)],
    }


def ident(src, B):
    hits = []
    for group, gname in ((4, 'quad'), (32, 'simd')):
        for name, want in cands(B, group).items():
            if all(w is None or s == w for s, w in zip(src, want)) and any(w is not None for w in want):
                oob = sorted({str(s) for s, w in zip(src, want) if w is None})
                hits.append(f'{gname}_{name}' + (f' (out-of-range lanes read {oob})' if oob else ''))
    return hits


def main(p_perm, p_uni):
    out = {}
    for path, tag in ((p_perm, 'perm'), (p_uni, 'uni')):
        st = json.load(open(path))
        base = next(r for r in st['results'] if r['name'] == 'quad_shuffle-base-A')
        B = [v & 0xffff for v in base['table'][8]]
        for r in st['results']:
            if r['layout'] != 'A' or r['key'] != 'quad_shuffle' or r['fault']: continue
            n = int.from_bytes(bytes.fromhex(r['cand'])[-6:], 'little')
            k = (n >> 47 & 1, n >> 38 & 3, n >> 26 & 3)
            src = src_lanes(r['table'][6])
            out.setdefault(k, {})[tag] = (ident(src, B), src)
    return out


if __name__ == '__main__':
    for k, v in sorted(main(*sys.argv[1:3]).items()):
        hp, hu = v['perm'][0], v['uni'][0]
        common = [h for h in hp if h.split(' ')[0] in [x.split(' ')[0] for x in hu]]
        print(f'op1={k[0]} op2={k[1]:02b} op3={k[2]:02b}', common or ('perm:', hp, 'uni:', hu, v['uni'][1][:8]))
