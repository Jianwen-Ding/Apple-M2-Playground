#!/usr/bin/env python3
"""Offline checks of the texture-target and filter-precision measurements (results/2026-10-20-texture-targets):
3D / 2D-array / cube / buffer targets, the 1/256 filter weight, the fp16 LOD with 1/64 level weight, single
12-bit rounding of trilinear results and float-format filter rounding. Inputs are regenerated from the case
generator (scripts/run_gles_texture_targets.py, fixed seed). No GPU access."""
import gzip, json, math, re, struct, sys
from fractions import Fraction as Fr
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO/'results/2026-10-20-texture-targets'
sys.path.insert(0, str(REPO/'scripts'))
from run_gles_texture_targets import cases  # noqa: E402

rec = json.load(gzip.open(D/'record.json.gz'))
C = cases()
ok = []
f = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
F32 = lambda x: f(fb(x))
h16 = lambda x: struct.unpack('<e', struct.pack('<e', x))[0]
wq = lambda a: math.floor(a*256+0.5)/256          # measured filter weight
q12 = lambda e: math.floor(e*16+0.5)/4080         # measured unorm8 filtered-result rounding (2026-10-18)


def check(name, cond):
    ok.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


def out(n):
    return rec[n]['out']


def listing(n):
    return gzip.open(D/'listings'/f'{n}.txt.gz', 'rt').read()


check(f'all {len(C)} cases ran with intact guard words', set(rec) == set(C) and all(r['run_ok'] and r['guards_intact'] for r in rec.values()))

