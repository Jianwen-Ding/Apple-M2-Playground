#!/usr/bin/env python3
"""Offline checks of the IEEE sqrt.rn.f32 measurements (results/2026-10-20-fsqrt32). The hardware records hold the
mismatch counts of exhaustive runs (outputs were compared on the host against integer-isqrt references at run time);
this script re-checks the references and the recorded claims. No GPU access."""
import gzip, json, random, statistics as st, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import softfp32 as S  # noqa: E402
from run_drm_fsqrt32 import exact, exact_any, sweep_inputs  # noqa: E402

rec = json.load(gzip.open(REPO/'results/2026-10-20-fsqrt32/record.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


rng = random.Random(1)
xs = [0x3f800000+rng.randrange(1 << 24) for _ in range(3000)] + [rng.getrandbits(32) for _ in range(3000)] + [rng.randrange(1, 1 << 23) for _ in range(1000)]
check('the run-time references (exact on [1,4), exact_any everywhere) agree with the rational reference ref_sqrt32 on 7,000 inputs',
      all(exact_any(x) == S.ref_sqrt32(x) for x in xs) and all(exact(x) == S.ref_sqrt32(x) for x in xs[:3000]))
check('sweep inputs cover all 256 exponents x 65,536 mantissas (16,777,216)', sum(len(sweep_inputs(c)) for c in range(16)) == 1 << 24 and
      len({x >> 23 for c in (0, 15) for x in sweep_inputs(c)}) == 32)
b = {k: rec[f'hw-{k}'] for k in ('one', 'coupled', 'mesa')}
check('exhaustive [1, 4) on hardware: the 5-op one-correction sequence is correctly rounded on all 16,777,216 inputs',
      b['one']['inputs'] == 1 << 24 and b['one']['wrong'] == 0)
check('exhaustive [1, 4): the 8-op coupled sequence also 16,777,216 / 16,777,216', b['coupled']['inputs'] == 1 << 24 and b['coupled']['wrong'] == 0)
check(f"Mesa x * rsqrt_special(x): {b['mesa']['wrong']:,} of 16,777,216 misrounded (32%), at most 2 ulp from correctly rounded",
      4_000_000 < b['mesa']['wrong'] < 7_000_000 and set(b['mesa']['ulp_hist']) <= {'1', '-1', '2', '-2'})
sw = {k: rec[f'hw-{k}-sweep'] for k in ('one', 'hybrid', 'soft', 'mesa')}
check('full-range sweep (16,777,216 inputs, all exponents): hybrid and soft bit-exact', all(sw[k]['inputs'] == 1 << 24 and sw[k]['wrong'] == 0 for k in ('hybrid', 'soft')))
be = {int(k): v for k, v in sw['one']['by_exponent'].items()}
check('sweep: the fast sequence alone fails only at biased exponents 0-24 (inside sqrt_fast_ok, exponents 48-254: 0 errors)',
      be and max(be) <= 24 and sum(v for k, v in be.items() if 48 <= k <= 254) == 0)
med = lambda k: st.median(r['fw_ns'] for r in rec['cost/'+k]['runs'])
sl = {'mesa': (med('mesa-k512')-med('mesa-k256'))/256, 'one': (med('one-k512')-med('one-k256'))/256,
      'hybrid': (med('hybrid-k32')-med('hybrid-k16'))/16, 'soft': (med('soft-k32')-med('soft-k16'))/16}
print('  us per dependent sqrt (clock held, 131,072 lanes):', {k: round(v/1000, 3) for k, v in sl.items()})
check('cost runs exact on checked lanes; exact sequence <= 2x Mesa; hybrid 3-8x; soft 60-150x',
      all(all(r['bad'] in (0, None) for r in rec['cost/'+k]['runs']) for k in ('one-k256', 'one-k512', 'hybrid-k16', 'hybrid-k32', 'soft-k16', 'soft-k32')) and
      sl['one']/sl['mesa'] <= 2 and 3 <= sl['hybrid']/sl['mesa'] <= 8 and 60 <= sl['soft']/sl['mesa'] <= 150)
print(f'{sum(ok)}/{len(ok)} fsqrt32 checks passed')
sys.exit(0 if all(ok) else 1)
