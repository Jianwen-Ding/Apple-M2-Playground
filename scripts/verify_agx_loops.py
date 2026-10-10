#!/usr/bin/env python3
"""Offline check of retained AGX loop-timing evidence (no GPU access).

Evidence: results/2026-10-10-agx-loops/*.json, produced by
run_drm_compute.py --kind loop on the direct DRM path. Claims checked:

  1. every run passed whole-buffer oracles; every loop variant was gated
     by the emulator and differed from its emulated copy only in K;
  2. lowest clock state: loop overhead ~86 ns/iteration; a dependent
     fadd32 or iadd costs ~4.5 ns; two independent chains halve that;
     iadd gains nothing from 4 chains over 2;
  3. with 512-step bodies, 4 fadd32 chains cost the same as 2 (the 64-step
     4-chain figure is an overhead-overlap artefact, not a throughput);
  4. top clock state: dependent/independent stays 2:1; lowest/top time ratio
     is ~3.15 (= 1398/444 MHz); assuming top = 1398 MHz (GET_PARAMS max) a
     SIMD group issues 1 instruction/cycle and a dependent chain advances
     every 2 cycles;
  5. one SIMD group per core runs as fast as one group total; a core
     saturates at ~3.5 single-group equivalents (4 schedulers x 32 lanes);
  6. run time is linear in trip count, and a 1-instruction body hides
     entirely inside the ~86 ns per-iteration overhead.
"""
import argparse
import json
from pathlib import Path
import statistics as st
import sys

