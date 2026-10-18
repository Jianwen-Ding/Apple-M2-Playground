#!/usr/bin/env python3
"""Offline checks of the register-spill cost measurement (results/2026-10-18-spill-cost). No GPU access."""
import gzip, json, statistics, sys
from pathlib import Path

rs = json.load(gzip.open(Path(__file__).resolve().parents[1]/'results/2026-10-18-spill-cost/spill.json.gz'))
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


by = {r['nv']: r for r in rs}
med = {n: statistics.median(r['fence_s']) for n, r in by.items()}
ins = {n: int(r['mesa_stats'][0][0]) for n, r in by.items()}
sp = {n: int(r['mesa_stats'][0][1]) for n, r in by.items()}
fl = {n: int(r['mesa_stats'][0][2]) for n, r in by.items()}
check('9 shaders (16..384 live values), 5 runs each, every output matches the host model', len(rs) == 9 and all(r['ok'] and len(r['fence_s']) == 5 for r in rs))
check('Mesa spills nothing up to 96 live values, starts at 128 (6) and grows (70, 134, 262); fills equal spills', all(sp[n] == 0 for n in (16, 32, 48, 64, 96)) and [sp[n] for n in (128, 192, 256, 384)] == [6, 70, 134, 262] and sp == fl)
xs = [32, 48, 64, 96]
mx, my = statistics.mean(ins[n] for n in xs), statistics.mean(med[n] for n in xs)
slope = sum((ins[n]-mx)*(med[n]-my) for n in xs)/sum((ins[n]-mx)**2 for n in xs)
icept = my-slope*mx
check('no-spill baseline: time grows linearly with instruction count, about 0.1-0.4 us per instruction per 262,144 lanes', 1e-7 < slope < 4e-7)
extra = {n: (med[n]-(icept+slope*ins[n]))/sp[n] for n in (192, 256, 384)}
check('a spill + fill pair costs 3-15 us per 262,144 lanes beyond the baseline at 192, 256 and 384 live values (20-60 ALU-instruction equivalents)', all(3e-6 < v < 15e-6 for v in extra.values()))
check('the 6-spill shader (128 values) is within noise of its baseline (+/- 0.1 ms)', abs(med[128]-(icept+slope*ins[128])) < 1e-4)
print({n: round(v*1e6, 2) for n, v in extra.items()}, 'us per pair; slope', round(slope*1e6, 3), 'us/instr')
sys.exit(0 if all(ok) else 1)
