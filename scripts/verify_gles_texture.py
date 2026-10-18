#!/usr/bin/env python3
"""Offline checks of the Mesa-GLES texture / image measurements (results/2026-10-18-gles-texture). No GPU access."""
import gzip, json, math, random, struct, sys
from pathlib import Path

D = Path(__file__).resolve().parents[1]/'results/2026-10-18-gles-texture'
rec = json.load(gzip.open(D/'record.json.gz'))
ok = []
f = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


check('all 14 cases ran with intact guard words', len(rec) == 14 and all(r['run_ok'] and r.get('guards_intact', True) for r in rec.values()))
check('r8 unorm: all 256 values equal float32(k/255)', all(rec['fetch_r8']['out'][k] == fb(k/255) for k in range(256)))
sn = lambda k: max((k-256 if k >= 128 else k)/127, -1.0)
check('r8 snorm: all 256 values equal max(k/127, -1) (-128 and -127 both give -1)', all(rec['fetch_snorm']['out'][k] == fb(sn(k)) for k in range(256)))


def srgb(c):
    x = c/255
    return x/12.92 if x <= 0.04045 else ((x+0.055)/1.055)**2.4


check('sRGB8 decode: all 256 values equal float32(round(srgb(k) * 4095) / 4095) (12-bit table, not float32 of the formula)',
      all(rec['fetch_srgb']['out'][k] == fb(round(srgb(k)*4095)/4095) for k in range(256)))


def h2f(v):
    s = -1 if v & 0x8000 else 1; e = (v >> 10) & 31; m = v & 1023
    if e == 0: return math.copysign(m*2**-24, s)
    if e == 31: return float('nan') if m else s*math.inf
    return s*(1+m/1024)*2**(e-15)


o = rec['fetch_r16f']['out']
bad = [v for v in range(65536) if not math.isnan(h2f(v)) and o[v] != fb(h2f(v))]
nanok = all((o[v] & 0x7f800000) == 0x7f800000 and o[v] & 0x7fffff for v in range(65536) if (v & 0x7c00) == 0x7c00 and v & 0x3ff)
check('r16f fetch: all 63,490 non-NaN half patterns exact (denormals kept, -0 stays -0, infinities kept) and all 2,046 NaN patterns stay NaN', bad == [] and nanok and o[32768] == 0x80000000)
rng = random.Random(7); vals = [rng.randrange(256) for _ in range(256)]
tx = lambda x, y: vals[y*16+x]
o = rec['bilinear_r8']['out']


def ex(i):
    a = i % 256; cx = i//256; fx = a/256; fy = 0.375
    t = [tx(cx, 3), tx(cx+1, 3), tx(cx, 4), tx(cx+1, 4)]
    return (t[0]*(1-fx)+t[1]*fx)*(1-fy)+(t[2]*(1-fx)+t[3]*fx)*fy


check('bilinear r8 (256 sub-texel positions x 15 cells): every result is float32(floor(exact*16 + 0.5) / 4080), i.e. round-half-up to 1/16 of a unorm step (12 bits)',
      all(o[i] == fb(math.floor(ex(i)*16+0.5)/4080) for i in range(3840)))
check('bilinear: neither floor nor nearest-even reproduces it (the tie rule is half-up)', sum(o[i] == fb(math.floor(ex(i)*16)/4080) for i in range(3840)) < 3840 and sum(o[i] == fb(round(ex(i)*16)/4080) for i in range(3840)) < 3840)
wv = [rng.randrange(1, 255) for _ in range(256)]
fn = {'clamp': lambda x: min(max(x, 0), 15), 'repeat': lambda x: x % 16, 'mirror': lambda x: (x % 32) if x % 32 < 16 else 31-x % 32}
check('nearest sampling x in [-20, 35]: clamp, repeat and mirror-repeat each exact for all 56 positions',
      all(rec[f'nearest_wrap_{m}']['out'][i] == fb(wv[5*16+g(i-20)]/255) for m, g in fn.items() for i in range(56)))
o = rec['image_rgba8']['out']
check('imageLoad rgba8 unorm: r and g of all 256 values equal float32(k/255)', all(o[v] == fb(v/255) and o[256+v] == fb((255-v)/255) for v in range(256)))
o = rec['image_r32f']['out']
check('imageStore / imageLoad r32f round trip is bit-exact for 1,024 patterns', all(o[i] == (0x3f800000+i*977) & 0xffffffff for i in range(1024)))
[rng.randrange(1, 255) for _ in range(0)]
u32 = [rng.getrandbits(32) for _ in range(256)]
f32 = [0, 0x80000000, 1, 0x7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0x7f7fffff] + [rng.getrandbits(32) for _ in range(248)]
check('integer fetch: r8ui (256 values) and r32ui (256 random words) exact', rec['fetch_r8ui']['out'] == list(range(256)) and rec['fetch_r32ui']['out'] == u32)
o = rec['fetch_rgba8snorm']['out']
check('rgba8snorm: r and g channels of all 256 values equal max(k/127, -1)', all(o[k] == fb(sn(k)) and o[256+k] == fb(sn(255-k)) for k in range(256)))
check('rgba32f fetch is bit-exact for 256 patterns incl. denormals, infinities, -0 and NaN payloads', rec['fetch_rgba32f']['out'] == [v ^ 0x80000000 for v in f32])
sys.exit(0 if all(ok) else 1)
