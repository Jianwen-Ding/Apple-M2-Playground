#!/usr/bin/env python3
"""Offline checks of the emulated 64-bit atomic add (results/2026-10-18-atom64) and the Honeykrisp capability record."""
import gzip
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
D = ROOT/'results/2026-10-18-atom64'
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


caps = (D/'honeykrisp-caps.txt').read_text()
check('Honeykrisp (Apple M2 Max G14C B1) reports shaderBufferInt64Atomics = 0 and shaderSharedInt64Atomics = 0, shaderInt64 = 1',
      'Apple M2 Max' in caps and re.search(r'shaderInt64=1 bufferInt64Atomics\(1\.2\)=0 sharedInt64Atomics\(1\.2\)=0 bufferInt64Atomics\(ext struct\)=0', caps))
rec = json.load(gzip.open(D/'atom64.json.gz'))
rs = rec['results']
by = lambda m: [r for r in rs if r['mode'] == m]
check('8 repeats x 4 modes, 4,096 lanes each', len(rs) == 32 and all(len(by(m)) == 8 for m in ('distinct', 'shared', 'ticket', 'wrap')) and rec['lanes'] == 4096)
check('final 64-bit value exact in all 32 runs (random 64-bit addends to distinct words, one shared word, low-word-wrapping addends, and +1 tickets)',
      all(r['final_exact'] for r in rs))
check('distinct words (no contention): every returned old value exact in all 8 runs', all(r['old_exact'] for r in by('distinct')))
t = by('ticket')
check('ticket (4,096 lanes add 1 to a word 256 below a 2^32 boundary): returned values never duplicate', all(r['duplicates'] == 0 and r['distinct_returned'] == 4096 for r in t))
check('ticket: returned values that are the expected consecutive numbers: only 1,556-3,877 of 4,096 per run (the rest are torn across the carry)',
      all(1500 <= r['in_expected_range'] <= 3900 for r in t) and min(r['in_expected_range'] for r in t) < 2000 and all(r['in_expected_range'] < 4096 for r in t))
sys.path.insert(0, str(ROOT/'scripts')); sys.path.insert(0, str(ROOT.parent/'AGX-Performance-Simulator/scripts'))
if '--no-sim' not in sys.argv:
    import random
    import coverage as cov
    import run_drm_atom64 as R
    import run_drm_compute as drm
    n = 4096
    code = drm.build_main(R.body(n))
    for mode in ('distinct', 'shared', 'ticket', 'wrap'):
        vals, tgt, init = R.make(mode, n, random.Random(9))
        words = 5*n+2*n+4
        o, tt = cov.simulate(code, n, 32, 64, 0, R.table(vals, tgt, init, n, words))
        res = R.analyse(mode, vals, tgt, init, tt, n)
        good = res['final_exact'] and (mode != 'distinct' or res['old_exact']) and (mode != 'ticket' or res['in_expected_range'] == n)
        check(f'Rust simulator replay of the emulation, mode {mode}: {good}', good)
sys.exit(0 if all(ok) else 1)
