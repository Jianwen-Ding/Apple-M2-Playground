#!/usr/bin/env python3
"""Offline checks of the fmadd32 bit-52 (pow fixup) rule (results/2026-10-18-fma-b52): the Python reference model against the retained hardware
results, the Rust simulator against freshly recorded coverage cases, and the retained historical bit-52 records of 2026-10-11."""
import gzip
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ONE, QNAN = 0x3f800000, 0x7fc00000
flush = lambda x: x & 0x80000000 if (x & 0x7f800000) == 0 else x
isnan = lambda x: bool((x & 0x7f800000) == 0x7f800000 and x & 0x7fffff)
isinf = lambda x: (x & 0x7fffffff) == 0x7f800000
f32 = lambda x: struct.unpack('<f', struct.pack('<I', x))[0]
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def int_class(y):
    v = abs(f32(y))
    if v >= 2**24:
        return 'even'
    if v != math.floor(v):
        return 'non'
    return 'odd' if int(v) % 2 else 'even'


def fixup(x, y, c):
    """bit 52 of fmadd32 D = A * B + C: C (the provisional pow result) fixed up by the C99 pow special cases of (A, B)."""
    fx, fy = flush(x), flush(y)
    cc = c if isnan(c) else flush(c)
    neg = lambda v: QNAN if isnan(v) else v ^ 0x80000000
    if fy & 0x7fffffff == 0 or x == ONE:
        return ONE
    if isnan(y):
        return cc
    if isnan(x):
        if x & 0x80000000 and not isinf(y) and int_class(y) == 'non':
            return QNAN
        return cc
    if fy == ONE:
        return fx
    if fx & 0x80000000:
        if x == 0xbf800000 and isinf(y):
            return ONE
        zero_or_inf = (fx & 0x7fffffff) == 0 or isinf(fx)
        k = None if isinf(y) else int_class(y)
        if not zero_or_inf and k == 'non':
            return QNAN
        if k == 'odd':
            return neg(cc)
    return cc


rec = json.load(gzip.open(ROOT/'results/2026-10-18-fma-b52/b52.json.gz'))
for key, name, n in (('set1', '24^3 special triples (+-0, subnormals, normals, +-1, +-inf, NaNs)', 13824), ('set2', 'integer / near-integer B (odd, even, 2^23 / 2^24 boundary) x signs x 4 C', 1024)):
    d = rec[key]
    T = [tuple(t) for t in d['triples']]
    check(f'{name}: {n} triples, 3 identical hardware runs', len(T) == n and d['runs'][0] == d['runs'][1] == d['runs'][2] and len(d['runs'][0]) == n)
    bad = sum(1 for t, r in zip(T, d['runs'][0]) if r != fixup(*t))
    check(f'{name}: the reference model equals every hardware result word (0 exceptions, got {bad})', bad == 0)
d1 = rec['set1']
T1 = [tuple(t) for t in d1['triples']]
old = lambda a, b, c: a if b == ONE else ONE if a == ONE else c
check('the 2026-10-11 rule (B = 1 -> A; A = 1 -> 1; else C) fails on 6,062 of the 13,824 triples (B zero / denormal, A < 0, ...)',
      sum(1 for t, r in zip(T1, d1['runs'][0]) if r != old(*t)) == 6062)
suite = ROOT.parent/'AGX-Performance-Simulator/rust/target/release/suite_check'
if '--no-sim' not in sys.argv:
    r = subprocess.run([str(suite), str(ROOT.parent/'AGX-Performance-Simulator/coverage/expected'), '--only', 'fmadd_b52'], capture_output=True, text=True)
    check('Rust simulator vs the recorded coverage cases fmadd_b52 (24^3 and integer sets, recorded twice on the GPU, deterministic): 2 of 2 exact',
          'fmadd_b52    pass    2 /    2' in r.stdout and 'mismatch    0' in r.stdout)
    r = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/replay_fmadd_lane.py')], capture_output=True, text=True, cwd=ROOT)
    line = r.stdout.splitlines()[0]
    d = eval(line)
    check('Rust simulator replay of the retained 2026-10-11 bit-flip records: %s (the 98 historical 8-byte bit-52 programs now match instead of being refused)' % line,
          d.get('match') == 391 and 'mismatch' not in d)
sys.exit(0 if all(ok) else 1)
