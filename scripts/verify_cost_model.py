#!/usr/bin/env python3
"""Offline accuracy check of scripts/agx_cost.py against the stored hardware measurements (no GPU).

Datasets and their role (results/2026-10-11-cost-model and the instruction bench):
  bench      FIT       60 single-instruction loops: the model's own parameters (checks rounding only)
  rotation   FIT       72 instructions over D = 4..16 destinations: the result-cache rule was fit here
  memory     FIT       load/store probes: the memory parameters were taken from these
  load grid  FIT       30-point ALU-before/after-load grid: the load fast latency / quiet / defer parameters
  memstate   FIT       store, threadgroup and quiet-time probes
  spaces     FIT       memory-space transitions
  waits      FIT       idle wait cost (1-30 per repetition; the long-run mode is excluded)
  review2    FIT/INFO  threadgroup deferral and load window are checked; store-window cases are reported
  random     SELECTION 24 random kernels: the issue-interval rule was chosen by its score here
  heldout24  HELD OUT  24 new 24-instruction kernels, measured once the issue rule was chosen; later
                       ALU-side changes (operand decode, shared units, token scaling) were re-scored on
                       them, so they are now regression guards rather than pristine held-out data
  heldout48  HELD OUT  12 new 48-instruction kernels, same
Kernel errors are reported per whole loop trip and per loop body (the fitted empty-trip cost
removed from both measurement and prediction). Thresholds sit just above the README figures.
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
        return C.to_ref(c[1]-c[0])/(T*48)
    pred = {'latency': slope(1, 1), 'simd_issue': slope(8, 1), 'gpu': slope(8, 4)/4}
    for m in pred: err[m].append((pred[m]-v[m]['cycles_per_step'])/v[m]['cycles_per_step'])
for m, lim in (('latency', 0.03), ('simd_issue', 0.04), ('gpu', 0.06)):
    md, p90, mx, b = stats(err[m]); check(md <= lim, f'bench (FIT) {m}: median |err| {md:.3f} (limit {lim}), p90 {p90:.3f}, max {mx:.3f}')

rot = json.loads((R/'rotation.json').read_text())
rerr = []
for key, meas in rot.items():
    instr, D = key.split('|'); D = int(D)
    lines = [instr.format(r=5+k % D) for k in range(72)]
    body = b''.join(e(x) for x in lines)
    p = (H.predict(H.counted(body, 100), H.counted(body, 500), 400, 1)-35.25)/72
    rerr.append((p-meas)/meas)
md, p90, mx, b = stats(rerr[:16])      # 32-bit forms (iadd, fadd32)
check(md <= 0.05 and mx <= 0.12, f'rotation (FIT, 32-bit forms): median |err| {md:.3f}, max {mx:.3f}')
md, p90, mx, b = stats(rerr[16:])
print(f'info rotation (fadd16): median |err| {md:.3f}, max {mx:.3f} (16-bit writeback not modelled beyond D=9)')

EMPTY_MEAS = 35.25
_c = [C.simulate(C.decode(H.counted(b'', t), P), C.trace(H.counted(b'', t))[0], P, 1) for t in (200, 1000)]
EMPTY_PRED = C.to_ref(_c[1]-_c[0])/800
print(f'info empty loop trip: measured {EMPTY_MEAS:.2f}, predicted {EMPTY_PRED:.2f} (reference units)')
mem = json.loads((R/'memory.json').read_text())
MEM = {'load line 1 + wait 0': ['iadd r13, r1, 32', 'device_load 0, i32, x, r6, u8_u9, r13, unsigned', 'wait 0'],
       '2 loads line 1 + one wait': ['iadd r13, r1, 32', 'device_load 0, i32, x, r6, u8_u9, r13, unsigned', 'device_load 0, i32, x, r7, u8_u9, r13, unsigned', 'wait 0']}
for name, lines in MEM.items():
    body = b''.join(e(x) for x in lines)*8
    p = (H.predict(H.counted(body, 100), H.counted(body, 500), 400, 1)-EMPTY_PRED)/8
    check(abs(p-mem[name])/mem[name] < 0.05, f'memory (FIT) {name}: measured {mem[name]:.1f}, predicted {p:.1f}')
# regression guards just above the figures published in the cost-model README (median |err| limits:
# whole trip 1 group, 4 groups, then loop body only 1 group, 4 groups)
grid = json.loads((R/'load-alu-grid.json').read_text())
gerr = []
Lg = 'device_load 0, i32, x, r6, u8_u9, r26, unsigned'
for key, m in grid.items():
    a_, b_ = map(int, key.split(','))
    pre = ['iadd r%d, r%d, 1' % (14+i % 4, 14+i % 4) for i in range(a_)]; post = ['iadd r%d, r%d, 1' % (18+i % 4, 18+i % 4) for i in range(b_)]
    body = b''.join(e(x) for x in pre+[Lg]+post+['wait 0'])*8
    p = (H.predict(H.counted(body, 100, consts=(1, 0x3f800000, 32, 7)), H.counted(body, 500, consts=(1, 0x3f800000, 32, 7)), 400, 1)-EMPTY_MEAS)/8
    gerr.append((p-m)/m)
md, p90, mx, b = stats(gerr)
check(md <= 0.03 and mx <= 0.08, f'load-after-ALU grid (FIT, 30 points): median |err| {md:.3f}, max {mx:.3f}')
from run_drm_tg_layout import tg
consts = (1, 0x3f800000, 32, 7)
st_ = agx_loop.store(5, 8, 26); L_ = e('device_load 0, i32, x, r6, u8_u9, r26, unsigned')
A_ = e('iadd r14, r14, 1'); W_ = e('wait 0'); TS_ = tg(False, 'i32', 5, base=None, index=1); LD_ = tg(True, 'i32', 6, base=None, index=0)
I8_ = b''.join(e('iadd r%d, r%d, 1' % (r, r)) for r in range(15, 23))
MS = {'store': [st_], 'store, wait': [st_, W_], 'iadd, store': [A_, st_], 'iadd, store, wait': [A_, st_, W_], 'store, store': [st_, st_],
      'store, 8 iadd': [st_, I8_], 'iadd, wait, store': [A_, W_, st_], 'iadd, store, store': [A_, st_, st_], 'tg store': [TS_],
      'iadd, tg store': [A_, TS_], 'load, wait': [L_, W_], 'load, iadd, wait': [L_, A_, W_], 'iadd, load, wait': [A_, L_, W_],
      'iadd, wait, load, wait': [A_, W_, L_, W_], 'iadd, store, load, wait': [A_, st_, L_, W_]}
meas_ms = json.loads((R/'memstate.json').read_text())
merr = []
for name, parts in MS.items():
    body = b''.join(parts)*8
    p = (H.predict(H.counted(body, 100, consts=consts), H.counted(body, 500, consts=consts), 400, 1)-EMPTY_MEAS)/8
    merr.append((p-meas_ms[name])/meas_ms[name])
md, p90, mx, b = stats(merr)
check(md <= 0.04 and mx <= 0.15, f'memory state probes (FIT, 15 cases): median |err| {md:.3f}, max {mx:.3f}')
TL_ = tg(True, 'i32', 7, base=None, index=0)
SP = {'dev store, dev store': [st_, st_], 'tg store, tg store': [TS_, TS_], 'dev store, tg store': [st_, TS_],
      'tg store, dev store': [TS_, st_], 'dev load, wait, tg load, wait': [L_, W_, TL_, W_],
      'dev store, tg load, wait': [st_, TL_, W_], 'tg store, dev load, wait': [TS_, L_, W_]}
meas_sp = json.loads((R/'spaces.json').read_text()); serr = []
for name, parts in SP.items():
    body = b''.join(parts)*8
    p = (H.predict(H.counted(body, 100, consts=consts), H.counted(body, 500, consts=consts), 400, 1)-EMPTY_MEAS)/8
    serr.append((p-meas_sp[name])/meas_sp[name])
md, p90, mx, b = stats(serr)
check(md <= 0.03 and mx <= 0.05, f'memory-space transitions (FIT, 7 cases): median |err| {md:.3f}, max {mx:.3f}')
wt = json.loads((R/'waits.json').read_text()); werr = []
for key, m in wt.items():
    slot, k = map(int, key.split(','))
    if k not in (1, 8, 16, 30): continue          # the long-run ~11-unit mode (k >= 31) is not modelled
    body = (e(f'wait {slot}')*k)*8
    werr.append(((H.predict(H.counted(body, 100), H.counted(body, 500), 400, 1)-EMPTY_MEAS)/8-m)/m)
md, p90, mx, b = stats(werr)
check(mx <= 0.05, f'idle wait cost, 1-30 waits per repetition (FIT, 8 cases): median |err| {md:.3f}, max {mx:.3f}')
r2 = json.loads((R/'review2.json').read_text())
W1_ = e('wait 1'); TLr = tg(True, 'i32', 7, base=None, index=0)
I8r = b''.join(e('iadd r%d, r%d, 1' % (15+i % 8, 15+i % 8)) for i in range(8))
def r2pred(parts):
    body = b''.join(parts)*8
    return (H.predict(H.counted(body, 100, consts=consts), H.counted(body, 500, consts=consts), 400, 1)-EMPTY_MEAS)/8
cerr = [(r2pred(p_)-r2[n])/r2[n] for n, p_ in {'C tg load, wait': [TLr, W_], 'C tg load, iadd, wait': [TLr, A_, W_],
                                                'C tg load, 8 iadd, wait': [TLr, I8r, W_]}.items()]
md, p90, mx, b = stats(cerr)
check(mx <= 0.10, f'threadgroup load deferral (FIT, review2 C, 3 cases): median |err| {md:.3f}, max {mx:.3f}')
werr = [(r2pred([A_, W1_*k, L_, W_])-r2[f'B iadd, {k} wait1, load, wait0'])/r2[f'B iadd, {k} wait1, load, wait0'] for k in (0, 1, 2, 3, 4, 6, 8)]
md, p90, mx, b = stats(werr)
check(md <= 0.05 and mx <= 0.10, f'load quiet-time window (iadd, k idle waits, load; 7 cases): median |err| {md:.3f}, max {mx:.3f}')
info = []
for name, parts in (('B iadd, 4 wait1, store', [A_, W1_*4, st_]), ('B iadd, 8 wait1, store', [A_, W1_*8, st_]),
                    ('E iadd, store, load, wait', [A_, st_, L_, W_]), ('A store, 8 iadd', [st_, I8r])):
    info.append(f'{name}: measured {r2[name]:.1f}, predicted {r2pred(parts):.1f}')
print('info known residuals (store window / store->load overlap / first store of a trip): ' + '; '.join(info))
for fname, role, lim1, lim4, blim1, blim4 in (('random-kernels.json', 'SELECTION', 0.06, 0.12, 0.08, 0.17),
                                             ('heldout24.json', 'HELD OUT', 0.06, 0.12, 0.09, 0.15),
                                             ('heldout48.json', 'HELD OUT', 0.045, 0.10, 0.05, 0.12)):
  rk = json.loads((R/fname).read_text())
  for gm, groups, lim, blim in (('one', 1, lim1, blim1), ('gpu', 4, lim4, blim4)):
    errs, berrs = [], []
    for x in rk:
        lines, body = H.kernel(x['seed'], len(x['ops']))
        p = H.predict(H.counted(body, 100), H.counted(body, 500), 400, groups)
        m = x[gm]['measured']
        errs.append((p-m)/m); berrs.append(((p-EMPTY_PRED)-(m-EMPTY_MEAS))/(m-EMPTY_MEAS))
    md, p90, mx, b = stats(errs); bmd, bp90, bmx, bb = stats(berrs)
    check(md <= lim and bmd <= blim, f'{fname} ({role}), {groups} group(s)/core: whole trip median {md:.3f} p90 {p90:.3f} max {mx:.3f} bias {b:+.3f}'
                                     f' | body only median {bmd:.3f} p90 {bp90:.3f} max {bmx:.3f} (limits {lim}/{blim})')
print(f'{fails} failures'); sys.exit(1 if fails else 0)
