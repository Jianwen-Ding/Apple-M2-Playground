#!/usr/bin/env python3
"""Offline checks of the retained setp fix-up extension evidence (results/2026-10-19-fcmp-extra). No GPU access."""
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_drm_fcmp_fixup import ieee, VALS, N, NAMES, UNAMES, FNAMES

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-fcmp-extra'
checks = []


def check(name, ok):
    checks.append(bool(ok))
    print('PASS' if ok else 'FAIL', name)


rec = json.load(gzip.open(D/'fixup_extra.json.gz'))
names = NAMES + UNAMES + FNAMES
check('record covers all 20 outputs', rec['names'] == names and rec.get('extra') is True)
check('3 repeats', len(rec['results']) == 3)
n = N*N
A = [VALS[i//N] for i in range(n)]; B = [VALS[i % N] for i in range(n)]
want = {nm: [ieee(nm, x, y) for x, y in zip(A, B)] for nm in names}
ok = True
for r in rec['results']:
    for nm in names:
        got = r['out'][nm]
        if len(got) != n:
            ok = False; break
        if nm in ('min', 'max'):
            from run_drm_fcmp_fixup import same
            if not same(nm, got, want[nm]):
                ok = False; break
        elif any(g != w for g, w in zip(got, want[nm])):
            ok = False; break
check('all 20 outputs exact on all 2,304 pairs in all 3 runs', ok)
check('float-result outputs are exactly 0x3f800000 or 0',
      all(v in (0, 0x3f800000) for r in rec['results'] for nm in FNAMES for v in r['out'][nm]))
check('host oracle normalised (nan/num are 0/1, not payload ints)',
      all(v in (0, 1) for v in want['nan']+want['num']))
sys.exit(0 if all(checks) else 1)
