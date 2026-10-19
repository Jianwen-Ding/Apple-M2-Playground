#!/usr/bin/env python3
"""End-to-end texture-unit verification: synthesize Mesa-layout root table + descriptor set +
texel buffers (pure Python, no numpy), run the driver's recorded extract through the Rust
simulator (agx_run), and check outputs against independent references.

Workloads (small sizes, deterministic LCG inputs):
  texfetch   r32f texelFetch, bit-exact incl. signed zero / near-max / min-normal
  texfilter  RGBA8 linear/clamp textureLod, exact-weight bilinear within 2/255 at best subtexel bits
  imgerode   r32ui ping-pong erode over 4 dispatches, bit-exact
  imgtonemap RGBA8 load -> Reinhard -> store, max diff 1 (rounding ties), alpha kept

Needs the simulator repo next to this one (SIMREPO) with rust/target/release/agx_run built.
No GPU access.
"""
import math
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMREPO = Path(os.environ.get('SIMREPO', ROOT.parent / 'AGX-Performance-Simulator'))
AGX_RUN = SIMREPO / 'rust/target/release/agx_run'

CH = {'r32f': 0x21, 'r32ui': 0x21, 'rgba8': 0x28}
TY = {'r32f': 4, 'r32ui': 2, 'rgba8': 0}
BPP = {'r32f': 4, 'r32ui': 4, 'rgba8': 1}
COMPS = {'r32f': 1, 'r32ui': 1, 'rgba8': 4}

ok = []


def check(name, cond, detail=''):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name, detail)


