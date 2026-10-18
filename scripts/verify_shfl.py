#!/usr/bin/env python3
"""Offline checks of the retained shfl.sync lowering run (results/2026-10-18-shfl) and a simulator replay (skip with --no-sim)."""
import gzip
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_drm_shfl as R  # noqa: E402

rec = json.load(gzip.open(ROOT/'results/2026-10-18-shfl/shfl.json.gz'))
rs = rec['results']
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


gen = [r for r in rs if r['name'].startswith('generic')]
fast = [r for r in rs if r['name'].startswith('fast')]
naive = {r['mode']: r for r in rs if r['name'].startswith('naive')}
check('240 SIMD groups (7,680 lanes) per program; 48 generic, 256 fast and 4 negative-control programs', rec['groups'] == 240 and (len(gen), len(fast), len(naive)) == (48, 256, 4))
check('generic lowering, every mode x clamp/segment-mask (widths 32..1 and random 13-bit c): all groups equal the PTX semantics',
      all(r['groups_bad'] == 0 for r in gen) and {r['mode'] for r in gen} == set(R.MODES))
check('fast lowering (one instruction): up / down / bfly / idx with every constant amount 0..63: all groups exact',
      all(r['groups_bad'] == 0 for r in fast) and len({r['name'] for r in fast}) == 256)
check('negative control, naive idx (one simd_shuffle, per-lane index): wrong exactly on the 160 groups whose index low bits vary within a quad',
      naive['idx']['groups_bad'] == 160 and set(naive['idx']['bad_by_kind']) == {'1', '2', '3', '5'})
check('negative control, naive up / down / bfly (index = lane +- b): wrong on all 240 groups, uniform amounts included',
      all(naive[m]['groups_bad'] == 240 for m in ('up', 'down', 'bfly')))
check('generic lowering instruction counts (without the load and store): up 21, down 21, bfly 21, idx 22',
      [len(R.generic_lines(m, R.default_c(m))[0]) for m in ('up', 'down', 'bfly', 'idx')] == [21, 21, 21, 22])
# the PTX reference itself on a few hand-checked cases
a = list(range(100, 132))
d, p = R.ptx_shfl('up', a, [1]*32, R.default_c('up'))
check('reference: shfl.up by 1 keeps lane 0, others take the lane below', d[0] == 100 and d[1:] == a[:31] and p[0] == 0 and all(p[1:]))
d, p = R.ptx_shfl('down', a, [40]*32, R.default_c('down'))
check('reference: shfl.down by 40 (bval = 8): lanes 24-31 keep their own value', d[:24] == a[8:] and d[24:] == a[24:] and p[24] == 0)
d, p = R.ptx_shfl('idx', a, [3]*32, R.default_c('idx', 8))
check('reference: shfl.idx, width 8, index 3: each segment broadcasts its lane 3', all(d[l] == a[(l & ~7) | 3] for l in range(32)))
d, p = R.ptx_shfl('bfly', a, [1]*32, R.default_c('bfly'))
check('reference: shfl.bfly mask 1 swaps neighbours', d == [a[l ^ 1] for l in range(32)])
if '--no-sim' not in sys.argv:
    out = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/run_drm_shfl.py'), 'offline', '--groups', '60'], capture_output=True, text=True, cwd=ROOT)
    line = out.stdout.splitlines()[0] if out.stdout else out.stderr[-300:]
    check('Rust simulator replay (60 groups per program, all 308 programs): ' + line, 'mismatching groups total 0' in line)
sys.exit(0 if all(ok) else 1)
