#!/usr/bin/env python3
"""Offline checks of the shfl lowering cost and register-amount measurements (results/2026-10-20-shfl-cost). No GPU access."""
import gzip, json, statistics as st, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO/'results/2026-10-20-shfl-cost'
sys.path.insert(0, str(REPO/'scripts'))
from run_drm_shfl import MODES, data, default_c, ptx_shfl  # noqa: E402

ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


ld = lambda n: json.load(gzip.open(D/n))
ch, nat = ld('chain.json.gz'), ld('chain-native.json.gz')
check('chain runs: every K=64 hardware output equals the simulator (7 kinds x 5 and 4 kinds x 7 repeats)',
      all(all(v) and len(v) == 5 for v in ch['exact_vs_sim'].values()) and len(ch['exact_vs_sim']) == 7 and
      all(all(v) and len(v) == 7 for v in nat['exact_vs_sim'].values()) and len(nat['exact_vs_sim']) == 4)
med = lambda r, kind, k: st.median(x['fw_ns'] for x in r['runs'] if x['kind'] == kind and x['k'] == k)
slope_nat = {k: (med(nat, k, 2048)-med(nat, k, 1024))/1024 for k in ('iadd', 'xor1', 'up1', 'idxreg')}
slope_gen = {k: (med(ch, k, 128)-med(ch, k, 1))/127 for k in ('gen_idx', 'gen_up', 'gen_bfly')}
print('  ns per chain step (131,072 lanes):', {k: round(v, 1) for k, v in {**slope_nat, **slope_gen}.items()})
check('native shuffles (xor/up/register idx) cost 140-180 ns per dependent step, about 2x a dependent iadd (60-90 ns)',
      all(140 <= slope_nat[k] <= 180 for k in ('xor1', 'up1', 'idxreg')) and 60 <= slope_nat['iadd'] <= 90 and
      all(1.7 <= slope_nat[k]/slope_nat['iadd'] <= 2.5 for k in ('xor1', 'up1', 'idxreg')))
check('generic 21/22-instruction lowering costs 2.7-3.1 us per step: 16-20x a native shuffle',
      all(2700 <= v <= 3100 for v in slope_gen.values()) and all(16 <= v/st.mean(slope_nat[k] for k in ('xor1', 'up1', 'idxreg')) <= 20 for v in slope_gen.values()))
lin = [(med(ch, k, 64)-med(ch, k, 1))/63 for k in slope_gen]
check('generic cost is linear in K (K=1..64 slope within 10% of K=1..128)', all(abs(a/b-1) < 0.1 for a, b in zip(lin, slope_gen.values())))

hw, sim = ld('regamt-hw.json.gz'), ld('regamt-sim.json.gz')
check('register-amount programs: hardware equals simulator, 8/8', all(x['out'] == y['out'] for x, y in zip(hw['results'], sim['results'])) and len(hw['results']) == 8)
A, B = data(240, 11); n = 240*32
good = True
for r in hw['results']:
    for g in range(240):
        sl = slice(32*g, 32*g+32)
        d, _ = ptx_shfl(r['mode'], A[sl], B[sl], default_c(r['mode']))
        uniform = len(set(B[sl])) == 1
        exact = r['out'][32*g:32*g+32] == d
        if r['variant'] == 'masked' and uniform and not exact:
            good = False
check('masked register amount (and b, 31; native op b) equals PTX for every warp-uniform b in all 4 modes (80/80 groups each)', good and
      all(0 not in r['bad_by_kind'] and 4 not in r['bad_by_kind'] for r in hw['results'] if r['variant'] == 'masked'))
check('without the mask, uniform amounts >= 32 are wrong (the register form does not apply the PTX 5-bit mask)',
      all(r['bad_by_kind'].get('0', 0)+r['bad_by_kind'].get('4', 0) > 0 for r in hw['results'] if r['variant'] == 'raw'))
check('per-lane amounts (kinds 1, 2, 3, 5) are wrong in every mode: still need the generic sequence',
      all(all(r['bad_by_kind'].get(str(k), 0) == 40 for k in (1, 2, 3, 5)) for r in hw['results']))
print(f'{sum(ok)}/{len(ok)} shfl-cost checks passed')
sys.exit(0 if all(ok) else 1)