# 3D targets
o, v = out('fetch3d_r32ui'), C['fetch3d_r32ui']['vals']
check('3D texelFetch: 512/512 texels exact (x fastest, then y, then z)', all(o[i] == v[i] for i in range(512)))
edge = []
for k, x in enumerate(o[512:]):
    t = k % 32-12; p = [(t, 3, 4), (3, t, 4), (3, 4, t)][k//32]
    edge.append(x == (v[p[2]*64+p[1]*8+p[0]] if all(0 <= c < 8 for c in p) else 0))
check('3D texelFetch out of range on any axis returns 0; 96/96 edge lanes', all(edge))
for w in ('repeat', 'mirror', 'clamp'):
    o = out('wrap3d_'+w); good = 0
    for i, x in enumerate(o):
        z = i-12; m = z % 16
        zz = z % 8 if w == 'repeat' else min(max(z, 0), 7) if w == 'clamp' else (m if m < 8 else 15-m)
        good += x == v[zz*64+5*8+2]
    check(f'3D wrap {w} in the R axis: 32/32 (z = -12..19)', good == 32)
o = out('weight_sweep3d_r32f')
check('3D z filter weight = round-half-up(frac*256)/256: 1024/1024', all(f(o[k]) == wq(k/1024) for k in range(1024)))
c, o, v = C['linear3d_r8'], out('linear3d_r8'), C['linear3d_r8']['vals']
T3 = lambda x, y, z: v[min(max(z, 0), 7)*64+min(max(y, 0), 7)*8+min(max(x, 0), 7)]


def tri(p, wf):
    cs = [F32(F32(q)/8)*8-0.5 for q in p]; i0 = [math.floor(q) for q in cs]; fr = [wf(q-math.floor(q)) for q in cs]; s = 0
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                s += (fr[0] if dx else 1-fr[0])*(fr[1] if dy else 1-fr[1])*(fr[2] if dz else 1-fr[2])*T3(i0[0]+dx, i0[1]+dy, i0[2]+dz)
    return s


q_ok = [o[i] == fb(q12(tri(p, wq))) for i, p in enumerate(c['pts'])]
ex_ok = [o[i] == fb(q12(tri(p, lambda a: a))) for i, p in enumerate(c['pts'])]
near = [abs((tri(p, wq)*16) % 1-0.5) < 0.02 for i, p in enumerate(c['pts']) if not q_ok[i]]
check('3D trilinear r8: axis sweeps 192/192 exact with 1/256 weights + 12-bit half-up rounding', all(q_ok[:192]))
check('3D trilinear r8 random points: >= 443/448 with 1/256 weights (exact weights only 245/448); every miss is within 0.02 of a 1/16-step tie',
      sum(q_ok) >= 443 and sum(ex_ok) < 300 and all(near) and len(near) == 448-sum(q_ok))
lv = C['lod3d_trilinear']['vals']
L0 = sum(lv[z*64+y*8+x] for x in (3, 4) for y in (3, 4) for z in (3, 4))/8
levels = [L0, 100, 150, 200]
good = 0
for lod, x in zip([-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0], out('lod3d_trilinear')):
    lc = min(max(lod, 0), 3); lo = int(lc); hi = min(lo+1, 3); fr = lc-lo
    good += x == fb(q12(levels[lo]*(1-fr)+levels[hi]*fr))
check('3D mipmaps (depth halves per level): trilinear level blend rounded once to the 12-bit grid, 12/12', good == 12)

# 2D arrays
o, va = out('fetcharray_r32ui'), C['fetcharray_r32ui']['vals']
check('2D-array texelFetch: 384/384 exact; layers -2,-1,6..9 return 0, layers 0..5 exact',
      all(o[i] == va[i] for i in range(384)) and all(o[384+k] == (va[(k-2)*64+43] if 0 <= k-2 < 6 else 0) for k in range(12)))
sel = [min(max(round(-2+i/16), 0), 5) for i in range(161)]     # Python round = ties to even
check('2D-array float layer = clamp(roundEven(l), 0, 5): 161/161 incl. ties 0.5->0, 1.5->2, 2.5->2, 3.5->4, 4.5->4',
      all(x == va[sel[i]*64+43] for i, x in enumerate(out('layerselect_r32ui'))))
check('the tie rule is Mesa lowering (rint + clamp in the shader before texture_sample), not hardware', 'rint' in listing('layerselect_r32ui'))
o, v = out('lineararray_r8'), C['lineararray_r8']['vals']
good = 0
for i, x in enumerate(o):
    a = (i % 64)/64; L = min(max(round((i//64)*1.3+0.2), 0), 5); b = 0.25
    t = lambda xx, yy: v[L*64+yy*8+xx]
    good += x == fb(q12((t(2, 4)*(1-a)+t(3, 4)*a)*(1-b)+(t(2, 5)*(1-a)+t(3, 5)*a)*b))
check('2D-array linear filter never blends layers: 256/256 single-layer bilinear', good == 256)

# cube


def cube_ref(d):
    x, y, z = [F32(q) for q in d]; ax, ay, az = abs(x), abs(y), abs(z)
    if ax >= ay and ax >= az:
        face, sc, tc, ma = (0, -z, -y, ax) if x >= 0 else (1, z, -y, ax)
    elif ay >= az:
        face, sc, tc, ma = (2, x, z, ay) if y >= 0 else (3, x, -z, ay)
    else:
        face, sc, tc, ma = (4, x, -y, az) if z >= 0 else (5, -x, -y, az)
    s, t = (sc/ma+1)/2, (tc/ma+1)/2
    return face, min(max(math.floor(s*4), 0), 3), min(max(math.floor(t*4), 0), 3)


o = out('cube_r32ui')
check('cube: GL major-axis face selection (ties x > y > z) and s/t mapping, 214/214 incl. 16 tie directions',
      all(((x >> 8) & 255, x & 15, (x >> 4) & 15) == cube_ref(d) and x >> 24 == 0x5a for d, x in zip(C['cube_r32ui']['dirs'], o)))
check('cube face selection is in hardware: the direction goes straight to texture_sample tex_cube', re.search(r'texture_sample.*tex_cube, r\d+_r\d+_r\d+', listing('cube_r32ui')) is not None)

# texture buffers (tex1Dfetch)
o, v = out('buffer_r32ui'), C['buffer_r32ui']['vals']
check('buffer r32ui: 1000/1000 exact, all 104 out-of-range indices (-40..-1, 1000..1063) return 0',
      all(o[i+40] == v[i] for i in range(1000)) and all(o[i] == 0 for i in list(range(40))+list(range(1040, 1104))))
check('buffer r8: k -> float32(k/255) 256/256, OOB 0', all(out('buffer_r8')[k] == fb(F32(k/255)) for k in range(256)) and set(out('buffer_r8')[256:]) == {0})
o, v = out('buffer_rgba32f'), C['buffer_rgba32f']['vals']
check('buffer rgba32f: 256/256 words exact incl. NaN payloads and -0; OOB returns (0,0,0,0) (alpha 0)', o[:256] == v[:256] and set(o[256:]) == {0})
L = listing('buffer_r32ui')
check('Mesa lowers buffers to tex_2d texture_load with x = i & mask, y = i >> 14 and a bounds select',
      re.search(r'bfeil r\d+, 0, r\d+, 14', L) and re.search(r'texture_load.*tex_2d', L) and 'icmpsel ult' in L)
o = [f(x) for x in out('oob_rgba8_alpha')]
check('2D texelFetch OOB on rgba8 returns (0,0,0,0); in-range exact', o[:4] == [F32(200/255), F32(100/255), F32(50/255), F32(25/255)] and o[4:] == [0.0]*4)
o = [f(x) for x in out('oob_r8_gba')]
check('2D texelFetch OOB on r8 returns (0,0,0,1): missing channels still swizzle to 0,0,1', o == [F32(200/255), 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])

# filter weights and level weight
o = out('weight_sweep_r32f')
check('2D x filter weight = floor(frac*256 + 0.5)/256: 4096/4096 fractions k/4096 (257 values, first step at k=8)',
      all(f(o[k]) == wq(k/4096) for k in range(4096)) and len({f(x) for x in o[:4096]}) == 257)
check('weight readout spot points (4.5 + j/64 + 1/8192): 64/64', all(f(o[4096+j]) == wq(j/64+1/8192) for j in range(64)))
o = out('lod_weight_r32f')
check('trilinear level weight = floor(fp16(lod)*64)/64: 4096/4096 (lod = k/4096)', all(f(o[k]) == math.floor(h16(k/4096)*64)/64 for k in range(4096)))
check('neither exact lod nor floor(lod*64)/64 reproduces it', sum(f(o[k]) == k/4096 for k in range(4096)) < 100 and sum(f(o[k]) == math.floor(k/64)/64 for k in range(4096)) < 4096)
check('the lod operand is 16-bit: Mesa writes it with fmul32 into a half register', re.search(r'fmul32 r\d+h, .*\n.*\n.*\n.*texture_sample.*lod_min, r\d+h', listing('lod_weight_r32f')) is not None)
v2 = C['lod_offgrid_r8']['vals']; o = out('lod_offgrid_r8')
T2 = lambda x, y: v2[min(max(y, 0), 15)*16+min(max(x, 0), 15)]
xx, yy = 6.8125-0.5, 10.1875-0.5; x0, y0 = math.floor(xx), math.floor(yy); a, b = wq(xx-x0), wq(yy-y0)
L0off = (T2(x0, y0)*(1-a)+T2(x0+1, y0)*a)*(1-b)+(T2(x0, y0+1)*(1-a)+T2(x0+1, y0+1)*a)*b
once = twice = 0
for i in range(64, 128):
    fr = math.floor(h16((i % 64)/64)*64)/64
    once += o[i] == fb(q12(L0off*(1-fr)+101*fr))
    twice += o[i] == fb(q12(math.floor(L0off*16+0.5)/16*(1-fr)+101*fr))
check('2D trilinear off the grid: one 12-bit rounding after the full blend 64/64 (rounding the level-0 bilinear first: < 64)', once == 64 and twice < 64)
check('2D trilinear at a texel centre: 64/64 with the same rule', all(o[i] == fb(q12(T2(6, 9)*(1-math.floor(h16(i/64)*64)/64)+101*math.floor(h16(i/64)*64)/64)) for i in range(64)))

# 2D random bilinear and float formats
c, o, v = C['bilinear_random_r8'], out('bilinear_random_r8'), C['bilinear_random_r8']['vals']
T = lambda x, y: v[min(max(y, 0), 15)*16+min(max(x, 0), 15)]
good = 0
for i, (px, py) in enumerate(c['pts']):
    xx = F32(F32(px)/16)*16-0.5; yy = F32(F32(py)/16)*16-0.5; x0, y0 = math.floor(xx), math.floor(yy); a, b = wq(xx-x0), wq(yy-y0)
    good += o[i] == fb(q12((T(x0, y0)*(1-a)+T(x0+1, y0)*a)*(1-b)+(T(x0, y0+1)*(1-a)+T(x0+1, y0+1)*a)*b))
check('2D bilinear r8 at 1024 random points: 1024/1024 with 1/256 weights + 12-bit half-up rounding', good == 1024)
for nm, rnd, need in (('bilinear_r16f', h16, 3813), ('bilinear_r32f', F32, 3835)):
    v = C[nm]['vals']; o = out(nm); good = worst = 0
    for i in range(3840):
        fx, fy = Fr(i % 256, 256), Fr(3, 8); cx = i//256
        t = [Fr(v[3*16+cx]), Fr(v[3*16+cx+1]), Fr(v[4*16+cx]), Fr(v[4*16+cx+1])]
        e = float((t[0]*(1-fx)+t[1]*fx)*(1-fy)+(t[2]*(1-fx)+t[3]*fx)*fy)
        r = rnd(e); good += o[i] == fb(r)
        if nm == 'bilinear_r16f':
            worst = max(worst, abs(f(o[i])-r)/max(abs(h16(r)-struct.unpack('<e', struct.pack('<H', struct.unpack('<H', struct.pack('<e', r))[0] ^ 1))[0]), 1e-30))
        else:
            worst = max(worst, abs(fb(f(o[i])) - fb(r)) if (o[i] ^ fb(r)) >> 31 == 0 else 99)
    check(f'{nm}: {good}/3840 equal the correctly rounded exact blend (need >= {need}); every other lane within 1 ulp', good >= need and worst <= 1.0001)

# images
check('3D image store/load r32ui: 512/512', all(x == (i*2654435761) & 0xffffffff for i, x in enumerate(out('image3d_r32ui'))))
check('2D-array image store/load r32ui: 384/384', all(x == (i*2246822519+7) & 0xffffffff for i, x in enumerate(out('imagearray_r32ui'))))
check('3D/array image_write encodings use tex_3d / tex_2d_array', 'image_write' in listing('image3d_r32ui') and 'tex_3d' in listing('image3d_r32ui') and 'tex_2d_array' in listing('imagearray_r32ui'))

# follow-ups: wide buffers, mipmapped arrays, seamless cube filtering
c, o = C['buffer_wide_r32ui'], out('buffer_wide_r32ui')
check('buffer wider than 16384 (70000 texels): 176/176 across every 16384-texel row boundary, OOB tail returns 0',
      all(x == (c['vals'][k] if k < 70000 else 0) for k, x in zip(c['idx'], o)))
o = out('mip_array_r8')
check('mipmapped 2D array: level = ceil(lod-0.5) clamped, per layer, 64/64',
      all(x == 10+40*min(max(math.ceil((i % 16)*0.25-0.5), 0), 3)+i//16 for i, x in enumerate(o)))
o = [f(x)*255 for x in out('cube_seam_r8')]
exp = [100-10*min(k, 8) for k in range(33)] + [100+10*min(k, 8) for k in range(1, 33)]
check('cube linear filtering is seamless: 50/50 blend of +X and +Z at the shared edge, linear over half a texel, 65/65',
      all(abs(g-e) < 1e-4 for g, e in zip(o, exp)))

print(f'{sum(ok)}/{len(ok)} texture-target checks passed')
sys.exit(0 if all(ok) else 1)
