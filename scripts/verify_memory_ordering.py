#!/usr/bin/env python3
"""Offline check of the retained cross-workgroup message-passing evidence (no GPU)."""
import gzip, json, sys
from collections import defaultdict
from pathlib import Path
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-memory-ordering'
fails = 0
def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)
def load(n): return json.loads(gzip.open(R/f'{n}.json.gz').read())['results']
def agg(rows, key):
    out = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        a = out[key(r)]; a[0] += r['mp_violations']; a[1] += r['flag_seen']; a[2] += r['reads_total']
    return out

m = load('matrix')
check(len(m) == 24 and all(r['final_data_ok'] for r in m), 'matrix: 24 variants, every data/flag word 1 at the end')
by = agg(m, lambda r: r['writer_fence'])
check(by['none'][0] > 10000 and by['f596'][0] > 10000, f"no fence / memory_barrier: violations {by['none'][0]} / {by['f596'][0]}")
check(by['mesa_qf'][0] == 0, "Mesa queue-family sequence on the writer: 0 violations in all 8 reader/store variants")
check(sum(r['violations_same_core'] for r in m) == 0 and sum(r['flag_seen_same_core'] for r in m) > 0, 'same-core pairs: messages seen, never violated')
check(all(r['flag_seen'] > 0.15*r['reads_total'] for r in m), 'messages become visible mid-dispatch in every variant')

b = agg(load('bisect'), lambda r: r['writer_fence'])
check(b['f533'][0] == 0 and b['f596+f533'][0] == 0 and b['mesa_qf'][0] == 0, 'bisect: f533 alone, f596+f533 and the full sequence give 0 violations')
others = [k for k in b if 'f533' not in k and k != 'mesa_qf']
check(len(others) == 11 and all(b[k][0] > 10000 for k in others), 'bisect: every other single barrier / f596 pair still violates: ' + ', '.join(f'{k}={b[k][0]}' for k in sorted(others)))

rd = agg(load('reader'), lambda r: (r['writer_fence'], r['store_coherent'], r['reader_invalidate'], r['reader_fence']))
check(all(v[0] == 0 for k, v in rd.items() if k[0] == 'f533' and k[3] == 'f59d'), 'f533 writer + reader f59d between flag and data: 0 violations (both store policies, with/without top invalidate)')
check(rd[('f533', 0, 0, 'none')][0] > 0, f"f533 writer, reader without any invalidate: {rd[('f533', 0, 0, 'none')][0]} violations (stale data line)")
check(all(v[0] > 10000 for k, v in rd.items() if k[0] == 'f596'), 'f596 writer violates for every reader variant')
nw = agg(load('nowait'), lambda r: r['writer_fence'])
check(0 < nw['f533'][0] < 2000, f"both loads in flight (no wait between): f533 writer still {nw['f533'][0]} violations")
print(f'{fails} failures'); sys.exit(1 if fails else 0)
