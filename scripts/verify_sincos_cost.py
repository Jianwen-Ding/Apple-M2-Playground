#!/usr/bin/env python3
"""Offline checks of the sin/cos sequence cost measurement (results/2026-10-18-sincos-cost). No GPU access."""
import gzip, json, statistics as st, sys
from pathlib import Path

rec = json.load(gzip.open(Path(__file__).resolve().parents[1]/'results/2026-10-18-sincos-cost/sincos.json.gz'))
rs = rec['runs']
ok = []


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


med = {(kd, k): st.median(x['fw_ns'] for x in rs if x['kind'] == kd and x['k'] == k) for kd in ('mesa', 'fma') for k in (1, 64, 128)}
check('2 sequences x chains of 1 / 64 / 128 x 5 runs at 131,072 lanes, every dispatch timed', len(rs) == 30 and rec['lanes'] == 131072 and all(x['fw_ns'] > 0 for x in rs))
check('every sampled result is a valid sine value in [-1, 1]', all(-1.0001 <= struct_v <= 1.0001 for x in rs for struct_v in
      [__import__('struct').unpack('<f', __import__('struct').pack('<I', w))[0] for w in x['out_sample']]))
sl = {kd: (med[(kd, 128)]-med[(kd, 1)])/127 for kd in ('mesa', 'fma')}
check('Mesa sequence: 0.9-1.3 us per evaluation per 131,072 lanes (fit over 1..128)', 900 < sl['mesa'] < 1300)
check('fma-split sequence: 0.9-1.3 us per evaluation', 900 < sl['fma'] < 1300)
check('the PTX-compliant fma-split sequence costs the same within 5% (one extra fmul and an fmul turned fmadd are free here)', abs(sl['fma']/sl['mesa']-1) < 0.05)
print({k: round(v, 1) for k, v in sl.items()}, 'ns per evaluation')
sys.exit(0 if all(ok) else 1)
