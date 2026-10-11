#!/usr/bin/env python3
"""Offline accuracy check of scripts/agx_cost.py against the stored hardware measurements (no GPU).

Datasets (results/2026-10-11-cost-model and the instruction bench):
  bench      : 60 single-instruction loops, latency / single-group issue / 4-groups-per-core (in-sample fit)
  rotation   : 72 independent instructions over D = 4..16 destination registers (result-cache rule)
  random     : 24 random 24-instruction kernels, 1 group and 4 groups per core (out of sample)
Thresholds are the accuracy the README claims; a model change that breaks one fails here.
"""
import gzip, json, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agx_cost as C, cost_hw as H, run_bench as B, agx_loop
R = Path(__file__).resolve().parents[1]/'results/2026-10-11-cost-model'
e = agx_loop.encode
fails = 0
def check(ok, msg):
    global fails
    fails += not ok; print(('ok   ' if ok else 'FAIL ')+msg, flush=True)
def stats(errs):
    a = sorted(abs(x) for x in errs); return a[len(a)//2], a[int(.9*len(a))], a[-1], st.median(errs)

P = C.Params()
bench = json.loads(gzip.open(C.BENCH).read())['ops']
T = 20
err = {'latency': [], 'simd_issue': [], 'gpu': []}
for op, v in bench.items():
    def slope(ch, groups):
        c = [C.simulate(C.decode(B.loop(op, ch, S, T), P), C.trace(B.loop(op, ch, S, T))[0], P, groups) for S in (16, 64)]
        return (c[1]-c[0])/(T*48)
    pred = {'latency': slope(1, 1), 'simd_issue': slope(8, 1), 'gpu': slope(8, 4)/4}
    for m in pred: err[m].append((pred[m]-v[m]['cycles_per_step'])/v[m]['cycles_per_step'])
for m, lim in (('latency', 0.03), ('simd_issue', 0.04), ('gpu', 0.06)):
    md, p90, mx, b = stats(err[m]); check(md <= lim, f'bench {m}: median |err| {md:.3f} (limit {lim}), p90 {p90:.3f}, max {mx:.3f}')

rot = json.loads((R/'rotation.json').read_text())
rerr = []
for key, meas in rot.items():
    instr, D = key.split('|'); D = int(D)
    lines = [instr.format(r=5+k % D) for k in range(72)]
    body = b''.join(e(x) for x in lines)
    p = (H.predict(H.counted(body, 100), H.counted(body, 500), 400, 1)-35.25)/72
    rerr.append((p-meas)/meas)
md, p90, mx, b = stats(rerr[:16])      # 32-bit forms (iadd, fadd32)
check(md <= 0.05 and mx <= 0.12, f'rotation (32-bit forms): median |err| {md:.3f}, max {mx:.3f}')
md, p90, mx, b = stats(rerr[16:])
print(f'info rotation (fadd16): median |err| {md:.3f}, max {mx:.3f} (16-bit writeback not modelled beyond D=9)')

for fname, lim1, lim4 in (('random-kernels.json', 0.06, 0.12), ('heldout24.json', 0.06, 0.12), ('heldout48.json', 0.05, 0.12)):
  rk = json.loads((R/fname).read_text())
  for gm, groups, lim in (('one', 1, lim1), ('gpu', 4, lim4)):
    errs = []
    for x in rk:
        lines, body = H.kernel(x['seed'], len(x['ops']))
        p = H.predict(H.counted(body, 100), H.counted(body, 500), 400, groups)
        errs.append((p-x[gm]['measured'])/x[gm]['measured'])
    md, p90, mx, b = stats(errs)
    check(md <= lim, f'{fname}, {groups} group(s)/core: median |err| {md:.3f} (limit {lim}), p90 {p90:.3f}, max {mx:.3f}, bias {b:+.3f}')
print(f'{fails} failures'); sys.exit(1 if fails else 0)
