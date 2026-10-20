#!/usr/bin/env python3
"""Offline checks of the cross-context memory-latency measurements (results/2026-10-20-cross-context-latency). No GPU access.
Neighbour test (scripts/run_drm_neighbour.py): ns per hop = firmware ns / hops; minimum over repeats."""
import gzip, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
rec = json.load(gzip.open(REPO/'results/2026-10-20-cross-context-latency/record.json.gz'))
old = json.load(gzip.open(REPO/'results/2026-10-16-cache-line/neighbour-v2.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


def hop(r):
    return {(x['elements'], x['offset']): min(x['fw_ns'])/r['hops'] for x in r['runs']}


on = [hop(rec['on1']), hop(rec['on2'])]; off = [hop(rec['off1']), hop(rec['off2'])]
check('interleaved A/B: a clock-keeper process running raises the 64 MiB-span hop from 256 to 448 ns (d=4) and 407 to 640-654 ns (d=64), both rounds',
      all(abs(h[(65536, 4)]-256) < 5 and abs(h[(65536, 64)]-407) < 5 for h in off) and all(h[(65536, 4)] > 440 and h[(65536, 64)] > 630 for h in on))
check('L2-level hops rise only slightly with the keeper (164 -> 170, 217 -> 230-233 ns)',
      all(abs(h[(1024, 4)]-164) < 2 and abs(h[(1024, 64)]-217) < 2 for h in off) and all(168 < h[(1024, 4)] < 173 and 228 < h[(1024, 64)] < 236 for h in on))
lk, kl, ks = hop(rec['longkeeper2']), hop(rec['neigh-k-long']), hop(rec['neigh-k-short'])
check('not process churn: one long-lived keeper process (64 x 64 commands) gives the same 448 ns', lk[(65536, 4)] > 440)
check('far-memory penalty independent of the keeper command length (63 ms: 449, 0.64 ms: 445 ns); the L2-level penalty grows with command rate (0.64 ms: 238 / 437 ns)',
      kl[(65536, 4)] > 440 and ks[(65536, 4)] > 440 and kl[(1024, 64)] < 236 and ks[(1024, 64)] > 400)
c32, c64, cb = hop(rec['ctx-32-no']), hop(rec['ctx-64-no']), hop(rec['ctx-64-busy6'])
check('same context: a second workgroup chasing alongside adds only ~34-40 ns (290 / 447), an ALU-busy second workgroup none at d=4 (256 ns)',
      abs(c32[(65536, 4)]-256) < 5 and 280 < c64[(65536, 4)] < 300 and abs(cb[(65536, 4)]-256) < 5)
new = hop(rec['rerun-all-offsets-nokeeper']); O = hop(old)
check('cache-line conclusion unchanged without the keeper: the step is between d = 60 and 64 at L2 and the 64 MiB level; L1 flat',
      new[(1024, 64)] - new[(1024, 60)] > 40 and new[(65536, 64)] - new[(65536, 60)] > 100 and abs(new[(64, 64)]-new[(64, 4)]) < 1)
check('the 2026-10-16 absolute far-memory latencies (448 / 670 ns) carry the keeper penalty: 256 / 408 ns without it',
      O[(65536, 4)] > 440 and O[(65536, 64)] > 660 and new[(65536, 4)] < 260 and new[(65536, 64)] < 412)
print(f'{sum(ok)}/{len(ok)} cross-context checks passed')
sys.exit(0 if all(ok) else 1)
