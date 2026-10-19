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


check('all 27 cases ran with intact guard words', len(rec) == 27 and all(r['run_ok'] and r.get('guards_intact', True) for r in rec.values()))

# RNG must replay the case generator exactly (bilinear 256 + wrap 256 + r32ui 256 + f32 248 draws first)
rng = random.Random(7)
_bil = [rng.randrange(256) for _ in range(256)]
wrapvals = [rng.randrange(1, 255) for _ in range(256)]
_u32 = [rng.getrandbits(32) for _ in range(256)]
_f32 = [rng.getrandbits(32) for _ in range(248)]
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

# border colours (CLAMP_TO_BORDER): the colour converts to the texture format
b = rec['border_r8_border_half']['out']
check('border 0.5 on r8: 16/16 in-range exact, all 40 OOB lanes read float32(round(0.5*255)/255) = 128/255',
      all(b[i] == struct.unpack('<I', struct.pack('<f', wrapvals[5*16+(i-20)]/255.0))[0] for i in range(56) if 0 <= (i-20) < 16) and
      all(b[i] == struct.unpack('<I', struct.pack('<f', 128/255.0))[0] for i in range(56) if not 0 <= (i-20) < 16))
b0 = rec['border_r8_border_zero']['out']
check('border 0.0 on r8: 16/16 in-range exact, all 40 OOB lanes read exactly 0.0',
      all(b0[i] == struct.unpack('<I', struct.pack('<f', wrapvals[5*16+(i-20)]/255.0))[0] for i in range(56) if 0 <= (i-20) < 16) and
      all(b0[i] == 0 for i in range(56) if not 0 <= (i-20) < 16))
bi = rec['border_r32ui']['out']
rng2 = random.Random(7)
[rng2.randrange(256) for _ in range(256)]          # bilinear vals
[rng2.randrange(1, 255) for _ in range(256)]        # wrapvals
raw32 = [rng2.getrandbits(32) for _ in range(256)]  # fetch_r32ui / border_r32ui words
check('border 0x12345678 on r32ui: 16/16 in-range exact, all 40 OOB lanes read 0x12345678',
      all(bi[i] == raw32[5*16+(i-20)] for i in range(56) if 0 <= (i-20) < 16) and
      all(bi[i] == 0x12345678 for i in range(56) if not 0 <= (i-20) < 16))
bl = rec['border_r8_linear']['out']
blm = 0
for i in range(256):
    t = i/256.0
    i0 = -1 if t < 0.5 else 0
    fr = (t+0.5) if i0 == -1 else (t-0.5)
    a0 = 64 if i0 == -1 else wrapvals[5*16]
    a1 = wrapvals[5*16] if i0 == -1 else wrapvals[5*16+1]
    if f(bl[i]) == struct.unpack('<f', struct.pack('<f', math.floor((a0*(1-fr)+a1*fr)*16+0.5)/4080))[0]:
        blm += 1
check('linear blend into the border: 256/256 follow the 12-bit unorm rule with the quantized border (64)', blm == 256)

# 16-bit formats through texelFetch (all 65,536 values each)
o16 = rec['fetch_r16']['out']
check('r16 unorm: all 65,536 values equal float32(k/65535)',
      all(o16[v] == struct.unpack('<I', struct.pack('<f', v/65535.0))[0] for v in range(65536)))
osn = rec['fetch_r16snorm']['out']
check('r16 snorm: all 65,536 values equal float32(max(s/32767, -1)) (-32768 and -32767 both give -1)',
      all(osn[v] == struct.unpack('<I', struct.pack('<f', max(((v-65536 if v >= 32768 else v)/32767.0), -1.0)))[0] for v in range(65536)))
oui = rec['fetch_r16ui']['out']
check('r16ui: all 65,536 values exact', all(oui[v] == v for v in range(65536)))

# mipmaps: 16x16 L0 = pattern, L1..L4 solid; level = ceil(lod - 0.5) clamped to [0, 4]
lods = [-1.0, -0.5, 0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
L0 = wrapvals[8*16+8]/255.0
LV = {0: L0, 1: 100/255.0, 2: 150/255.0, 3: 200/255.0, 4: 250/255.0}
def _level(lod):
    return min(max(math.ceil(lod - 0.5), 0), 4)
ln = rec['lod_nearest']['out']
check('textureLod nearest: level = ceil(lod - 0.5) clamped (ties go to the lower level), 16/16',
      all(struct.unpack('<f', struct.pack('<I', ln[i]))[0] == struct.unpack('<f', struct.pack('<f', LV[_level(l)]))[0] for i, l in enumerate(lods)))
ll = rec['lod_linear']['out']
tl = 0
for i, l in enumerate(lods):
    lo = 0 if l < 0 else min(math.floor(l), 4)
    fr = 0.0 if (l < 0 or lo >= 4) else l - math.floor(l)
    if ll[i] == struct.unpack('<I', struct.pack('<f', LV[lo]*(1-fr)+LV[min(lo+1, 4)]*fr))[0]:
        tl += 1
check('textureLod trilinear: float32-exact blend of adjacent levels by fractional lod, 16/16', tl == 16)
gr = rec['grad_pick']['out']
check('textureGrad: rho = max texel-gradient, lod = log2(rho), same level rule (k=1..8 -> L0,L1,L2,L2,L2,L3,L3,L3)',
      [struct.unpack('<f', struct.pack('<I', gr[i]))[0] for i in range(8)] ==
      [struct.unpack('<f', struct.pack('<f', LV[{1: 0, 2: 1, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3}[i+1]]))[0] for i in range(8)])
sys.exit(0 if all(ok) else 1)
