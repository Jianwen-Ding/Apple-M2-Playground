#!/usr/bin/env python3
"""Offline checks of results/2026-10-11-barrier-0x68-vs-0x78 (run_drm_barrier_stress.py, run_drm_tg_capacity.py)."""
import json
from pathlib import Path
import sys

EV = Path(__file__).resolve().parents[1]/'results/2026-10-11-barrier-0x68-vs-0x78'
checks = []
check = lambda name, ok, detail='': checks.append((name, bool(ok), detail))
load = lambda f: json.loads((EV/f).read_text())


def rows(f):
    d = load(f)
    return d, {r['name']: r for r in d['results']}


def parse(name):
    mem, n, bar, pre = name.split('-', 3)
    return mem, int(n[1:]), bar, pre


def main():
    files = ['matrix-shared8k.json', 'tg-matrix-shared32k.json', 'n256-by-group.json',
             'dist2-sizes256.json', 'dist4-sizes256.json', 'dist1-sizes512-1024.json']
    valid = []   # (file, dist, record) excluding threadgroup rows of the 8 KiB-declared run (capacity artifact)
    for f in files:
        d, R = rows(f)
        check(f'{f}: complete, no fault, every lane reached the suffix',
              d['complete'] and all(not r['fault'] and r['suffix_lanes'] == d['total'] for r in R.values()))
        for name, r in R.items():
            mem, n, _, _ = parse(name)
            if f == 'matrix-shared8k.json' and mem == 'tg': continue
            valid.append((f, d.get('dist', 1), r))
    controls = [(f, r) for f, _, r in valid if parse(r['name'])[2] == 'wait' and parse(r['name'])[1] >= 128]
    check('negative control (wait as barrier) shows stale reads in every run with >= 4 SIMD groups',
          controls and all(r['mismatches'] > 0 for _, r in controls), len(controls))
    z68 = [r for _, _, r in valid if parse(r['name'])[2] == '68']
    check('0x68: zero mismatches in every variant, memory, size (64..1024) and distance', z68 and all(r['mismatches'] == 0 for r in z68), len(z68))
    small78 = [r for _, _, r in valid if parse(r['name'])[2] == '78' and parse(r['name'])[1] <= 128]
    check('0x78: zero mismatches with up to 4 SIMD groups (64/128 lanes), all variants, both memories',
          small78 and all(r['mismatches'] == 0 for r in small78), len(small78))
    big78 = [(dist, r) for _, dist, r in valid if parse(r['name'])[2] == '78' and parse(r['name'])[1] >= 256]
    check('0x78 with >= 8 SIMD groups: stale reads in some variant of every size', all(
        any(r['mismatches'] > 0 for d, r in big78 if parse(r['name'])[1] == n) for n in {parse(r['name'])[1] for _, r in big78}))
    grouped = [(dist, r) for dist, r in big78 if r.get('err_lanes_by_group')]
    def crossing(g, G, dist):
        return g//4 != ((g+dist) % G)//4
    check('0x78: errors only in reading groups whose partner lies in another aligned block of 4 SIMD groups',
          grouped and all(c == 0 for dist, r in grouped for g, c in enumerate(r['err_lanes_by_group'])
                          if not crossing(g, len(r['err_lanes_by_group']), dist)), len(grouped))
    check('0x78 (wait+mb): every crossing reading group has errors (dist 1 at 256/512/1024, dist 2, dist 4)',
          all(all(c > 0 for g, c in enumerate(r['err_lanes_by_group']) if crossing(g, len(r['err_lanes_by_group']), dist))
              for dist, r in grouped if r['name'].endswith('wait+mb')))

    d8, R8 = rows('matrix-shared8k.json')
    art = [(R8[f'tg-n{n}-68-{p}']['mismatches'], R8[f'tg-n{n}-78-{p}']['mismatches']) for n in (128, 256) for p in ('none', 'wait', 'mb', 'wait+mb')]
    check('capacity artifact: with 8 KiB declared, tg 128/256-lane rows fail identically for 0x68 and 0x78 at n=128',
          all(a == b == 131072000 for a, b in art[:4]))
    C = load('tg-capacity.json')
    check('threadgroup memory: exchange exact iff highest byte < declared/4 (8, 16, 32 KiB)',
          C and all(r['exact'] == (r['highest_byte_touched'] < r['declared_bytes']//4) for r in C), len(C))

    for name, ok, detail in checks:
        print(('PASS ' if ok else 'FAIL ')+name+(f'  [{detail}]' if detail != '' else ''))
    failed = sum(not ok for _, ok, _ in checks)
    print(f'{len(checks)-failed}/{len(checks)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
