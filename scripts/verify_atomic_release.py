#!/usr/bin/env python3
"""Offline checks of the retained atomic-as-release MP litmus (results/2026-10-18-atomic-release). No GPU access."""
import collections
import gzip
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-atomic-release'
rs = json.load(gzip.open(D/'atom.json.gz'))['results']
g = collections.defaultdict(list)
for r in rs:
    g[(r['writer_fence'], r['flag_mode'], r['reader_fence'])].append(r)
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def v(wf, m, rf):
    return [r['mp_violations'] for r in g[(wf, m, rf)]]


check('96 runs: 4 writer fences x 4 flag modes x 2 reader fences x 3 repeats', len(rs) == 96 and all(len(x) == 3 for x in g.values()))
check('every run: 1,048,576 reads, all 65,536 flags and data words final', all(r['reads_total'] == 1048576 and r['flags_final'] == 65536 and r['data_final_ok'] for r in rs))
check('same-core pairs never violate', all(r['violations_same_core'] == 0 for r in rs))
for wf in ('none', 'f596'):
    for m in ('add', 'addret', 'xchg'):
        for rf in ('f59d', 'none'):
            check(f'{m} flag with writer fence {wf}, reader {rf}: 500,000+ violating reads per run (worse than a store)',
                  min(v(wf, m, rf)) > 500000)
    check(f'store flag with writer fence {wf}: 30,000-110,000 violating reads per run', all(30000 <= x <= 110000 for rf in ('f59d', 'none') for x in v(wf, 'store', rf)))
for m in ('store', 'add', 'addret', 'xchg'):
    check(f'f533 writer + f59d reader, {m} flag: 0 violations in 3 runs', max(v('f533', m, 'f59d')) == 0)
    check(f"Mesa's sequence writer + f59d reader, {m} flag: 0 violations in 3 runs", max(v('mesa_qf', m, 'f59d')) == 0)
check('f533 writer without a reader fence: atomic flags leak (up to 2,400 reads), as the store does (up to 240)',
      max(max(v('f533', m, 'none')) for m in ('add', 'addret', 'xchg')) > 1000 and max(v('f533', 'store', 'none')) <= 240)
check('atomic flags are visible earlier: flag seen in 85%+ of reads for add/addret/xchg vs under 55% for the store (no fence)',
      all(r['flag_seen'] > 0.85*r['reads_total'] for r in rs if r['flag_mode'] != 'store' and r['writer_fence'] == 'none') and
      all(r['flag_seen'] < 0.55*r['reads_total'] for r in rs if r['flag_mode'] == 'store' and r['writer_fence'] == 'none'))
sys.exit(0 if all(ok) else 1)