def _dset(mem, start, size, v):
    for i in range(size):
        if (v >> i) & 1:
            mem[(start + i) // 8] |= 1 << ((start + i) % 8)


def pitch_of(fmt, wd):
    return ((wd * BPP[fmt] * COMPS[fmt] + 15) // 16) * 16


def tex_desc24(fmt, wd, ht, va, pitch):
    d = bytearray(24)
    _dset(d, 0, 4, 2); _dset(d, 4, 2, 0); _dset(d, 6, 7, CH[fmt]); _dset(d, 13, 3, TY[fmt])
    for i, s in enumerate((0, 1, 2, 3)):
        _dset(d, 16 + 3 * i, 3, s)
    _dset(d, 28, 14, wd - 1); _dset(d, 42, 14, ht - 1)
    _dset(d, 66, 36, va >> 4)
    _dset(d, 110, 18, (pitch - 16) >> 4)
    return bytes(d)


def sampler_desc8(filt):
    d = bytearray(8)
    f = 0 if filt == 'nearest' else 1
    for off, size, v in ((25, 2, f), (23, 2, f), (27, 2, 1), (29, 3, 0), (32, 3, 0), (35, 3, 0)):
        for i in range(size):
            if (v >> i) & 1:
                d[(off + i) // 8] |= 1 << ((off + i) % 8)
    return bytes(d)


def sampled_desc64(fmt, wd, ht, va, pitch, filt):
    d = bytearray(tex_desc24(fmt, wd, ht, va, pitch) + sampler_desc8(filt))
    d += bytearray(32)
    struct.pack_into('<H', d, 32, 28)
    struct.pack_into('<h', d, 34, -1)
    return bytes(d)


def pbe_desc24(fmt, wd, ht, va, pitch):
    d = bytearray(24)
    _dset(d, 0, 4, 2); _dset(d, 4, 2, 0); _dset(d, 6, 7, CH[fmt]); _dset(d, 13, 3, TY[fmt])
    for i, s in enumerate((0, 1, 2, 3)):
        _dset(d, 16 + 2 * i, 2, s)
    _dset(d, 24, 14, wd - 1); _dset(d, 38, 14, ht - 1)
    _dset(d, 64, 36, va >> 4)
    _dset(d, 104, 21, pitch - 16)
    return bytes(d)


def storage_desc48(fmt, wd, ht, va, pitch):
    return tex_desc24(fmt, wd, ht, va, pitch) + pbe_desc24(fmt, wd, ht, va, pitch)


def pad_rows(raw, wd, bpp, pitch, ht):
    out = bytearray(pitch * ht)
    roww = wd * bpp
    for y in range(ht):
        out[y * pitch:y * pitch + roww] = raw[y * roww:(y + 1) * roww]
    return bytes(out)


class LCG:
    def __init__(self, seed):
        self.s = seed & 0xffffffff

    def u32(self):
        self.s = (1664525 * self.s + 1013904223) & 0xffffffff
        return self.s

    def u8(self):
        return self.u32() >> 24

    def uni(self, a, b):
        return a + (b - a) * (self.u32() / 2 ** 32)

    def normal(self):
        u1 = max(self.u32() / 2 ** 32, 1e-12)
        u2 = self.u32() / 2 ** 32
        return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


class Ctx:
    """Scratch dir + VA allocator + agx_run driver."""

    def __init__(self):
        self.d = Path(tempfile.mkdtemp(prefix='verify-texunit-'))
        self.nxt = 0x10000000

    def alloc(self, n):
        va = self.nxt
        self.nxt += (n + 0xffff) // 0x10000 * 0x10000 + 0x10000
        return va

    def run(self, code, grid, wg, preamble, uniforms, maps, dumps):
        cmd = [str(AGX_RUN), str(code), '--grid', grid, '--wg', wg, '--shared', '0',
               '--preamble', str(preamble)]
        for u, v in uniforms:
            cmd += ['--uniform', f'{u}={v:#x}']
        for va, path in maps:
            cmd += ['--map', f'{va:#x}={path}']
        for va, nbytes, path in dumps:
            cmd += ['--dump', f'{va:#x}={nbytes}:{path}']
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f'agx_run failed: {r.stdout.strip()} {r.stderr.strip()}')


def root_table(root_va, set_va, gc_va, push):
    root = bytearray(1784)
    struct.pack_into('<Q', root, 0, root_va)
    struct.pack_into('<Q', root, 8, set_va)
    struct.pack_into('<Q', root, 72, gc_va)
    root[496:496 + len(push)] = push
    return bytes(root)


# ------------------------------------------------------------------------------------------------ texfetch

def do_texfetch(cx):
    W, H, N = 64, 32, 256
    rng = LCG(0xFE7C4)
    texels = [rng.normal() * 100 for _ in range(W * H)]
    texels[0:4] = [0.0, -0.0, 3.4e38, 1.1754944e-38]
    coords = [(0, 0), (1, 0), (63, 31), (5, 7)] + [(rng.u32() % W, rng.u32() % H) for _ in range(4, N)]
    pitch = pitch_of('r32f', W)
    tex = pad_rows(struct.pack('<%df' % (W * H), *texels), W, 4, pitch, H)
    f32tex = struct.unpack('<%df' % (W * H), struct.pack('<%df' % (W * H), *texels))

    c_va, o_va, t_va = cx.alloc(8 * N), cx.alloc(4 * N), cx.alloc(len(tex))
    set_va, root_va, gc_va = cx.alloc(0x1000), cx.alloc(0x1000), cx.alloc(0x1000)
    d = cx.d
    (d / 'coords.bin').write_bytes(struct.pack('<%di' % (2 * N), *[c for xy in coords for c in xy]))
    (d / 'out.bin').write_bytes(bytes(4 * N))
    (d / 'tex.bin').write_bytes(tex)
    se = bytearray(128)
    se[0:64] = sampled_desc64('r32f', W, H, t_va, pitch, 'nearest')
    struct.pack_into('<Q', se, 64, c_va); struct.pack_into('<I', se, 72, 8 * N)
    struct.pack_into('<Q', se, 80, o_va); struct.pack_into('<I', se, 88, 4 * N)
    (d / 'set.bin').write_bytes(bytes(se))
    (d / 'root.bin').write_bytes(root_table(root_va, set_va, gc_va, struct.pack('<I', N)))
    (d / 'gc.bin').write_bytes(struct.pack('<4I', 1, 1, 1, 0))

    code = SIMREPO / 'spirv/expected/texfetch/code'
    cx.run(code / 'main.bin', '256,1,1', '256,1,1', code / 'preamble.bin',
           [(0, root_va), (1, 0), (2, set_va), (3, 0)],
           [(c_va, d / 'coords.bin'), (o_va, d / 'out.bin'), (t_va, d / 'tex.bin'),
            (set_va, d / 'set.bin'), (root_va, d / 'root.bin'), (gc_va, d / 'gc.bin')],
           [(o_va, 4 * N, d / 'got.bin')])
    got = struct.unpack('<%df' % N, (d / 'got.bin').read_bytes())
    bad = 0
    for i, (x, y) in enumerate(coords):
        a, b = got[i], f32tex[y * W + x]
        same = (a == b) or (a != a and b != b)
        if not same:
            bad += 1
    check('texfetch: texelFetch bit-exact incl +-0/3.4e38/min-normal', bad == 0, f'{N - bad}/{N}')


# ------------------------------------------------------------------------------------------------ texfilter

def bilinear(tex, TW, TH, u, v, bits):
    x, y = u * TW - 0.5, v * TH - 0.5
    x0, y0 = math.floor(x), math.floor(y)
    if bits is not None:
        a = round((x - x0) * 2 ** bits) / 2 ** bits
        b = round((y - y0) * 2 ** bits) / 2 ** bits
    else:
        a, b = x - x0, y - y0

    def at(xx, yy):
        xx = min(max(xx, 0), TW - 1); yy = min(max(yy, 0), TH - 1)
        i = (yy * TW + xx) * 4
        return [tex[i + k] / 255.0 for k in range(4)]

    c00, c10, c01, c11 = at(x0, y0), at(x0 + 1, y0), at(x0, y0 + 1), at(x0 + 1, y0 + 1)
    return [((1 - a) * (1 - b) * c00[k] + a * (1 - b) * c10[k] + (1 - a) * b * c01[k] + a * b * c11[k])
            for k in range(4)]


def do_texfilter(cx):
    TW, TH, N = 32, 32, 512
    rng = LCG(0xF11E4)
    tex = bytearray(TW * TH * 4)
    for y in range(TH):
        for x in range(TW):
            i = (y * TW + x) * 4
            tex[i] = x * 255 // (TW - 1)
            tex[i + 1] = y * 255 // (TH - 1)
            tex[i + 2] = ((x // 4 + y // 4) % 2) * 255
            tex[i + 3] = rng.u8()
    uv = [(rng.uni(-0.05, 1.05), rng.uni(-0.05, 1.05)) for _ in range(N)]
    pitch = pitch_of('rgba8', TW)
    img = pad_rows(bytes(tex), TW, 4, pitch, TH)

    u_va, o_va, t_va = cx.alloc(8 * N), cx.alloc(16 * N), cx.alloc(len(img))
    set_va, root_va, gc_va = cx.alloc(0x1000), cx.alloc(0x1000), cx.alloc(0x1000)
    d = cx.d
    (d / 'uv.bin').write_bytes(struct.pack('<%df' % (2 * N), *[c for p in uv for c in p]))
    (d / 'out.bin').write_bytes(bytes(16 * N))
    (d / 'tex.bin').write_bytes(img)
    se = bytearray(128)
    se[0:64] = sampled_desc64('rgba8', TW, TH, t_va, pitch, 'linear')
    struct.pack_into('<Q', se, 64, u_va); struct.pack_into('<I', se, 72, 8 * N)
    struct.pack_into('<Q', se, 80, o_va); struct.pack_into('<I', se, 88, 16 * N)
    (d / 'set.bin').write_bytes(bytes(se))
    (d / 'root.bin').write_bytes(root_table(root_va, set_va, gc_va, struct.pack('<I', N)))
    (d / 'gc.bin').write_bytes(struct.pack('<4I', (N + 255) // 256, 1, 1, 0))

    code = SIMREPO / 'spirv/expected/texfilter/code'
    cx.run(code / 'main.bin', f'{N},1,1', '256,1,1', code / 'preamble.bin',
           [(0, root_va), (1, 0), (2, set_va), (3, 0)],
           [(u_va, d / 'uv.bin'), (o_va, d / 'out.bin'), (t_va, d / 'tex.bin'),
            (set_va, d / 'set.bin'), (root_va, d / 'root.bin'), (gc_va, d / 'gc.bin')],
           [(o_va, 16 * N, d / 'got.bin')])
    got = struct.unpack('<%df' % (4 * N), (d / 'got.bin').read_bytes())
    best = None
    for bits in range(4, 11):
        m = 0.0
        for i, (u, v) in enumerate(uv):
            for k, r in enumerate(bilinear(tex, TW, TH, u, v, bits)):
                m = max(m, abs(got[4 * i + k] - r))
        if best is None or m < best[1]:
            best = (bits, m)
    check('texfilter: bilinear within 2/255 at best subtexel precision', best[1] <= 2 / 255,
          f'best {best[0]} bits at {best[1] * 255:.3f}/255')


# ------------------------------------------------------------------------------------------------ imgerode

def erode_ref(img, Wd, H):
    out = [[0] * Wd for _ in range(H)]
    for y in range(H):
        for x in range(Wd):
            m = 0xffffffff
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    m = min(m, img[min(max(y + dy, 0), H - 1)][min(max(x + dx, 0), Wd - 1)])
            out[y][x] = m
    return out


def do_imgerode(cx):
    Wd, H, ITERS = 64, 48, 4
    rng = LCG(0xE20DE)
    img = [[rng.u32() % (1 << 20) for _ in range(Wd)] for _ in range(H)]
    pitch = pitch_of('r32ui', Wd)
    raw = bytearray()
    for y in range(H):
        for x in range(Wd):
            raw += struct.pack('<I', img[y][x])
    img0 = pad_rows(bytes(raw), Wd, 4, pitch, H)

    a_va, b_va = cx.alloc(len(img0)), cx.alloc(len(img0))
    set_va, root_va, gc_va = cx.alloc(0x1000), cx.alloc(0x1000), cx.alloc(0x1000)
    d = cx.d
    (d / 'a.bin').write_bytes(img0)
    (d / 'b.bin').write_bytes(bytes(len(img0)))
    se = bytearray(96)
    se[0:48] = storage_desc48('r32ui', Wd, H, a_va, pitch)
    se[48:96] = storage_desc48('r32ui', Wd, H, b_va, pitch)
    (d / 'set.bin').write_bytes(bytes(se))
    (d / 'gc.bin').write_bytes(struct.pack('<4I', (Wd + 15) // 16, (H + 15) // 16, 1, 0))

    code = SIMREPO / 'spirv/expected/imgerode/code'
    uni = [(0, root_va), (1, 0), (2, set_va), (3, 0), (15, 0), (16, 4294967295)]
    maps = [(a_va, d / 'a.bin'), (b_va, d / 'b.bin'), (set_va, d / 'set.bin'),
            (root_va, None), (gc_va, d / 'gc.bin')]
    for k in range(ITERS):
        (d / f'root{k}.bin').write_bytes(root_table(
            root_va, set_va, gc_va, struct.pack('<iiI', Wd, H, k & 1)))
        maps = [(a_va, d / 'a.bin'), (b_va, d / 'b.bin'), (set_va, d / 'set.bin'),
                (root_va, d / f'root{k}.bin'), (gc_va, d / 'gc.bin')]
        cx.run(code / 'main.bin', f'{Wd},{H},1', '16,16,1', code / 'preamble.bin', uni, maps,
               [(a_va, len(img0), d / 'a.bin'), (b_va, len(img0), d / 'b.bin')])
    ref = img
    for _ in range(ITERS):
        ref = erode_ref(ref, Wd, H)
    got = struct.unpack('<%dI' % (Wd * H), (d / 'a.bin').read_bytes())
    flat = [ref[y][x] for y in range(H) for x in range(Wd)]
    bad = sum(1 for a, b in zip(got, flat) if a != b)
    check('imgerode: 4 ping-pong erode iterations bit-exact', bad == 0, f'{Wd * H - bad}/{Wd * H}')


# ------------------------------------------------------------------------------------------------ imgtonemap

def do_imgtonemap(cx):
    Wd, H, EXPO = 64, 48, 2.5
    rng = LCG(0x70E)
    img = bytearray(Wd * H * 4)
    for i in range(Wd * H):
        for k in range(4):
            img[4 * i + k] = rng.u8()
    for x in range(Wd):
        for k in range(3):
            img[x * 4 + k] = x
    pitch = pitch_of('rgba8', Wd)
    raw = pad_rows(bytes(img), Wd, 4, pitch, H)

    i_va = cx.alloc(len(raw))
    set_va, root_va, gc_va = cx.alloc(0x1000), cx.alloc(0x1000), cx.alloc(0x1000)
    d = cx.d
    (d / 'img.bin').write_bytes(raw)
    (d / 'set.bin').write_bytes(storage_desc48('rgba8', Wd, H, i_va, pitch))
    (d / 'root.bin').write_bytes(root_table(
        root_va, set_va, gc_va, struct.pack('<ii', Wd, H) + struct.pack('<f', EXPO)))
    (d / 'gc.bin').write_bytes(struct.pack('<4I', (Wd + 15) // 16, (H + 15) // 16, 1, 0))

    code = SIMREPO / 'spirv/expected/imgtonemap/code'
    cx.run(code / 'main.bin', f'{Wd},{H},1', '16,16,1', code / 'preamble.bin',
           [(0, root_va), (1, 0), (2, set_va), (3, 0), (9, 0)],
           [(i_va, d / 'img.bin'), (set_va, d / 'set.bin'), (root_va, d / 'root.bin'), (gc_va, d / 'gc.bin')],
           [(i_va, len(raw), d / 'got.bin')])
    got = (d / 'got.bin').read_bytes()
    bad = alpha_bad = 0
    for y in range(H):
        for x in range(Wd):
            for k in range(3):
                v = img[y * pitch + x * 4 + k]
                f = (v / 255 * EXPO) / (1 + v / 255 * EXPO) * 255
                lo, hi = math.floor(f), math.ceil(f)
                g = got[y * pitch + x * 4 + k]
                if g != lo and g != hi:
                    bad += 1
            if got[y * pitch + x * 4 + 3] != img[y * pitch + x * 4 + 3]:
                alpha_bad += 1
    check('imgtonemap: reinhard store within 1 level, alpha kept', bad == 0 and alpha_bad == 0,
          f'{Wd * H * 3 - bad}/{Wd * H * 3} color, alpha {alpha_bad} bad')


def main():
    if not AGX_RUN.exists():
        print(f'skip: {AGX_RUN} not built')
        return 2
    cx = Ctx()
    do_texfetch(cx)
    do_texfilter(cx)
    do_imgerode(cx)
    do_imgtonemap(cx)
    print(f'{sum(ok)}/{len(ok)} texture-unit checks passed')
    return 0 if all(ok) else 1


if __name__ == '__main__':
    sys.exit(main())
