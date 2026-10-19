#!/usr/bin/env python3
"""Texture / image semantics and encodings through Mesa's GLES driver (safe-05). Mesa builds all texture, sampler and image state; nothing is
hand-encoded and no texture word is edited. Each case: a GLSL ES 3.2 compute shader (tests/gles_compute.c with GLES_SHADER_FILE and the GLES_TEX_*
variables), a texture with known contents, the outputs recorded as raw words, plus the AGX binary captured from Mesa's shader cache.
  run_gles_texture.py [--out DIR] [--only NAME]
Cases: fetch_r8 / fetch_snorm / fetch_srgb / fetch_r16f (every texel value of the format), bilinear_r8 (256 sub-texel positions x 15 cells),
nearest_wrap_{clamp,repeat,mirror} (out-of-range coordinates), image_rgba8 (read-only imageLoad of every 8-bit value; outputs are r then g), image_r32f (store then load).
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INC = Path('/save/workspace/AGX_Probe/mesa/include')
HEAD = ("#version 320 es\nprecision highp int;\nprecision highp float;\nprecision highp sampler2D;\nprecision highp image2D;\n"
        "layout(local_size_x=32, local_size_y=1, local_size_z=1) in;\nlayout(std430, binding=0) buffer Output { uint data[]; };\nuniform uint count;\n")
TEX = "layout(binding=0) uniform highp sampler2D tex;\n"


def fbits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def cases():
    rng = random.Random(7)
    out = {}
    # 1. exhaustive 8-bit formats and 16-bit float through texelFetch
    out['fetch_r8'] = dict(fmt='r8', w=16, h=16, data=bytes(range(256)), count=256, filt='nearest',
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=floatBitsToUint(texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0).r); }\n")
    out['fetch_snorm'] = dict(fmt='r8snorm', w=16, h=16, data=bytes(range(256)), count=256, filt='nearest',
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=floatBitsToUint(texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0).r); }\n")
    srgb = bytes(b for v in range(256) for b in (v, 0, 0, 255))
    out['fetch_srgb'] = dict(fmt='rgba8srgb', w=16, h=16, data=srgb, count=256, filt='nearest',
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=floatBitsToUint(texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0).r); }\n")
    out['fetch_r16f'] = dict(fmt='r16f', w=256, h=256, data=b''.join(struct.pack('<H', v) for v in range(65536)), count=65536, filt='nearest',
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=floatBitsToUint(texelFetch(tex, ivec2(int(i%256u),int(i/256u)), 0).r); }\n")
    # 2. bilinear: 16x16 r8 random texels; lane i: fraction a = i % 256 in x (units 1/256), cell cx = i / 256, fy = 0.375, row 3
    vals = [rng.randrange(256) for _ in range(256)]
    out['bilinear_r8'] = dict(fmt='r8', w=16, h=16, data=bytes(vals), count=256*15, filt='linear', vals=vals,
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float fx=float(i%256u)/256.0; float cx=float(i/256u); "
                      "vec2 uv=(vec2(cx+0.5+fx, 3.5+0.375))/16.0; data[8u+i]=floatBitsToUint(textureLod(tex, uv, 0.0).r); } }\n")
    # 3. nearest filtering with out-of-range coordinates, three wrap modes: x from -20 to 35 at row 5
    wrapvals = [rng.randrange(1, 255) for _ in range(256)]
    for wrap in ('clamp', 'repeat', 'mirror'):
        out[f'nearest_wrap_{wrap}'] = dict(fmt='r8', w=16, h=16, data=bytes(wrapvals), count=56, filt='nearest', wrap=wrap, vals=wrapvals,
            glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float x=float(int(i)-20); "
                          "vec2 uv=vec2(x+0.5, 5.5)/16.0; data[8u+i]=floatBitsToUint(textureLod(tex, uv, 0.0).r); } }\n")
    # 4. image store then load: rgba8 unorm rounding of i/1023 in the red channel; r32f round trip
    # (GLES allows read-write images only in the 32-bit formats: the rgba8 image is read only)
    out['image_rgba8'] = dict(fmt='rgba8', w=16, h=16, data=bytes(b for v in range(256) for b in (v, 255-v, 0, 255)), count=512, filt='nearest', image=True,
        glsl=HEAD+"layout(rgba8, binding=0) readonly uniform highp image2D img;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count && i<256u){ ivec2 p=ivec2(int(i%16u),int(i/16u)); "
              "vec4 v=imageLoad(img, p); data[8u+i]=floatBitsToUint(v.r); data[8u+256u+i]=floatBitsToUint(v.g); } }\n")
    out['image_r32f'] = dict(fmt='r32f', w=32, h=32, data=bytes(4*1024), count=1024, filt='nearest', image=True,
        glsl=HEAD+"layout(r32f, binding=0) uniform highp image2D img;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec2 p=ivec2(int(i%32u),int(i/32u)); "
              "imageStore(img, p, vec4(uintBitsToFloat(0x3f800000u + i*977u), 0.0, 0.0, 0.0)); memoryBarrierImage(); data[8u+i]=floatBitsToUint(imageLoad(img, p).r); } }\n")
    # 5. integer and wide formats through texelFetch (usampler needs its own precision statement)
    UH = HEAD+"precision highp usampler2D;\n"
    out['fetch_r8ui'] = dict(fmt='r8ui', w=16, h=16, data=bytes(range(256)), count=256, filt='nearest',
        glsl=UH+"layout(binding=0) uniform highp usampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0).r; }\n")
    u32 = [rng.getrandbits(32) for _ in range(256)]
    out['fetch_r32ui'] = dict(fmt='r32ui', w=16, h=16, data=b''.join(struct.pack('<I', v) for v in u32), count=256, filt='nearest', vals=u32,
        glsl=UH+"layout(binding=0) uniform highp usampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0).r; }\n")
    out['fetch_rgba8snorm'] = dict(fmt='rgba8snorm', w=16, h=16, data=bytes(b for v in range(256) for b in (v, 255-v, 0, 0)), count=512, filt='nearest',
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<256u && i<count){ vec4 v=texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0); data[8u+i]=floatBitsToUint(v.r); data[8u+256u+i]=floatBitsToUint(v.g); } }\n")
    f32 = [0x00000000, 0x80000000, 0x00000001, 0x007fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0x7f7fffff] + [rng.getrandbits(32) for _ in range(248)]
    out['fetch_rgba32f'] = dict(fmt='rgba32f', w=16, h=16, data=b''.join(struct.pack('<4I', v, v ^ 0x80000000, v, v) for v in f32), count=256, filt='nearest', vals=f32,
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count) data[8u+i]=floatBitsToUint(texelFetch(tex, ivec2(int(i%16u),int(i/16u)), 0).g); }\n")
    # 6. out-of-range integer coordinates through texelFetch (no wrap mode applies; measures the raw edge rule)
    oob = [rng.getrandbits(32) for _ in range(256)]
    out['oob_fetch_r32ui'] = dict(fmt='r32ui', w=16, h=16, data=b''.join(struct.pack('<I', v) for v in oob), count=64, filt='nearest', vals=oob,
        glsl=UH+"layout(binding=0) uniform highp usampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec2 p = i < 32u ? ivec2(int(i)-8, 5) : ivec2(5, int(i-32u)-8); "
              "data[8u+i]=texelFetch(tex, p, 0).r; } }\n")
    # 7. textureGather (tld4 equivalent) on r8: 2x2 footprint at texel corners and centres
    gvals = [rng.randrange(256) for _ in range(256)]
    out['gather_r8'] = dict(fmt='r8', w=16, h=16, data=bytes(gvals), count=64, filt='nearest', vals=gvals,
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ vec2 uv = (i < 32u ? vec2(float(i)+0.5, 5.0) : vec2(5.0, float(i-32u)+0.5))/16.0; "
              "vec4 g=textureGather(tex, uv); data[8u+i]=uint(g.r*255.0+0.5)+uint(g.g*255.0+0.5)*256u+uint(g.b*255.0+0.5)*65536u+uint(g.a*255.0+0.5)*16777216u; } }\n")
    # 8. bilinear filtering of an sRGB texture (does the 12-bit grid apply after sRGB decode?)
    svals = [rng.randrange(256) for _ in range(256)]
    out['bilinear_srgb'] = dict(fmt='rgba8srgb', w=16, h=16, data=bytes(b for v in svals for b in (v, 0, 0, 255)), count=256*15, filt='linear', vals=svals,
        glsl=HEAD+TEX+"void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float fx=float(i%256u)/256.0; float cx=float(i/256u); "
                      "vec2 uv=(vec2(cx+0.5+fx, 3.5+0.375))/16.0; data[8u+i]=floatBitsToUint(textureLod(tex, uv, 0.0).r); } }\n")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/gles-texture'))
    p.add_argument('--only')
    a = p.parse_args()
    out = a.out; out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', f'-I{INC}', str(REPO/'tests/gles_compute.c'), '-o', str(out/'gles_compute'), '-ldl'], check=True)
    rec = {}
    for name, c in cases().items():
        if a.only and name != a.only:
            continue
        d = out/name; subprocess.run(['rm', '-rf', str(d)], check=True); d.mkdir()
        (d/'shader.glsl').write_text(c['glsl']); (d/'tex.bin').write_bytes(c['data'])
        cache = d/'cache'; cache.mkdir()
        env = {'PATH': '/usr/bin', 'GLES_SHADER_FILE': str(d/'shader.glsl'), 'GLES_TEX_FORMAT': c['fmt'], 'GLES_TEX_W': str(c['w']), 'GLES_TEX_H': str(c['h']),
               'GLES_TEX_DATA': str(d/'tex.bin'), 'GLES_TEX_FILTER': c['filt'], 'GLES_TEX_WRAP': c.get('wrap', 'clamp'),
               'MESA_SHADER_CACHE_DIR': str(cache), 'MESA_SHADER_CACHE_DISABLE': 'false'}
        if c.get('image'):
            env['GLES_TEX_IMAGE'] = '1'
        r = subprocess.run([str(out/'gles_compute'), 'index', str(c['count']), '/dev/dri/renderD128'], cwd=d, capture_output=True, timeout=300, env=env)
        (d/'stdout.txt').write_bytes(r.stdout)
        res = {'run_ok': r.returncode == 0 and (d/'output.bin').exists(), 'count': c['count']}
        if res['run_ok']:
            groups = (c['count']+31)//32
            w = struct.unpack(f'<{8+groups*32+8}I', (d/'output.bin').read_bytes())
            res['guards_intact'] = all(x == 0xcdcdcdcd for x in w[:8]) and all(x == 0xcdcdcdcd for x in w[8+c['count']:8+groups*32+8][-8:])
            res['out'] = list(w[8:8+c['count']])
        else:
            res['stderr'] = r.stderr.decode()[-300:]
        rec[name] = res
        print(name, {k: (v if k != 'out' else f'{len(v)} words') for k, v in res.items()}, flush=True)
    (out/'record.json').write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    sys.exit(main())
