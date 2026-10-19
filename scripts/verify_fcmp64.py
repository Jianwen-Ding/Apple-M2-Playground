#!/usr/bin/env python3
"""Offline checks of the fp64 setp/min/max evidence (results/2026-10-19-fp64-cmp). No GPU access."""
import gzip, json, math, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import softfp64 as S

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-fp64-cmp'
checks = []


def check(name, cond):
    checks.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


rec = json.load(gzip.open(D/'fcmp64.json.gz'))
want_ops = sorted('c_'+n for n in S.FCMP_OPS)
check('all 18 compare ops recorded', sorted(rec.keys()) == want_ops)
check('every op: 5,312 lanes checked x 3 runs, 0 lanes differ from IEEE',
      all(r['checked'] == 5312 and len(r['runs']) == 3 and all(x['bad'] == 0 for x in r['runs']) for r in rec.values()))
check('instruction counts in the expected band (predicates 20-61, min/max 49)',
      all(20 <= rec[o]['instructions'] <= 61 for o in want_ops))

# DSL interpreter self-check on tricky pairs (must match IEEE before any hardware run)

def run_cmp(builder, a, b):
    P = S.Prog()
    ah, al = P.input('ah'), P.input('al')
    bh, bl = P.input('bh'), P.input('bl')
    hi, lo = builder(P, (ah, al), (bh, bl))
    g = P.run({'ah': a >> 32, 'al': a & 0xffffffff, 'bh': b >> 32, 'bl': b & 0xffffffff})
    return (g(hi) << 32) | g(lo)


def bits(x):
    return struct.unpack('<Q', struct.pack('<d', x))[0]


tricky = [(0.0, 2.0), (2.0, 0.0), (-0.0, 0.0), (0.0, -0.0), (-0.0, -5e-324), (3.0, -1.0),
          (-2.0, -2.0), (float('inf'), 1.0), (float('-inf'), float('inf')),
          (float('nan'), 1.0), (1.0, float('nan')), (float('nan'), float('nan'))]
ok = True
for n in S.FCMP_OPS:
    fn = getattr(S, 'fcmp_'+n)
    for a, b in tricky:
        got = run_cmp(fn, bits(a), bits(b))
        want = S.ref('c_'+n, a, b)
        if math.isnan(want):
            good = (got >> 52 & 0x7ff) == 0x7ff and got & 0xfffffffffffff != 0
        else:
            good = got == bits(want)
        ok &= good
        if not good:
            print('  interpreter mismatch', n, a, b, hex(got))
check('DSL interpreter matches IEEE on 12 tricky pairs x 18 ops', ok)
sys.exit(0 if all(checks) else 1)
