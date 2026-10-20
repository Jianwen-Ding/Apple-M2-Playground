#!/usr/bin/env python3
"""B21: what an executed `trap` (0x0008) does. probe_variants: surrogate = 0x18 (2-byte no-op, recorded), variant =
trap. Every lane stores 0x11110000|gid to table[gid] before X and 0x22220000|gid to table[256+gid] after it; the
harness then stores gid ^ 0x5a5a0000 as its output. Cases: all lanes run X; odd lanes run X inside an if; only SIMD
group 1 (gid 32-63, workgroup 0) runs X with two 64-thread workgroups. Usage: b21.py run|dry"""
import json, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import probe_variants as PV, record_suite as RS, agx_loop
PV.cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
st = agx_loop.store
NOP, TRAP = bytes.fromhex('1800'), bytes.fromhex('0800')

def probe(name, n, wg, cond):
    pre = mov(26, 0x11110000) + e('or r14, r1, r26') + mov(26, 0x22220000) + e('or r15, r1, r26') + mov(26, 256) + e('iadd r21, r1, r26')
    pre += st(14, 8, 1) + e('wait 0')
    if cond == 'odd':
        pre += mov(26, 1) + e('and r24, r1, r26') + e('if_icmp r0l, ueq, r24, r26, 1')
    elif cond == 'group1':
        pre += mov(26, 5) + e('asr r24, r1, r26') + mov(26, 1) + e('if_icmp r0l, ueq, r24, r26, 1')
    suf = (e('pop_exec r0l, 1') if cond != 'all' else b'') + st(15, 8, 21) + e('wait 0') + mov(26, 0x5a5a0000) + e('xor r2, r1, r26')
    t = [0] * 512
    tab = list(t)
    for i in range(n):
        tab[i] = 0x11110000 | i; tab[256 + i] = 0x22220000 | i
    want = [i ^ 0x5a5a0000 for i in range(n)]
    words = 8 + n + 8 + 16
    ok = lambda o, tb: len(o) == words and o[8:8 + n] == want and tb == tab
    return PV.Probe(name, pre, NOP, TRAP, suf, 0xffff, n, wg, 32, t, ok)

ps = [probe('trap_all', 32, 32, 'all'), probe('trap_odd', 32, 32, 'odd'), probe('trap_group1', 128, 64, 'group1')]
recs = PV.run(ps, Path('/scratch/agxsim-runs/b21/out'), dry=sys.argv[1] == 'dry', repeats=1)
for r in recs:
    n = r['n']; t1 = r['table_after']; o = r['out'][8:8 + n]
    print(json.dumps({'probe': r['name'], 'fault': r.get('fault'), 'fw_ns': r.get('fw_ns'),
                      'before_marker': sum(t1[i] == 0x11110000 | i for i in range(n)) if t1 else None,
                      'after_marker_lanes': [i for i in range(n) if t1 and t1[256 + i] == 0x22220000 | i][:70] if t1 else None,
                      'harness_store_lanes': [i for i in range(n) if o and o[i] == i ^ 0x5a5a0000][:70] if o else None}))
