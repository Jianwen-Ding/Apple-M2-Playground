#!/usr/bin/env python3
"""B46 on the GPU: rcp and rsqrt on 1,024 mantissas of every normal binade (both signs for rcp) and on 65,536
positive denormals, against the prediction from the [1,2) / [1,4) tables scaled by the exponent (b46_offline.py).
Reports mismatches by class, and what denormal inputs and denormal-range results give."""
import gzip, json, random, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import gpu_safety, run_bench as B, record_transcendentals as T
sys.path.insert(0, str(Path(__file__).parent))
from b46_offline import table

def predict(op, x, hw1):
    s = x >> 31; e = x >> 23 & 0xff; m = x & 0x7fffff
    if op == 'rcp':
        t = int(hw1[m]); re = (t >> 23 & 0xff) - (e - 127)
    else:
        if s: return None
        odd = (e - 127) & 1; t = int(hw1[odd << 23 | m]); re = (t >> 23 & 0xff) - (e - 127 - odd) // 2
    if not 0 < re < 255: return None            # result outside the normal range: reported separately
    return s << 31 | re << 23 | (t & 0x7fffff)

rng = random.Random(46)
res = {}
gpu_safety.require_budget(1)
R = B.Runner(Path('/scratch/agxsim-runs/b46/run'))
for op in ('rcp', 'rsqrt'):
    _, hw1, _ = table(op)
    xs = [s << 31 | e << 23 | rng.getrandbits(23) for e in range(1, 255) for s in ((0, 1) if op == 'rcp' else (0,)) for _ in range(1024)]
    xs += [rng.randrange(1, 1 << 23) for _ in range(65536)]          # positive denormals
    xs += [0, 1 << 31, 0x7f7fffff, 0x00800000]
    hw = T.results(R, op, np.array(xs, dtype=np.uint32))
    ok = bad = 0; outside = {}; den = {}
    for x, h in zip(xs, hw):
        h = int(h); e = x >> 23 & 0xff
        if e == 0:
            den[f'{h:08x}'] = den.get(f'{h:08x}', 0) + 1; continue
        p = predict(op, x, hw1)
        if p is None:
            # result would be denormal / overflow: record what the hardware gives
            k = f'exp{e}{"-" if x >> 31 else "+"}:{h:08x}' if h in (0, 0x80000000, 0x7f800000, 0xff800000) else f'exp{e}:other'
            outside[k] = outside.get(k, 0) + 1
        elif p == h: ok += 1
        else: bad += 1
    res[op] = {'normal_predicted_ok': ok, 'normal_mismatch': bad, 'denormal_input_results': den,
               'result_outside_normal_range': outside, 'specials': {f'{x:08x}': f'{int(h):08x}' for x, h in zip(xs[-4:], hw[-4:])}}
    print(op, json.dumps(res[op]), flush=True)
Path('gpu.json').write_text(json.dumps(res, indent=1) + '\n')
