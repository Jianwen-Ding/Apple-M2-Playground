#!/usr/bin/env python3
"""B29 (native texture sampling against ZLUDA's software reference): the probes existing findings did not cover, through
Mesa's GLES driver (Mesa builds every texture, sampler and image state word; nothing hand-encoded).
  depth compare (sampler2DShadow, all 8 functions; nearest, and linear = PCF or compare-after-filter?)
  textureGrad LOD selection (isotropic and anisotropic gradients) and the MIN_LOD / MAX_LOD clamps
  formatted image stores: float -> unorm8 / snorm8 rounding, out-of-range integers -> rgba8ui / rgba8i / rgba16ui / rgba16i
  run_gles_b29.py [--out DIR] [--only NAME]; analysis: verify_b29.py (offline)."""
import argparse, math, random, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gles_texture import run_cases  # noqa: E402

HEAD = ("#version 320 es\nprecision highp int;\nprecision highp usampler2D;\nprecision highp isampler2D;\nprecision highp float;\nprecision highp sampler2DShadow;\n"
        "precision highp sampler2D;\nprecision highp image2D;\nprecision highp uimage2D;\nprecision highp iimage2D;\n"
        "layout(local_size_x=32, local_size_y=1, local_size_z=1) in;\nlayout(std430, binding=0) buffer Output { uint data[]; };\nuniform uint count;\n")
F32 = lambda v: b''.join(struct.pack('<f', x) for x in v)
FUNCS = ['never', 'less', 'equal', 'lequal', 'greater', 'notequal', 'gequal', 'always']
DEPTH = [i / 16 for i in range(16)]          # texel i holds i/16