REPO = Path(__file__).resolve().parents[1]
TOP_MHZ = 1398.0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, default=REPO/'results/2026-10-10-agx-loops')
    a = p.parse_args()
    runs = {f.stem: json.loads(f.read_text()) for f in sorted(a.evidence.glob('*.json')) if f.stem != 'verification'}
    checks = []
    def check(name, ok, **detail):
        checks.append({'check': name, 'passed': bool(ok), **detail})
    fw = lambda s: s['fw_ts'][1]-s['fw_ts'][0]
    def times(name):
        v, = runs[name]['variants']
        return [fw(s) for s in v['samples']]
    low = lambda name: st.median(times(name)[1:5])       # stable lowest-state window
    top = lambda name: st.median(times(name)[-10:])      # plateau after warm-up

    # 1: integrity and emulator gating.
    check('runs-passed', all(r['passed'] and r['path'] == 'direct-drm' for r in runs.values()), runs=len(runs))
    check('oracles', all(v['buffer_ok'] for r in runs.values() for v in r['variants']),
          variants=sum(len(r['variants']) for r in runs.values()))
    gated = all(len(r.get('emulator', [])) == len(r['variants']) and all(e['differs_only_in_trip_immediate'] for e in r['emulator'])
                for r in runs.values())
    check('emulator-gated', gated)
    check('timestamps-ordered', all(s['fw_ts'][0] < s['fw_ts'][1] for r in runs.values() for v in r['variants'] for s in v['samples']))

    # 2: lowest-state costs, K = 2000, 64 steps per iteration.
    k, m = 2000, 64
    over = st.mean([low('iadd8-c1-m0'), low('fadd4-c1-m0'), low('iadd8-c4-m0'), low('fadd4-c4-m0')])/k
    check('loop-overhead', 80 < over < 92, ns_per_iteration=round(over, 2))
    per = {}
    for kind in ('iadd8', 'fadd4'):
        base = low(f'{kind}-c1-m0')
        for c in (1, 2, 4):
            per[(kind, c)] = (low(f'{kind}-c{c}-m64')-base)/(k*m)
    for kind in ('iadd8', 'fadd4'):
        check(f'dependent-{kind}', 4.2 < per[(kind, 1)] < 4.8, ns=round(per[(kind, 1)], 3))
        check(f'two-chains-halve-{kind}', 1.85 < per[(kind, 1)]/per[(kind, 2)] < 2.15,
              ratio=round(per[(kind, 1)]/per[(kind, 2)], 3))
    check('iadd-4-chains-no-gain', abs(per[('iadd8', 4)]-per[('iadd8', 2)]) < 0.05*per[('iadd8', 2)],
          c2_ns=round(per[('iadd8', 2)], 3), c4_ns=round(per[('iadd8', 4)], 3))

    # 3: large bodies, K = 500.
    big = {c: low(f'fadd4-c{c}-m512-k500') for c in (1, 2, 4)}
    check('large-body-4-equals-2', abs(big[4]-big[2]) < 0.02*big[2], c2_us=round(big[2]/1000, 1), c4_us=round(big[4]/1000, 1),
          short_body_c4_ns=round(per[('fadd4', 4)], 3))
    check('large-body-dependent-2x', 1.85 < big[1]/big[2] < 2.0, ratio=round(big[1]/big[2], 3))

    # 4: top state, K = 2000, 512 steps.
    k, m = 2000, 512
    t1, t2 = top('warm-fadd4-c1-m512'), top('warm-fadd4-c2-m512')
    i1, i2 = top('warm-iadd8-c1-m512'), top('warm-iadd8-c2-m512')
    lowest_c1 = big[1]*4                                   # same body, 4x the trips, lowest state
    ratio = lowest_c1/t1
    check('lowest-to-top-ratio', 3.05 < ratio < 3.25, ratio=round(ratio, 3), mhz_ratio=round(TOP_MHZ/444, 3))
    over_top = over/ratio
    cyc = lambda t: (t-k*over_top)/(k*m)*TOP_MHZ/1000
    cycles = {'fadd4-c1': cyc(t1), 'fadd4-c2': cyc(t2), 'iadd8-c1': cyc(i1), 'iadd8-c2': cyc(i2)}
    check('cycles-at-top', all(1.9 < cycles[x] < 2.1 for x in ('fadd4-c1', 'iadd8-c1')) and
          all(0.95 < cycles[x] < 1.1 for x in ('fadd4-c2', 'iadd8-c2')),
          cycles={x: round(y, 3) for x, y in cycles.items()}, loop_overhead_cycles=round(over_top*TOP_MHZ/1000, 1))

    # 5: SIMD groups per core at top state (fadd32, 2 chains, 512 steps, K = 2000).
    g = {int(n.split('-')[1]): top(n) for n in runs if n.startswith('groups-')}
    check('one-group-per-core-free', abs(g[1216]-g[32]) < 0.01*g[32], us={n: round(v/1000, 1) for n, v in sorted(g.items())})
    sat = {n: (n/1216)*g[32]/g[n] for n in g if n >= 9728}
    lanes_ops = 38912*k*m/(g[38912]*1e-9)
    check('core-saturation', all(3.2 < x < 3.9 for x in sat.values()),
          single_group_equivalents_per_core={n: round(x, 2) for n, x in sat.items()},
          fp32_adds_per_s=f'{lanes_ops:.3e}', fraction_of_non_fma_peak=round(lanes_ops/(38*128*TOP_MHZ*1e6), 3))

    # 6: linear in trip count (lowest state, 1 step).
    v = {x['n']: st.median(fw(s) for s in x['samples'][1:]) for x in runs['trip-scale']['variants']}
    # A 1-step body adds nothing measurable: it hides inside the per-iteration overhead.
    slope = (v[10000]-v[1000])/9000
    intercept = v[1000]-1000*slope
    check('linear-in-trips-small-body-hidden', abs(slope-over) < 0.03*over and 3000 < intercept < 10000,
          one_step_ns_per_iteration=round(slope, 2), empty_loop_ns_per_iteration=round(over, 2), intercept_ns=round(intercept))

    passed = all(c['passed'] for c in checks)
    (a.evidence/'verification.json').write_text(json.dumps({'passed': passed, 'checks': checks}, indent=1)+'\n')
    for c in checks: print(('PASS ' if c['passed'] else 'FAIL ')+c['check'], {k: v for k, v in c.items() if k not in ('check', 'passed')})
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
