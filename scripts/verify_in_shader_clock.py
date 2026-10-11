#!/usr/bin/env python3
"""Offline checks of results/2026-10-11-in-shader-clock (run_drm_cpu_clock.py records)."""
import json
from pathlib import Path
import sys

EV = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]/'results/2026-10-11-in-shader-clock'
checks = []
check = lambda name, ok, detail='': checks.append((name, bool(ok), detail))


def load(f):
    p = EV/f
    return json.loads(p.read_text())['results'] if p.exists() else None


def main():
    S = load('same-line-stale.json')
    if S:
        check('same line, no barrier: both reads return the same value (normal and coherent load, flush or not)',
              all(r['counter_delta'] == 0 and r['timer_delta_ticks'] == 0 for r in S), len(S))
        check('...but the value is a live CPU write from inside the run (not the initial sentinel, counter > 0)',
              all(not r['any_sentinel'] and 0 < r['lane0'][0] <= r['cpu_clock']['iters'] for r in S))
    B = load('barrier-variants.json')
    if B:
        f = lambda coh, sl, bw: next(r for r in B if r['coherent'] == coh and r['second_line'] == sl and r['between'] == bw)
        for coh in (False, True):
            check(f'coherent={coh}: reading a second, untouched cache line gives a fresh time',
                  f(coh, True, 'none')['timer_delta_ticks'] > 0)
        check('normal load: no barrier (mem/device/unknown/Mesa device-scope) refreshes the same line',
              all(f(False, False, bw)['timer_delta_ticks'] == 0 for bw in ('mem_barrier', 'device_barrier_1', 'device_barrier_2', 'unknown_barrier_1', 'mesa_device_scope')))
        check('coherent load: device_barrier_1, unknown_barrier_1 and the Mesa device-scope sequence refresh it',
              all(f(True, False, bw)['timer_delta_ticks'] > 0 for bw in ('device_barrier_1', 'unknown_barrier_1', 'mesa_device_scope')))
        check('coherent load: memory_barrier and device_barrier_2 do not',
              all(f(True, False, bw)['timer_delta_ticks'] == 0 for bw in ('mem_barrier', 'device_barrier_2')))
    L = load('linearity.json')
    if L:
        ok = [r for r in L if r['timer_delta_ticks'] > 0]
        check('linearity runs: every variant returns a fresh time', len(ok) == len(L), len(L))
        diffs = [r['fw_ns_last']/1e3-r['timer_delta_ns']/1e3 for r in L]
        check('shader-measured time = firmware dispatch time minus 3-8 us, from 0 to 100,000 trips',
              all(3 <= x <= 8 for x in diffs), (round(min(diffs), 2), round(max(diffs), 2)))
        zero = [r['timer_delta_ns']/1e3 for r in L if r['trips'] == 0]
        check('back-to-back reads are 0.3-1 us apart (cost of one read)', all(0.3 <= x <= 1.0 for x in zero), zero)
        check('timer tick is 1/24 MHz (CNTFRQ_EL0)', all(r['cpu_clock']['cntfrq'] == 24000000 for r in L))
        check('all 32 lanes read identical values', all(r['lanes_agree'] for r in L))
    for name, ok, detail in checks:
        print(('PASS ' if ok else 'FAIL ')+name+(f'  [{detail}]' if detail != '' else ''))
    failed = sum(not ok for _, ok, _ in checks)
    print(f'{len(checks)-failed}/{len(checks)} checks passed')
    return 1 if failed or not checks else 0


if __name__ == '__main__':
    sys.exit(main())