def cases():
    out = {}
    # depth compare, nearest: lane = 4 * texel + j, ref = texel depth + (-1/64, 0, +1/64, +1/2)[j]
    refs = lambda i, j: DEPTH[i] + (-1/64, 0.0, 1/64, 0.5)[j]
    for fn in FUNCS:
        out[f'shadow_nearest_{fn}'] = dict(fmt='d32f', w=16, h=1, data=F32(DEPTH), count=64, filt='nearest', compare=fn,
            glsl=HEAD + "layout(binding=0) uniform highp sampler2DShadow tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x;"
                 " if(i<count){ uint t=i/4u, j=i%4u; float off = j==0u?-1.0/64.0: j==1u?0.0: j==2u?1.0/64.0:0.5;"
                 " float ref=float(t)/16.0+off; float u=(float(t)+0.5)/16.0;"
                 " data[8u+i]=floatBitsToUint(texture(tex, vec3(u, 0.5, ref))); } }\n")
    # depth compare, linear: x = 4.5 + k/16 for k = 0..15 (between texels 4 and 5), ref sweeps 4/16 .. 6/16 in 8 steps
    for fn in ('lequal', 'greater'):
        out[f'shadow_linear_{fn}'] = dict(fmt='d32f', w=16, h=1, data=F32(DEPTH), count=128, filt='linear', compare=fn,
            glsl=HEAD + "layout(binding=0) uniform highp sampler2DShadow tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x;"
                 " if(i<count){ float x=4.5+float(i%16u)/16.0; float ref=4.0/16.0+float(i/16u)/32.0;"
                 " data[8u+i]=floatBitsToUint(texture(tex, vec3(x/16.0, 0.5, ref))); } }\n")
    # mip chain: 64x64 r32f, level k = k everywhere (7 levels)
    mip = []
    for k in range(7):
        s = 64 >> k
        mip += [float(k)] * (s * s)
    # textureGrad, isotropic: g = 2^(e/16) / 64 for e = -32..127 (lod -2..~8), dPdx = (g, 0), dPdy = (0, g)
    out['grad_iso'] = dict(fmt='r32f', w=64, h=64, levels=7, data=F32(mip), count=160, filt='trilinear',
        glsl=HEAD + "layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x;"
             " if(i<count){ float g=exp2((float(i)-32.0)/16.0)/64.0;"
             " data[8u+i]=floatBitsToUint(textureGrad(tex, vec2(0.5), vec2(g,0.0), vec2(0.0,g)).r); } }\n")
    # textureGrad, anisotropic: dPdx = (gx, 0), dPdy = (0, gy) with gx = 2^(a/4)/64, gy = 2^(b/4)/64, a, b = 0..15
    out['grad_aniso'] = dict(fmt='r32f', w=64, h=64, levels=7, data=F32(mip), count=256, filt='trilinear',
        glsl=HEAD + "layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x;"
             " if(i<count){ float gx=exp2(float(i%16u)/4.0)/64.0, gy=exp2(float(i/16u)/4.0)/64.0;"
             " data[8u+i]=floatBitsToUint(textureGrad(tex, vec2(0.5), vec2(gx,0.0), vec2(0.0,gy)).r); } }\n")
    # textureGrad, diagonal gradient: dPdx = (g, g), dPdy = (-g, g): lod uses the length or the max component?
    out['grad_diag'] = dict(fmt='r32f', w=64, h=64, levels=7, data=F32(mip), count=96, filt='trilinear',
        glsl=HEAD + "layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x;"
             " if(i<count){ float g=exp2(float(i)/16.0)/64.0;"
             " data[8u+i]=floatBitsToUint(textureGrad(tex, vec2(0.5), vec2(g,g), vec2(-g,g)).r); } }\n")
    # LOD clamps: textureLod with lod = -1 + i/16 (i = 0..143), MIN_LOD 1.5, MAX_LOD 3.25; trilinear and nearest_mipmap
    for filt in ('trilinear', 'nearest_mipmap'):
        out[f'lod_clamp_{filt}'] = dict(fmt='r32f', w=64, h=64, levels=7, data=F32(mip), count=144, filt=filt, minlod=1.5, maxlod=3.25,
            glsl=HEAD + "layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x;"
                 " if(i<count){ data[8u+i]=floatBitsToUint(textureLod(tex, vec2(0.5), -1.0+float(i)/16.0).r); } }\n")
    # image stores: lane i stores to texel (i % 64, i / 64) and reads it back
    def store(name, fmt, qual, img, val, read, n, w=64):
        samp = {'image2D': 'sampler2D', 'uimage2D': 'usampler2D', 'iimage2D': 'isampler2D'}[img]
        out[name] = dict(fmt=fmt, w=w, h=(n + w - 1) // w, data=bytes({'rgba8': 4, 'rgba8snorm': 4, 'rgba8ui': 4, 'rgba8i': 4,
                         'rgba16ui': 8, 'rgba16i': 8}[fmt] * w * ((n + w - 1) // w)), count=n, filt='nearest', image=True,
            glsl=HEAD + f"layout({qual}, binding=0) writeonly uniform highp {img} img;\n"
                 f"layout(binding=0) uniform highp {samp} tex;\nvoid main(){{ uint i=gl_GlobalInvocationID.x;"
                 f" if(i<count){{ ivec2 p=ivec2(int(i%{w}u), int(i/{w}u)); imageStore(img, p, {val});"
                 f" memoryBarrierImage(); memoryBarrier(); data[8u+i]={read}; }} }}\n")
    # float -> unorm8: v = -0.25 + i/2048 (i = 0..3071: -0.25 .. 1.25 in 1/2048 steps)
    store('store_unorm8', 'rgba8', 'rgba8', 'image2D', 'vec4(-0.25+float(i)/2048.0, 0.0, 0.0, 1.0)',
          'uint(round(texelFetch(tex, p, 0).r*255.0))', 3072)
    # float -> snorm8: v = -1.25 + i/1024 (i = 0..2559)
    store('store_snorm8', 'rgba8snorm', 'rgba8_snorm', 'image2D', 'vec4(-1.25+float(i)/1024.0, 0.0, 0.0, 1.0)',
          'uint(int(round(texelFetch(tex, p, 0).r*127.0)))', 2560)
    # integers out of range
    store('store_u8', 'rgba8ui', 'rgba8ui', 'uimage2D', 'uvec4(i*7u, 0u, 0u, 0u)', 'texelFetch(tex, p, 0).r', 1024)
    store('store_i8', 'rgba8i', 'rgba8i', 'iimage2D', 'ivec4(int(i)-512, 0, 0, 0)', 'uint(texelFetch(tex, p, 0).r)', 1024)
    store('store_u16', 'rgba16ui', 'rgba16ui', 'uimage2D', 'uvec4(i*97u, 0u, 0u, 0u)', 'texelFetch(tex, p, 0).r', 1024)
    store('store_i16', 'rgba16i', 'rgba16i', 'iimage2D', 'ivec4((int(i)-512)*97, 0, 0, 0)', 'uint(texelFetch(tex, p, 0).r)', 1024)
    return out

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/gles-b29'))
    p.add_argument('--only')
    a = p.parse_args()
    run_cases(cases(), a.out, a.only)

if __name__ == '__main__':
    sys.exit(main())
