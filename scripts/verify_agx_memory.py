#!/usr/bin/env python3
"""Offline check of retained pointer-chase (load latency) evidence. No GPU access.

Evidence: results/2026-10-10-agx-memory-latency/*.json from
run_drm_compute.py --kind chase (direct DRM). Each hop is
`device_load r2 = table[r2]; wait 0` over a single random cycle; 16 hops per
loop iteration, so ~1/16 of the ~38-cycle loop overhead is included per hop.
Claims checked:

  1. every chase passed its whole-buffer oracle (exact final index) and was
     emulator-gated against its own table;
  2. footprints <= 8 KiB hit at ~36-38 ns warm; the cold/warm ratio (~3.1)
     matches the clock ladder, i.e. ~50 cycles in both states;
  3. latency at least doubles between 8 and 12 KiB (first-level capacity);
  4. 12-64 KiB costs 90-110 ns warm, and a fresh 32 KiB run walks the clock
     ladder (first/last ratio 2.5-3.2): this level is GPU-clocked too;
  5. 1-16 MiB is a flat ~349 ns plateau; >= 64 MiB rises to ~370-390 ns;
  6. one line per 16 KiB page: latency follows line footprint, not page
     count; 16,384 pages add <= ~35 ns over 64 B stride at the same 1 MiB of lines.
"""
import argparse
import json
from pathlib import Path
import statistics as st
import sys

REPO = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, default=REPO/'results/2026-10-10-agx-memory-latency')
    a = p.parse_args()
    runs = {f.stem: json.loads(f.read_text()) for f in sorted(a.evidence.glob('*.json')) if f.stem != 'verification'}
    checks = []
    def check(name, ok, **detail):
        checks.append({'check': name, 'passed': bool(ok), **detail})
    per = lambda v: [(s['fw_ts'][1]-s['fw_ts'][0])/v['hops'] for s in v['samples']]
    def curve(run):
        return {v['footprint']: per(v) for v in runs[run]['variants']}
    warm = lambda xs: st.median(xs[-8:])

    check('runs-passed', all(r['passed'] and r['path'] == 'direct-drm' and r['kind'] == 'chase' for r in runs.values()), runs=len(runs))
    check('oracles', all(v['buffer_ok'] for r in runs.values() for v in r['variants']),
          variants=sum(len(r['variants']) for r in runs.values()), hops=sum(v['hops']*len(v['samples']) for r in runs.values() for v in r['variants']))
    check('emulator-gated', all(len(r.get('emulator', [])) == len(r['variants']) for r in runs.values()))

    f = curve('curve-fine')
    l1 = {n: warm(f[n]) for n in (2048, 8192)}
    ratio = st.median(f[2048][1:5])/l1[2048]
    check('first-level-hit', all(34 < x < 40 for x in l1.values()) and 2.9 < ratio < 3.3,
          warm_ns={k: round(v, 1) for k, v in l1.items()}, cold_over_warm=round(ratio, 3),
          cycles_warm_at_1398=round(l1[2048]*1.398, 1), cycles_cold_at_444=round(st.median(f[2048][1:5])*0.444, 1))
    check('capacity-step-8k-12k', warm(f[12288]) > 2*warm(f[8192]), ns_8k=round(warm(f[8192]), 1), ns_12k=round(warm(f[12288]), 1))
    mid = {n: warm(f[n]) for n in (12288, 16384, 32768, 65536)}
    fresh = per(runs['l2-clock-fresh']['variants'][0])
    check('second-level', all(88 < x < 110 for x in mid.values()) and 2.5 < fresh[0]/warm(fresh) < 3.2,
          warm_ns={k: round(v, 1) for k, v in mid.items()}, fresh_32k_first8=[round(x) for x in fresh[:8]],
          cycles_cold=round(fresh[0]*0.444), cycles_warm=round(warm(fresh)*1.398))
    plat = {n: warm(f[n]) for n in (1 << 20, 1 << 22, 1 << 24)}
    check('plateau-1m-16m', all(344 < x < 356 for x in plat.values()), warm_ns={k: round(v, 1) for k, v in plat.items()})
    big = [warm(f[n]) for n in (1 << 25, 1 << 26, 1 << 27, 1 << 28)]
    check('beyond-32m-rises', all(x < y for x, y in zip(big, big[1:])) and 360 < big[-1] < 400, warm_ns=[round(x, 1) for x in big])

    pg = curve('page-stride')
    small_pages = warm(pg[16*16384])
    many = warm(pg[16384*16384])
    check('page-stride-follows-lines', 34 < small_pages < 42 and 0 < many-plat[1 << 20] < 40 and
          warm(pg[1024*16384]) < 1.1*warm(f[65536]),
          ns_16_pages_1kib_lines=round(small_pages, 1), ns_1024_pages_64kib_lines=round(warm(pg[1024*16384]), 1),
          ns_64b_stride_64kib=round(warm(f[65536]), 1), ns_16384_pages_1mib_lines=round(many, 1),
          ns_64b_stride_1mib=round(plat[1 << 20], 1))

    passed = all(c['passed'] for c in checks)
    (a.evidence/'verification.json').write_text(json.dumps({'passed': passed, 'checks': checks}, indent=1)+'\n')
    for c in checks: print(('PASS ' if c['passed'] else 'FAIL ')+c['check'], {k: v for k, v in c.items() if k not in ('check', 'passed')})
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
