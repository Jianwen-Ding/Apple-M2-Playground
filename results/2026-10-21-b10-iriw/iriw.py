#!/usr/bin/env python3
"""B10 open item: IRIW (independent reads of independent writes) across workgroups, i.e. whether device memory is
multi-copy atomic. Workgroups of 32 lanes, in quads: role = workgroup % 4, slot = (workgroup / 4) * 32 + lane.
  role 0: x[slot] = 1          role 1: y[slot] = 1          (coherent store, then f533: the release sequence of B10)
  role 2 (reader A): K times { f59d; x; wait; f59d; y; wait }: A |= x & !y   ("x before y")
  role 3 (reader B): K times { f59d; y; wait; f59d; x; wait }: B |= y & !x   ("y before x")
A slot where A and B are both set saw the two writes in opposite orders (writes never revert, so no single order fits).
Straight-line code (no loops); every program runs in agx_run first. Usage: iriw.py sim|gpu [LANES] [K] [REPEATS] [VARIANT]
VARIANT: fenced (above, default) or plain (normal stores, no f533, no f59d, loads issued with waits only)."""
import json, struct, subprocess, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
sys.path.insert(0, '/save/workspace/apple-documentation-playground/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
from run_drm_litmus import store
from run_drm_cpu_clock import load
from run_drm_opcode_describe import get_sr
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
H = bytes.fromhex
mode = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 65536
K = int(sys.argv[3]) if len(sys.argv) > 3 else 16
reps = int(sys.argv[4]) if len(sys.argv) > 4 else 3
variant = sys.argv[5] if len(sys.argv) > 5 else 'fenced'
fenced = variant == 'fenced'
S = n // 4

def body():
    b = mov(26, 5) + e('asr r20, r1, r26')                       # r20 = workgroup
    b += mov(26, 3) + e('and r21, r20, r26')                     # r21 = role
    b += mov(26, 2) + e('asr r22, r20, r26') + mov(26, 5) + e('bfi r22, 0, r22, r26')   # (wg / 4) << 5
    b += mov(26, 31) + e('and r23, r1, r26') + e('or r22, r22, r23')                   # r22 = slot
    b += mov(26, S) + e('iadd r24, r22, r26')                    # r24 = y index
    b += mov(5, 1) + mov(9, 0)
    def role(k, inner):
        return mov(27, k) + e('if_icmp r0l, ueq, r21, r27, 1') + inner + e('pop_exec r0l, 1')
    fence = H('f533') if fenced else b''
    inv = H('f59d') if fenced else b''
    b += role(0, store(5, 22, fenced) + fence + e('wait 0'))
    b += role(1, store(5, 24, fenced) + fence + e('wait 0'))
    ra = b''
    for _ in range(K):
        ra += inv + load(6, 22, True) + e('wait 0') + inv + load(7, 24, True) + e('wait 0')
        ra += e('xor r8, r7, r5') + e('and r8, r6, r8') + e('or r9, r9, r8')         # A |= x & !y
    b += role(2, ra)
    rb = b''
    for _ in range(K):
        rb += inv + load(7, 24, True) + e('wait 0') + inv + load(6, 22, True) + e('wait 0')
        rb += e('xor r8, r6, r5') + e('and r8, r7, r8') + e('or r9, r9, r8')         # B |= y & !x
    b += role(3, rb)
    # results: A at 2S + slot, B at 3S + slot (readers only); core of every lane at 4S + gid
    b += mov(26, 2 * S) + e('iadd r25, r22, r26') + role(2, agx_loop.store(9, 8, 25))
    b += mov(26, 3 * S) + e('iadd r25, r22, r26') + role(3, agx_loop.store(9, 8, 25))
    b += get_sr(20, 3) + mov(26, 4 * S) + e('iadd r25, r1, r26') + agx_loop.store(3, 8, 25) + e('wait 0') + e('iadd r2, r21, 0')
    return b

bd = body(); cov.gate(bd); code = drm.build_main(bd)
words = 4 * S + n
if mode == 'sim':
    out, tab = cov.simulate(code, n, 32, 48, 0, [0] * words)
    assert sum(tab[:2 * S]) == 2 * S, 'writes'
    print(json.dumps({'mode': 'sim', 'lanes': n, 'K': K, 'variant': variant, 'writes_ok': True})); sys.exit()
import run_bench as B, gpu_safety
R = B.Runner(Path('/scratch/agxsim-runs/b10iriw/run'))
res = []
for rep in range(reps):
    gpu_safety.require_budget(1)
    out, tab, fw, _ = RS.run(R, code, n, 32, [0] * words, 48)
    x, y, A, Bv, core = tab[:S], tab[S:2 * S], tab[2 * S:3 * S], tab[3 * S:4 * S], tab[4 * S:4 * S + n]
    both = [s for s in range(S) if A[s] and Bv[s]]
    slot_cores = lambda s: [core[(s // 32 * 4 + r) * 32 + s % 32] for r in range(4)]
    distinct = sum(len(set(slot_cores(s))) == 4 for s in range(S))
    r = {'rep': rep, 'variant': variant, 'slots': S, 'reads_per_reader': K, 'writes_landed': sum(x) + sum(y) == 2 * S,
         'A_saw_x_first': sum(1 for a in A if a), 'B_saw_y_first': sum(1 for v in Bv if v), 'iriw_violations': len(both),
         'slots_on_4_distinct_cores': distinct, 'fw_ns': fw}
    res.append(r); print(json.dumps(r), flush=True)
Path(f'gpu_{variant}.json').write_text(json.dumps(res) + '\n')
