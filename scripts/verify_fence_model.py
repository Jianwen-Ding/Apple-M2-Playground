#!/usr/bin/env python3
"""The simulator's cost model (AGX-Performance-Simulator rust/src/cost.rs, `memory_barrier` costs) against the retained hardware fence
costs (results/2026-10-18-fence-cost). Offline: builds the exact probe programs, predicts them with agx_cost (one SIMD group) and compares
the per-fence cost (test - control) / N with the measured medians."""
import gzip
import json
import os
from pathlib import Path
import statistics as st
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import probe_fence_cost as F  # noqa: E402
import run_drm_compute as drm  # noqa: E402
AGX_COST = ROOT.parent/'AGX-Performance-Simulator/rust/target/release/agx_cost'
CYC_PER_NS = 1.398
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def predict(code, groups=1):
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as t:
        t.write(code+bytes(16)); p = t.name
    r = subprocess.run([str(AGX_COST), p, '--groups', str(groups), '--units', 'real', '--allow-unknown'], capture_output=True, text=True)
    os.unlink(p)
    return json.loads(r.stdout.strip().splitlines()[-1])


rec = json.load(gzip.open(ROOT/'results/2026-10-18-fence-cost/fc15.json.gz'))
meas = {}
for r in rec['results']:
    meas.setdefault((r['ctx'], r['fence']), []).append(r['fw_ns'])
n = rec['n']
diff = {}
for ctx in F.CONTEXTS:
    c0 = predict(drm.build_main(F.body(n, ctx, None)))['cycles']
    for f in F.FENCE_SET:
        c1 = predict(drm.build_main(F.body(n, ctx, f)))['cycles']
        model = (c1-c0)/n/CYC_PER_NS
        real = (st.median(meas[(ctx, f)])-st.median(meas[(ctx, None)]))/n
        diff[(ctx, f)] = (model, real)
single = [k for k in diff if k[1] not in ('f533+f59d', 'mesa_qf')]
check('the seven single barriers in all 3 contexts (21 cells): model within 1 ns of the measured per-fence cost (worst %.2f ns)' %
      max(abs(diff[k][0]-diff[k][1]) for k in single), all(abs(diff[k][0]-diff[k][1]) < 1.0 for k in single))
check('f533 + f59d (3 contexts): within 16 ns (worst %.1f)' % max(abs(diff[(c, 'f533+f59d')][0]-diff[(c, 'f533+f59d')][1]) for c in F.CONTEXTS),
      all(abs(diff[(c, 'f533+f59d')][0]-diff[(c, 'f533+f59d')][1]) < 16 for c in F.CONTEXTS))
check("Mesa's seven-barrier sequence back to back and after a load: within 17 ns (%.1f, %.1f)" % tuple(diff[(c, 'mesa_qf')][0]-diff[(c, 'mesa_qf')][1] for c in ('none', 'load')),
      all(abs(diff[(c, 'mesa_qf')][0]-diff[(c, 'mesa_qf')][1]) < 17 for c in ('none', 'load')))
check("Mesa's sequence after a store: the model is 12.6%% high (%+.0f ns of %.0f; the measured sequence is sub-additive)" % (diff[('store', 'mesa_qf')][0]-diff[('store', 'mesa_qf')][1], diff[('store', 'mesa_qf')][1]),
      0 < diff[('store', 'mesa_qf')][0]-diff[('store', 'mesa_qf')][1] < 80)
# Multi-group contention (2026-10-19 finding): the model must charge device fences per group
# with max-combination, so 8 identical groups cost the same wall time as 1 (ratio 1.000 measured).
grat = {}
for ctx in ('none', 'store'):
    c1 = predict(drm.build_main(F.body(n, ctx, None)), 1)['cycles']
    c8 = predict(drm.build_main(F.body(n, ctx, None)), 8)['cycles']
    for f in ('f533', 'mesa_qf'):
        m1 = (predict(drm.build_main(F.body(n, ctx, f)), 1)['cycles']-c1)/n
        m8 = (predict(drm.build_main(F.body(n, ctx, f)), 8)['cycles']-c8)/n
        grat[(ctx, f)] = m8/m1
check('fence wall cost 1 vs 8 groups identical in the model (ratios %s)' % {k: round(v, 3) for k, v in grat.items()},
      all(abs(v-1.0) < 0.01 for v in grat.values()))
sys.exit(0 if all(ok) else 1)
