#!/usr/bin/env python3
"""Offline checks of results/2026-10-11-tg-memory-addressing (run_drm_tg_layout.py, run_drm_tg_capacity.py)."""
import json
from pathlib import Path
import sys

EV = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]/'results/2026-10-11-tg-memory-addressing'
SIZE = {'i32': 4, 'i16': 2, 'i8': 1}
SENT = {'i32': 0xcdcdcdcd, 'i16': 0xcdcd, 'i8': 0xcd}
V = {'i32': lambda i: 0xa0000000+i, 'i16': lambda i: 0xa000+i, 'i8': lambda i: 0x40+i}
checks = []
check = lambda name, ok, detail='': checks.append((name, bool(ok), detail))


def main():
    d = json.loads((EV/'layout.json').read_text())
    h = lambda xs: [int(x, 16) for x in xs]
    for f in ('i32', 'i16', 'i8'):
        s = d['stride'][f]
        check(f'{f}: index i lands at byte 4*{SIZE[f]}*i (all 32 lanes)', h(s['x4_offset_reads']) == [V[f](i) for i in range(32)])
        check(f'{f}: reading byte {SIZE[f]}*i finds index i/4 at multiples of 4, the sentinel elsewhere',
              h(s['natural_offset_reads']) == [V[f](i//4) if i % 4 == 0 else SENT[f] for i in range(32)])
    for k, c in enumerate('xyzw'):
        m = d['mask'][c]
        check(f'mask {c}: lands at byte 16i+{4*k} only, value from the first register (r6)',
              all(h(m[f'byte 16i+{4*j}']) == ([0xb0000000+i for i in range(4)] if j == k else [0xcdcdcdcd]*4) for j in range(4)))
    for b, r in d['combined'].items():
        check(f'base register {b} + index i -> byte {b}+16i', r['all_lanes_at_base+16i'] and h(r['read base+4i'])[1:] == [0xcdcdcdcd]*3)
    cap = d['capacity']
    check('base addressing: exchange exact iff every byte < declared size (2, 4, 8 KiB)',
          cap and all(r['exact'] == (r['highest_byte_touched'] < r['declared_bytes']) for r in cap), len(cap))
    old = json.loads((EV/'index-capacity.json').read_text()) if (EV/'index-capacity.json').exists() else None
    if old is not None: check('earlier index-addressed capacity data agrees: exact iff 16*(offset+63)+16 <= declared',
          old and all(r['exact'] == (16*(r['element_offset']+63)+16 <= r['declared_bytes']) for r in old), len(old))
    for name, ok, detail in checks:
        print(('PASS ' if ok else 'FAIL ')+name+(f'  [{detail}]' if detail != '' else ''))
    failed = sum(not ok for _, ok, _ in checks)
    print(f'{len(checks)-failed}/{len(checks)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
