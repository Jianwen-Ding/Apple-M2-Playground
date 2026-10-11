#!/usr/bin/env python3
"""Classify a run_drm_bitflip.py record: per flipped bit, what changed relative to the baseline.

Classes: same | dest (only r5) | regs (other registers, listed) | length (marker
registers r16..r23 differ, i.e. the instruction swallowed or exposed markers).
For dest/regs, lane 0 and lane 7 values (baseline -> flipped) are shown.
"""
import json
import sys

MARKERS = range(16, 24)


def diff_regs(t0, t1):
    # r0h is never initialized (r0l is the exec counter), so only r0l is compared.
    lo = lambda t, r: [v & 0xffff for v in t[1+r]] if r == 0 else t[1+r]
    return [r for r in range(24) if lo(t0, r) != lo(t1, r)]


def classify(rec_a, rec_b, base_a, base_b):
    ra, rb = diff_regs(base_a['table'], rec_a['table']), diff_regs(base_b['table'], rec_b['table'])
    regs = sorted(set(ra) | set(rb))
    if not regs:
        return 'same', regs
    if any(r in MARKERS for r in regs):
        return 'length', regs
    return ('dest' if regs == [5] else 'regs'), regs


def main(path, as_json=False):
    st = json.load(open(path))
    by = {}
    for r in st['results']:
        by[r['name']] = r
    out = []
    keys = list(dict.fromkeys(r['key'] for r in st['results'] if r['key'] not in ('ref', 'ctrl')))
    ref_a, ref_b = by.get('ref-wait-A'), by.get('ref-wait-B')
    for key in keys:
        ba, bb = by.get(f'{key}-base-A'), by.get(f'{key}-base-B')
        if not ba or not bb or 'table' not in ba or 'table' not in bb:
            continue
        base_vs_ref = diff_regs(ref_a['table'], ba['table']) if ref_a else None
        flips = [r for r in st['results'] if r['key'] == key and r['flip'] and r['layout'] == 'A']
        for fa in flips:
            fb = by.get(fa['name'][:-2]+'-B')
            if not fb or 'table' not in fa or 'table' not in fb:
                out.append({'key': key, 'flip': fa['flip'], 'class': 'fault/incomplete'}); continue
            cls, regs = classify(fa, fb, ba, bb)
            row = {'key': key, 'flip': fa['flip'], 'class': cls, 'regs': regs, 'base_vs_ref': base_vs_ref}
            if cls in ('dest', 'regs', 'length'):
                row['samples'] = {f'r{r}': [[hex(ba['table'][1+r][l]), hex(fa['table'][1+r][l])] for l in (0, 7)] for r in regs[:4]}
            out.append(row)
    if as_json:
        print(json.dumps(out, indent=1))
    else:
        for row in out:
            f = row['flip']; fl = f"b{f['bit']}" if 'bit' in f else (f"m{f['mask']}" if 'mask' in f else (f"r{f['raw']}" if 'raw' in f else f"{f['field']}={f['value']}"))
            print(f"{row['key']:22s} {fl:10s} {row['class']:8s} {row.get('regs', '')} {row.get('samples', '')}")
    return out


if __name__ == '__main__':
    main(sys.argv[1], '--json' in sys.argv)
