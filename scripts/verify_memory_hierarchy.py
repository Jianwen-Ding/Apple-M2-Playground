#!/usr/bin/env python3
"""Offline check of the retained memory-hierarchy evidence (no GPU). Rows: core cycles (reference units) per
memory instruction of every SIMD group of one workgroup per core (scripts/mem_probes.py)."""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-memory-hierarchy'
fails = 0


def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg)


def rows(f, **kw):
    return [r for r in json.loads((R/f).read_text())['rows'] if all(r.get(k) == v for k, v in kw.items())]


def T(f, **kw):
    r = rows(f, **kw)
    assert len(r) == 1, (f, kw, len(r))
    return r[0]['core_cycles_per_step']


near = lambda x, y, tol: abs(x-y) <= tol*y
# loads, all lanes of all groups on the same lines (L1): 64-byte segments per instruction = 32*4*S/64 (min 1)
segs = {0: 1, 1: 2, 2: 4, 4: 8, 8: 16, 16: 32, 32: 32}
per = {S: T('coalesce-shared.json', stride=S, groups=32)/32 for S in segs}
check(all(near(per[S], segs[S]/2, 0.1) for S in (2, 4, 8, 16, 32)) and per[0] < 1.3 and per[1] < 1.3,
      'L1 loads cost ~0.5 core cycle per 64-byte segment (32 groups): ' + ', '.join(f'S={S}: {per[S]:.2f}' for S in segs))
check(near(T('coalesce-private.json', stride=1, groups=32)/32, 1.0, 0.05),
      f'a 128-byte coalesced load costs 1.0 cycle per core when groups touch different lines '
      f'({T("coalesce-private.json", stride=1, groups=32)/32:.2f}; same lines for all groups: {per[1]:.2f})')
st = {S: T('store.json', stride=S, groups=32)/32 for S in (0, 1, 4, 32)}
check(near(st[1], 2.0, 0.05) and near(st[4], 8.0, 0.05) and near(st[32], 32, 0.05),
      'stores cost ~1 core cycle per 64-byte segment, at least 2: ' + ', '.join(f'S={S}: {v:.2f}' for S, v in st.items()))
g1 = {S: T('coalesce-shared.json', stride=S, groups=1) for S in (0, 8, 32)}
check(g1[32] > 2.5*g1[0], f'one group: latency per load grows with segments (8 loads per wait): {g1}')
pw = {r['window_bytes']: r['core_cycles_per_step'] for r in rows('private.json', groups=32)}
check(max(pw[4096], pw[8192]) < 42 and all(85 < pw[w] < 100 for w in (32768, 65536, 131072, 262144))
      and all(pw[w] > 440 for w in (524288, 1048576, 2097152, 4194304)),
      'private per-core windows (32 groups): <= 8 KiB L1 (~40), 32-256 KiB L2 (~88-98), >= 512 KiB DRAM-bound (450-530): '
      + ', '.join(f'{w >> 10}K {v:.0f}' for w, v in sorted(pw.items())))
dram = [r for r in rows('stream-dram.json', groups=32) if r['window_bytes'] == 268435456][0]
gbs = 32*128/(dram['core_cycles_per_step']/(dram['mhz']*1e6))*38/1e9
check(380 < gbs < 440, f'DRAM-bound streaming (256 MiB window, 32 groups/core): {gbs:.0f} GB/s over 38 cores')
pad = {(r['pad_kind'], r['pad']): r['core_cycles_per_step'] for r in rows('pad.json', groups=1)}
jump = (pad[('indep', 4)]-pad[('indep', 0)])*8
step = (pad[('indep', 16)]-pad[('indep', 8)])*8/8
check(jump > 20 and step < 2, f'4 ALU instructions after a wait delay the next 8-load batch by {jump:.0f} cycles; '
      f'further independent ALU instructions cost {step:.1f} each')
idle = {(r['window_bytes'], r['groups']): r['core_cycles_per_step'] for r in rows('noise-idle.json')}
load = {(r['window_bytes'], r['groups']): r['core_cycles_per_step'] for r in rows('noise-cpuload.json')}
check(all(near(load[k], idle[k], 0.02) for k in ((4096, 1), (4096, 32), (4194304, 32))),
      'CPU load (10 busy cores) does not change L1 or DRAM-bandwidth rows (< 2%): ' + ', '.join(f'{k}: {idle[k]:.1f}/{load[k]:.1f}' for k in idle))
print(f'{fails} failures'); sys.exit(1 if fails else 0)
