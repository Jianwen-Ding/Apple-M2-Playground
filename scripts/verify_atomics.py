#!/usr/bin/env python3
"""Offline check of the retained device and threadgroup atomic evidence (no GPU).

Re-derives every expectation from the stored operands: per-lane old/new values,
contended-word serializations, the cmpxchg single winner and the counter
permutation. Also re-checks each recorded atomic against Mesa's packing formula.
"""
import gzip, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_drm_atomic as DA

R = Path(__file__).resolve().parents[1]/'results/2026-10-11-atomics'
INIT = 0x40000000
fails = []
def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ')+msg)
    if not cond: fails.append(msg)

def load(n): return json.loads(gzip.open(R/n).read())

def find_atomic(hexbody, opcode_low, size):
    b = bytes.fromhex(hexbody)
    for i in range(len(b)-size+1):
        if b[i] & 0x3f == opcode_low and (size == 8 or b[i] & 0xff == 0x19):
            yield b[i:i+size]

dev = load('device-all.json.gz')
check(dev['complete'] and len(dev['results']) == 33, 'device: 33 dispatches complete, no fault')
T, X, Y = dev['T'], dev['X'], dev['Y']
for r in dev['results']:
    op = DA.OPS.index(r['op'])
    a = next(c for c in find_atomic(r['body'], 0x15, 8) if (int.from_bytes(c, 'little') >> 6) & 15 == op)
    n = int.from_bytes(a, 'little'); ret = bool(n >> 47 & 1)
    idx = 3 if r['mode'] == 'shared' else 1
    check(n == DA.mesa_atomic(op, 10 if ret else 0, 16, 2*idx, 12, ret), f"device {r['name']}: encoding = Mesa formula")
    if r['mode'] in ('lane', 'noret'):
        want = [DA.apply(r['op'], T[i], X[i], Y[i]) for i in range(64)]
        check(r['table'][:64] == want, f"device {r['name']}: new values")
        if r['mode'] == 'lane': check(r['out'] == T, f"device {r['name']}: returned old values")
    else:
        notes, _ = DA.check_shared(op, r['out'], r['table'][64], X, Y, INIT)
        check(not notes, f"device {r['name']}: contended returns serialize to final {r['table'][64]:#x}")
cas = load('device-casrace.json.gz')['results'][0]
w = [i for i in range(64) if cas['out'][i] == INIT]
check(len(w) == 1 and cas['table'][64] == X[w[0]], f'device cmpxchg race: exactly one winner (lane {w})')
for n in ('count4096', 'count65536'):
    r = load(f'device-{n}.json.gz')['results'][0]
    check(r['ok'] and r['table'][64] == INIT+int(n[5:]), f'device add counter {n[5:]} lanes: final = init + n, returns a permutation')

tg = load('tg-all.json.gz')
check(tg['complete'] and len(tg['results']) == 34, 'threadgroup: 34 dispatches complete, no fault')
T, X, Y = tg['T'], tg['X'], tg['Y']
DA.N = 32
for r in tg['results']:
    op_name, mode = r['name'].rsplit('-', 1); op = DA.OPS.index(op_name)
    if mode in ('lane', 'noret'):
        check(r['tg'] == [DA.apply(op_name, T[i], X[i], Y[i]) for i in range(32)], f"threadgroup {r['name']}: new values")
        if mode == 'lane': check(r['out'] == T, f"threadgroup {r['name']}: returned old values")
    else:
        Yj = [INIT]*32 if mode == 'casrace' else Y
        notes, _ = DA.check_shared(op, r['out'], r['tg'][0], X, Yj, INIT)
        check(not notes and len(set(r['tg'])) == 1, f"threadgroup {r['name']}: contended returns serialize to final {r['tg'][0]:#x}")
        if mode == 'casrace':
            w = [i for i in range(32) if r['out'][i] == INIT]
            check(len(w) == 1 and r['tg'][0] == X[w[0]], f'threadgroup cmpxchg race: exactly one winner (lane {w})')
print(f'{len(fails)} failures')
sys.exit(1 if fails else 0)
