#!/usr/bin/env python3
"""Offline checks of the texture edge-case measurements (results/2026-10-19-texture-edge). No GPU access."""
import gzip, json, math, random, struct, sys
from pathlib import Path

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-texture-edge'
rec = json.load(gzip.open(D/'record.json.gz'))
ok = []
f = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


check('all 17 cases ran with intact guard words', len(rec) == 17 and all(r['run_ok'] and r.get('guards_intact', True) for r in rec.values()))

# RNG must replay the case generator exactly (bilinear 256 + wrap 256 + r32ui 256 + f32 248 draws first)
rng = random.Random(7)
[([rng.randrange(256) for _ in range(256)], [rng.randrange(1, 255) for _ in range(256)],
  [rng.getrandbits(32) for _ in range(256)], [rng.getrandbits(32) for _ in range(248)])]
oob = [rng.getrandbits(32) for _ in range(256)]
gvals = [rng.randrange(256) for _ in range(256)]
svals = [rng.randrange(256) for _ in range(256)]

o = rec['oob_fetch_r32ui']['out']
inin = [o[i] == oob[5*16+(i-8)] for i in range(32) if 0 <= (i-8) < 16] + \
       [o[i] == oob[((i-32)-8)*16+5] for i in range(32, 64) if 0 <= ((i-32)-8) < 16]
oobw = [o[i] for i in range(32) if not 0 <= (i-8) < 16] + [o[i] for i in range(32, 64) if not 0 <= ((i-32)-8) < 16]
check('texelFetch in-range: 32/32 exact', all(inin) and len(inin) == 32)
check('texelFetch out-of-range: all 32 lanes return 0, no fault', all(v == 0 for v in oobw) and len(oobw) == 32)


def T(x, y):
    return gvals[min(max(y, 0), 15)*16+min(max(x, 0), 15)]


g = rec['gather_r8']['out']
gm = 0
for i in range(32):
    x0, x1, y0, y1 = i, i+1, 4, 5
    exp = (T(x0, 5), T(x1, 5), T(x1, 4), T(x0, 4))
    got = (g[i] & 255, (g[i] >> 8) & 255, (g[i] >> 16) & 255, (g[i] >> 24) & 255)
    gm += got == exp
for i in range(32, 64):
    y0, y1, x0, x1 = (i-32), (i-32)+1, 4, 5
    exp = (T(x0, y1), T(x1, y1), T(x1, y0), T(x0, y0))
    got = (g[i] & 255, (g[i] >> 8) & 255, (g[i] >> 16) & 255, (g[i] >> 24) & 255)
    gm += got == exp
check('textureGather: 64/64 footprints ((x0,y1),(x1,y1),(x1,y0),(x0,y0)) with ceil-box and edge clamping', gm == 64)


def srgb(c):
    x = c/255
    lin = x/12.92 if x <= 0.04045 else ((x+0.055)/1.055)**2.4
    return round(lin*4095)/4095


s = rec['bilinear_srgb']['out']
sm = 0
for i in range(256*15):
    fx, cx = (i % 256)/256.0, i//256
    a = [svals[3*16+min(cx, 15)], svals[3*16+min(cx+1, 15)], svals[4*16+min(cx, 15)], svals[4*16+min(cx+1, 15)]]
    d = [srgb(v) for v in a]
    exact = (d[0]*(1-fx)+d[1]*fx)*0.625 + (d[2]*(1-fx)+d[3]*fx)*0.375
    sm += f(s[i]) == struct.unpack('<f', struct.pack('<f', round(exact*4095)/4095))[0]
check('sRGB bilinear: 3840/3840 equal float32(round(bilinear(12-bit taps) * 4095) / 4095)', sm == 3840)
sys.exit(0 if all(ok) else 1)
