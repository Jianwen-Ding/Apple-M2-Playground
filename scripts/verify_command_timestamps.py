#!/usr/bin/env python3
"""Offline check of retained Vulkan command-timestamp evidence (no GPU access).

Claims checked against results/2026-10-10-command-timestamps/*.json:
  1. every dispatch matched its exact readback oracle with guards intact,
     all timestamps were available, period 1 ns and 64 valid bits;
  2. every sample is ordered t0 < t1 < t2 < t3;
  3. every timestamp is a truncated 24 MHz tick: t == floor(k*125/3);
  4. t1-t0 (top-of-pipe -> compute stamp recorded BEFORE the dispatch) is
     linear in native instruction count, while t2-t1 (the conventional
     before/after pair around the dispatch) stays flat;
  5. host submit+wait exceeds t3-t0 by a roughly constant overhead;
  6. dependent and 4-way independent chains cost the same;
  7. slow-state time does not depend on active lanes (32..19456);
  8. samples fall in two discrete performance states ~1.5-1.8x apart;
  9. the direct DRM path (results/2026-10-10-direct-drm, no Mesa/Vulkan)
     passes whole-buffer oracles, its firmware start/end timestamps are on
     the same 24 MHz grid, and its chain slopes match the Vulkan path.
"""
import argparse
import json
from pathlib import Path
import statistics as st
import sys

REPO = Path(__file__).resolve().parents[1]


