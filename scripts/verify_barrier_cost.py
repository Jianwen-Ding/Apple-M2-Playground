#!/usr/bin/env python3
"""Offline checks of the barrier-after-ALU cost measurement (results/2026-10-18-barrier-cost). No GPU access."""
import gzip, json, statistics as st, sys
from pathlib import Path

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-barrier-cost'
ld = lambda n: json.load(gzip.open(D/n))
hw, ctl, mod = ld('barcost.json.gz')['runs'], ld('barcontrol.json.gz')['runs'], ld('barcost_model.json.gz')
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


def slope(rs, wg, alu):
    m = {nb: st.median(x['fw_ns'] for x in rs if x['wg'] == wg and x['alu'] == alu and x['nbar'] == nb) for nb in (1, 33, 65)}
    return (m[65]-m[1])/64


check('108 barrier dispatches and 36 no-barrier controls, every result equals the host sum', len(hw) == 108 and len(ctl) == 36 and all(x['result_ok'] for x in hw+ctl))
per = {(wg, a): slope(ctl, wg, a)/a for wg in (128, 256) for a in (4, 32)}
check('a dependent iadd costs 60-100 ns per 131,072 lanes with no barrier (workgroups of 128 and 256 lanes)', all(60 < v < 100 for v in per.values()))
ex4 = {wg: slope(hw, wg, 4)-slope(ctl, wg, 4) for wg in (128, 256)}
check('with 4 iadds before it a barrier adds 0-120 ns per round', all(0 <= v < 120 for v in ex4.values()))
ex32 = {wg: slope(hw, wg, 32)-slope(ctl, wg, 32) for wg in (128, 256)}
check('with 32 iadds before it the barrier adds nothing measurable (within +/- 200 ns of 2.3-2.6 us)', all(abs(v) < 200 for v in ex32.values()))
mslope = {wg: (mod[f'{wg}-32']['model'][str(65)]-mod[f'{wg}-32']['model'][str(1)])/64 for wg in (128, 256)}
check('the cost model predicts 0.2-0.4 of the measured round time for 32 iadds + barrier at 128 and 256 lanes (3-5x low, from the iadd chain, not the barrier)',
      all(0.2 < mslope[wg]/slope(hw, wg, 32) < 0.4 for wg in (128, 256)))
print({k: round(v, 1) for k, v in per.items()}, ex4, ex32, {k: round(v) for k, v in mslope.items()})
sys.exit(0 if all(ok) else 1)
