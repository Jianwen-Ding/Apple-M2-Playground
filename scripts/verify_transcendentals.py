#!/usr/bin/env python3
"""Offline check of novel-results/2026-10-16-transcendentals against results/2026-10-16-transcendentals.

  hw_samples.json.gz  M2 results (raw bits) for exp2 (76 binades), sin_pt_2 (60), log2 (12): 1,026 inputs per binade;
                      and Mesa's sin / cos sequence (chain_sin / chain_cos) plus the fma-split variant (chain_sin2 /
                      chain_cos2) on 32,768 inputs each, half around the replica's worst case
  exp2_G.bin.gz       the exp2 mantissa table G (G[0], then int8 first differences): the [1,2) recording
  sin_pt_2_H.bin.gz   the sin_pt_2 table H (H[0] as u32, then int8 first differences)

Pure Python (struct for fp32 rounding; every intermediate below is exact in a double before its single rounding).
"""
import gzip, json, math, struct, sys
from pathlib import Path

E = Path(__file__).resolve().parents[1]/'results/2026-10-16-transcendentals'
fails = 0


def check(ok, msg):
    global fails
    print(('ok   ' if ok else 'FAIL ')+msg)
    fails += not ok


def undiff(path):
    b = gzip.open(path).read()
    v = struct.unpack('<I', b[:4])[0]
    out = [v]
    for d in struct.unpack(f'<{len(b)-4}b', b[4:]):
        v += d
        out.append(v)
    return out


f32 = lambda v: struct.unpack('<f', struct.pack('<f', v))[0]
bits = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
val = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
G = undiff(E/'exp2_G.bin.gz')
H = undiff(E/'sin_pt_2_H.bin.gz')
check(len(G) == len(H) == 1 << 23, 'tables G (exp2) and H (sin_pt_2) have 2^23 entries')
S = json.load(gzip.open(E/'hw_samples.json.gz', 'rt'))['ops']


def exp2(b):
    if (b >> 23) & 0xff == 0xff:
        return None
    x = val(b) if (b >> 23) & 0xff else 0.0                    # fp32 denormals read as zero
    t = min(int(abs(x)*8388608.0), 1 << 40)                   # trunc(|x| * 2^23), exact
    q = ~t if x < 0 and t else t                              # ones' complement for negative values
    re = (q >> 23)+127
    return 0x7f800000 if re >= 255 else 0 if re <= 0 else re << 23 | G[q & 0x7fffff]


def sin_pt_2(b):
    x = val(b) if (b >> 23) & 0xff else 0.0
    if abs(x) == 1:
        return 0x3f800000
    if not abs(x) < 1:
        return 0x7fc00000                                      # canonical NaN beyond the domain
    return H[int(abs(x)*8388608.0)]


for op, fn in (('exp2', exp2), ('sin_pt_2', sin_pt_2)):
    xs, hw = S[op]['x'], S[op]['hw']
    got = [fn(x) for x in xs]
    bad = [i for i, (g, h) in enumerate(zip(got, hw)) if g is not None and g != h]
    covered = sum(g is not None for g in got)
    check(not bad and covered == len(xs),
          f'{op}: the model reproduces {covered - len(bad)} / {covered} hardware words over {S[op]["binades"]} binades'
          + (f' (first miss x={xs[bad[0]]:#x})' if bad else ''))
ex = dict(zip(S['exp2']['x'], S['exp2']['hw']))
check(ex.get(0xbf800000) == 0x3efffffe and ex.get(0x3f800000) == 0x40000000,
      'exp2(-1.0) = 0x3efffffe (0.49999988, the ones\' complement) while exp2(1.0) = 2.0 exactly')
sp = dict(zip(S['sin_pt_2']['x'], S['sin_pt_2']['hw']))
pairs = [(x, x | 0x80000000) for x in sp if x < 0x80000000 and (x | 0x80000000) in sp and val(x) < 1]
check(pairs and all(sp[a] == sp[b] for a, b in pairs), f'sin_pt_2 is even: sin_pt_2(-x) = sin_pt_2(x) on all {len(pairs)} paired inputs')

# exp2 accuracy against PTX ex2.approx.f32 (<= 2 ulp from the correctly rounded result) on the retained inputs
worst = 0
for x, h in zip(S['exp2']['x'], S['exp2']['hw']):
    xv = val(x)
    if not -126 <= xv < 128 or (x >> 23) & 0xff == 0:
        continue
    e = 2.0 ** xv
    cr = f32(e)
    if cr == 0 or math.isinf(cr) or (bits(cr) >> 23) & 0xff == 0:
        continue
    worst = max(worst, abs(val(h)-cr)/2.0 ** (math.floor(math.log2(cr))-23))
check(worst <= 2, f'exp2: at most {worst:.0f} ulp from the correctly rounded result on the retained inputs (PTX ex2.approx: 2 ulp)')

# Mesa's sin / cos sequence and the fma-split variant
CH = f32(0.5/math.pi)
CL = f32(0.5/math.pi-CH)


def chain(xb, cos, split):
    x = val(xb)
    t = f32(x*CL)
    t = f32(x*CH+t) if split else f32(x*CH)                  # fmadd32 (one rounding) or fmul32
    if cos:
        t = f32(t+0.25)
    fr = f32(t-math.floor(t))
    q = f32(fr*4.0)
    aq = abs(q)
    y = q if aq <= 1 else f32((2-aq)*math.copysign(1, q)) if aq <= 3 else f32((aq-4)*math.copysign(1, q))
    s = 1.0 if abs(y) >= 1 else val(H[int(abs(y)*8388608.0)])
    return bits(f32(s*y))


res = {}
for kind in ('sin', 'cos', 'sin2', 'cos2'):
    v = S['chain_'+kind]
    cos, split = kind.startswith('cos'), kind.endswith('2')
    got = [chain(x, cos, split) for x in v['x']]
    same = sum(g == h for g, h in zip(got, v['hw']))
    err = max(abs(val(h)-(math.cos if cos else math.sin)(val(x))) for x, h in zip(v['x'], v['hw']) if abs(val(x)) <= 2*math.pi)
    res[kind] = err
    check(same == len(got), f'chain_{kind}: the replica reproduces {same} / {len(got)} hardware words; '
          f'hardware max abs error in [-2pi, 2pi] 2^{math.log2(err):.2f}')
check(res['cos'] > 2**-20.4, f'Mesa\'s cos sequence exceeds PTX cos.approx (2^-20.4) on the GPU: 2^{math.log2(res["cos"]):.2f}')
check(res['cos2'] <= 2**-20.4 and res['sin2'] <= 2**-20.5 and res['sin'] <= 2**-20.5,
      f'fma-split cos 2^{math.log2(res["cos2"]):.2f} and sin 2^{math.log2(res["sin2"]):.2f}, Mesa sin 2^{math.log2(res["sin"]):.2f}: within PTX')
print(f'{fails} failures')
sys.exit(1 if fails else 0)