def fit(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/sum((x-mx)**2 for x in xs)
    a = my-b*mx
    ss = sum((y-my)**2 for y in ys); res = sum((y-a-b*x)**2 for x, y in zip(xs, ys))
    return a, b, 1-res/ss


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, default=REPO/'results/2026-10-10-command-timestamps')
    p.add_argument('--drm-evidence', type=Path, default=REPO/'results/2026-10-10-direct-drm')
    a = p.parse_args()
    runs = {f.stem: json.loads(f.read_text()) for f in sorted(a.evidence.glob('*.json')) if f.stem != 'verification'}
    checks = []
    def check(name, ok, **detail):
        checks.append({'check': name, 'passed': bool(ok), **detail})
    d01 = lambda s: s['ts'][1]-s['ts'][0]
    d12 = lambda s: s['ts'][2]-s['ts'][1]

    # 1-3: integrity over every retained sample.
    samples = [s for r in runs.values() for v in r['variants'] for s in v['samples']]
    check('runs-passed', all(r['passed'] for r in runs.values()), runs=len(runs))
    check('oracles-and-guards', all(v['values_ok'] and v['guards_ok'] and v['all_available']
                                    for r in runs.values() for v in r['variants']))
    limits = {json.dumps(l, sort_keys=True) for r in runs.values() for v in r['variants'] for l in v['limits']}
    check('limits', limits == {json.dumps({'timestamp_limits': {'period_ns': 1, 'compute_and_graphics': 1}}, sort_keys=True),
                               json.dumps({'queue': {'family': 0, 'timestamp_valid_bits': 64}}, sort_keys=True)})
    check('ordered', all(s['ts'][0] < s['ts'][1] < s['ts'][2] < s['ts'][3] for s in samples), samples=len(samples))
    stamps = [t for s in samples for t in s['ts']]
    check('24mhz-grid', all((t*3+124)//125*125//3 == t for t in stamps), timestamps=len(stamps),
          chance_rate=3/125)

    # 4: linear t1-t0 and flat t2-t1 in the slow state (n <= 65536, before any switch).
    for kind in ('iadd8', 'fadd4'):
        r = runs[f'sweep-{kind}']
        pts = [(v['n'], st.median(d01(s) for s in v['samples'])) for v in r['variants'] if v['n'] is not None and v['n'] <= 65536]
        intercept, slope, r2 = fit([x for x, _ in pts], [y for _, y in pts])
        flat = [st.median(d12(s) for s in v['samples']) for v in r['variants']]
        check(f'linear-t1-t0-{kind}', r2 > 0.999 and slope > 5, slope_ns_per_instr=round(slope, 3),
              intercept_ns=round(intercept), r2=round(r2, 6))
        check(f'flat-t2-t1-{kind}', max(flat) < 60000 and pts[-1][1] > 10*max(flat),
              t2_t1_medians_ns=[round(x) for x in flat], t1_t0_at_65536_ns=round(pts[-1][1]))

    # 5: host overhead beyond t3-t0, excluding each process's cold first sample.
    over = [s['host_ns']-(s['ts'][3]-s['ts'][0]) for r in runs.values() for v in r['variants'] for s in v['samples'][1:]]
    check('host-overhead', 50000 < st.median(over) < 300000, median_ns=round(st.median(over)),
          p10_ns=round(st.quantiles(over, n=10)[0]), p90_ns=round(st.quantiles(over, n=10)[-1]))

    # 6: chain independence at n=32768 (all matrix runs stayed in one state there).
    for kind in ('iadd8', 'fadd6', 'fadd4'):
        m = [st.median(d01(s) for s in v['samples']) for c in (1, 4)
             for v in runs[f'matrix-{kind}-c{c}']['variants'] if v['n'] == 32768]
        check(f'dependency-independent-{kind}', abs(m[0]-m[1]) < 0.08*m[0], c1_ns=round(m[0]), c4_ns=round(m[1]))

    # 7-8: lane-count independence and two-state clustering.
    count_runs = sorted((k for k in runs if k.startswith('count-')), key=lambda k: int(k.split('-')[1]))
    first = {}; allx = []
    for k in count_runs:
        xs = [d01(s) for v in runs[k]['variants'] if v['n'] == 65536 for s in v['samples']]
        first[k] = st.median(xs[:5]); allx += xs
    lo, hi = min(first.values()), max(first.values())
    check('lane-count-independent', hi-lo < 0.03*lo, counts={k: runs[k]['count'] for k in count_runs},
          slow_medians_ns={k: round(v) for k, v in first.items()})
    slow = [x for x in allx if x > 650000 and x < 760000]; fast = [x for x in allx if x < 500000]
    mid = [x for x in allx if not (x in slow or x in fast)]
    ratio = st.median(slow)/st.median(fast)
    check('two-performance-states', len(slow) > 20 and len(fast) > 15 and len(mid) <= 6 and 1.5 < ratio < 1.8,
          slow=len(slow), fast=len(fast), between=len(mid), slow_median_ns=round(st.median(slow)),
          fast_median_ns=round(st.median(fast)), ratio=round(ratio, 3))

    # Per-byte fetch model in both states: t = a + b*bytes from fadd4/iadd8 sweeps.
    slow_iadd = fit(*zip(*[(v['n'], st.median(d01(s) for s in v['samples'])) for v in runs['sweep-iadd8']['variants'] if v['n'] is not None and v['n'] <= 65536]))[1]
    slow_fadd = fit(*zip(*[(v['n'], st.median(d01(s) for s in v['samples'])) for v in runs['sweep-fadd4']['variants'] if v['n'] is not None and v['n'] <= 65536]))[1]
    per_byte = (slow_iadd-slow_fadd)/4
    check('fetch-model-slow-state', 1.5 < per_byte < 2.3, ns_per_byte=round(per_byte, 3),
          fixed_ns_per_instr=round(slow_fadd-4*per_byte, 3))

    # 9: direct DRM path agrees with the Vulkan path.
    drm = {f.stem: json.loads(f.read_text()) for f in sorted(a.drm_evidence.glob('*.json')) if f.stem != 'verification'}
    check('drm-oracles', all(r['passed'] and r['path'] == 'direct-drm' for r in drm.values()) and
          all(v['buffer_ok'] for r in drm.values() for v in r['variants']), runs=sorted(drm))
    fw = [t for r in drm.values() for v in r['variants'] for s in v['samples'] for t in s['fw_ts']+s['drm_time']]
    check('drm-24mhz-grid', all((t*3+124)//125*125//3 == t for t in fw) and all(
          s['fw_ts'][0] < s['fw_ts'][1] for r in drm.values() for v in r['variants'] for s in v['samples']), timestamps=len(fw))
    for kind, vk, top in (('iadd8', slow_iadd, 32768), ('fadd4', slow_fadd, 16384)):
        pts = [(v['n'], st.median(s['fw_ts'][1]-s['fw_ts'][0] for s in v['samples'][1:])) for v in drm[kind]['variants'] if v['n'] <= top]
        b = fit(*zip(*pts))[1]
        check(f'drm-slope-matches-vulkan-{kind}', abs(b-vk) < 0.05*vk, drm_ns_per_instr=round(b, 3), vulkan_ns_per_instr=round(vk, 3))
    empty = [s['fw_ts'][1]-s['fw_ts'][0] for r in drm.values() for v in r['variants'] if v['n'] in (None, 0) for s in v['samples'][1:]]
    check('drm-empty-command', st.median(empty) < 10000, median_fw_ns=round(st.median(empty)), samples=len(empty))

    passed = all(c['passed'] for c in checks)
    out = {'passed': passed, 'checks': checks}
    (a.evidence/'verification.json').write_text(json.dumps(out, indent=1)+'\n')
    for c in checks: print(('PASS ' if c['passed'] else 'FAIL ')+c['check'], {k: v for k, v in c.items() if k not in ('check', 'passed')})
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
