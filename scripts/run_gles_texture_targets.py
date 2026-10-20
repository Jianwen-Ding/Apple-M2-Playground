#!/usr/bin/env python3
"""Texture targets beyond 2D through Mesa's GLES driver (safe-05 remainder): 3D, 2D array, cube and buffer
textures, plus float-format filtering. Mesa builds every texture, sampler and image state word; nothing is
hand-encoded. Same harness and record layout as run_gles_texture.py (GLES_TEX_TARGET / GLES_TEX_D select the target).
  run_gles_texture_targets.py [--out DIR] [--only NAME]
CUDA relevance: tex3D, tex2DLayered, texCubemap, tex1Dfetch (texture buffer over linear memory), float linear filtering.
"""
import argparse, random, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gles_texture import run_cases  # noqa: E402

HEAD = ("#version 320 es\nprecision highp int;\nprecision highp float;\n"
        "precision highp sampler3D;\nprecision highp usampler3D;\nprecision highp sampler2DArray;\nprecision highp usampler2DArray;\n"
        "precision highp samplerCube;\nprecision highp usamplerCube;\nprecision highp samplerBuffer;\nprecision highp usamplerBuffer;\n"
        "precision highp sampler2D;\nprecision highp image3D;\nprecision highp image2DArray;\n"
        "layout(local_size_x=32, local_size_y=1, local_size_z=1) in;\nlayout(std430, binding=0) buffer Output { uint data[]; };\nuniform uint count;\n")
U32 = lambda vals: b''.join(struct.pack('<I', v) for v in vals)
F32 = lambda vals: b''.join(struct.pack('<f', v) for v in vals)
F16 = lambda vals: b''.join(struct.pack('<e', v) for v in vals)


def cases():
    rng = random.Random(11)
    out = {}
    # 1. 3D texelFetch: every texel of an 8x8x8 r32ui volume, then 64 out-of-range lanes (each axis -2..+9)
    v3 = [rng.getrandbits(32) for _ in range(512)]
    out['fetch3d_r32ui'] = dict(target='3d', fmt='r32ui', w=8, h=8, d=8, data=U32(v3), count=512+96, filt='nearest', vals=v3,
        glsl=HEAD+"layout(binding=0) uniform highp usampler3D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec3 p;"
             " if(i<512u) p=ivec3(int(i%8u),int((i/8u)%8u),int(i/64u)); else { int k=int(i-512u); int a=k/32; int t=k%32-12;"
             " p = a==0 ? ivec3(t,3,4) : a==1 ? ivec3(3,t,4) : ivec3(3,4,t); }"
             " data[8u+i]=texelFetch(tex, p, 0).r; } }\n")
    # 2. 3D trilinear within one level: r8 8x8x8 random, 3 axes swept with 64 fractions each plus 256 random points
    v3b = [rng.randrange(256) for _ in range(512)]
    pts = [(rng.uniform(0.5, 7.5), rng.uniform(0.5, 7.5), rng.uniform(0.5, 7.5)) for _ in range(256)]
    sweep = []
    for ax in range(3):
        for k in range(64):
            c = [3.5+0.375, 4.5+0.125, 2.5+0.625]; c[ax] = 2.5 + k/64; sweep.append(tuple(c))
    allp = sweep + pts
    out['linear3d_r8'] = dict(target='3d', fmt='r8', w=8, h=8, d=8, data=bytes(v3b), count=len(allp), filt='linear', vals=v3b, pts=allp,
        glsl=HEAD+"layout(binding=0) uniform highp sampler3D tex;\nconst vec3 P[%d] = vec3[](%s);\n" % (len(allp), ",".join(f"vec3({x!r},{y!r},{z!r})" for x, y, z in allp)) +
             "void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ data[8u+i]=floatBitsToUint(textureLod(tex, P[i]/8.0, 0.0).r); } }\n")
    # 3. 3D wrap in the R axis (repeat and mirror) with nearest sampling, z from -12..19
    for wrap in ('repeat', 'mirror', 'clamp'):
        out[f'wrap3d_{wrap}'] = dict(target='3d', fmt='r32ui', w=8, h=8, d=8, data=U32(v3), count=32, filt='nearest', wrap=wrap, vals=v3,
            glsl=HEAD+"layout(binding=0) uniform highp usampler3D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
                 " float z=float(int(i)-12); data[8u+i]=textureLod(tex, vec3(2.5, 5.5, z+0.5)/8.0, 0.0).r; } }\n")
    # 4. 3D mipmaps: 8x8x8 L0 random, L1 4x4x4 = 100, L2 2x2x2 = 150, L3 1x1x1 = 200 (depth halves too)
    mip3 = bytes(v3b) + bytes([100])*64 + bytes([150])*8 + bytes([200])
    lods = [-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
    out['lod3d_trilinear'] = dict(target='3d', fmt='r8', w=8, h=8, d=8, data=mip3, levels=4, count=len(lods), filt='trilinear', vals=v3b,
        glsl=HEAD+"layout(binding=0) uniform highp sampler3D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float lod=float[](%s)[i];"
             " data[8u+i]=floatBitsToUint(textureLod(tex, vec3(4.0,4.0,4.0)/8.0, lod).r); } }\n" % ",".join(f"{v:.2f}" for v in lods))
    # 5. 2D array: texelFetch all texels of 8x8x6, then layers -2..9 at a fixed texel (OOB layers)
    va = [rng.getrandbits(32) for _ in range(384)]
    out['fetcharray_r32ui'] = dict(target='2darray', fmt='r32ui', w=8, h=8, d=6, data=U32(va), count=384+12, filt='nearest', vals=va,
        glsl=HEAD+"layout(binding=0) uniform highp usampler2DArray tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec3 p;"
             " if(i<384u) p=ivec3(int(i%8u),int((i/8u)%8u),int(i/64u)); else p=ivec3(3,5,int(i-384u)-2);"
             " data[8u+i]=texelFetch(tex, p, 0).r; } }\n")
    # 6. 2D array layer selection with a float layer coordinate: layer = -2.0 .. 8.0 in steps of 1/16 (nearest)
    layers = [-2.0 + k/16 for k in range(161)]
    out['layerselect_r32ui'] = dict(target='2darray', fmt='r32ui', w=8, h=8, d=6, data=U32(va), count=len(layers), filt='nearest', vals=va, layers=layers,
        glsl=HEAD+"layout(binding=0) uniform highp usampler2DArray tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " float l=-2.0+float(i)/16.0; data[8u+i]=textureLod(tex, vec3(3.5/8.0, 5.5/8.0, l), 0.0).r; } }\n")
    # 7. linear filtering on an array never blends layers: r8, fractional layer and fractional xy
    vab = [rng.randrange(256) for _ in range(384)]
    out['lineararray_r8'] = dict(target='2darray', fmt='r8', w=8, h=8, d=6, data=bytes(vab), count=256, filt='linear', vals=vab,
        glsl=HEAD+"layout(binding=0) uniform highp sampler2DArray tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " float fx=float(i%64u)/64.0; float l=float(i/64u)*1.3+0.2; data[8u+i]=floatBitsToUint(textureLod(tex, vec3((2.5+fx)/8.0, (4.5+0.25)/8.0, l), 0.0).r); } }\n")
    # 8. cube map face selection and face coordinates: 4x4 r32ui per face, each texel unique; nearest; random and
    # axis-tie directions. Output: the texel value (decoded offline to face, s, t).
    cube = [(f << 8) | (t << 4) | s | 0x5a000000 for f in range(6) for t in range(4) for s in range(4)]
    dirs = []
    for _ in range(192):
        dirs.append(tuple(rng.uniform(-1, 1) for _ in range(3)))
    for a in (1.0, -1.0):
        for b in (1.0, -1.0):
            dirs += [(a, b, 0.25), (a, 0.25, b), (0.25, a, b), (a, b, b)]
    dirs += [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    out['cube_r32ui'] = dict(target='cube', fmt='r32ui', w=4, h=4, data=U32(cube), count=len(dirs), filt='nearest', vals=cube, dirs=dirs,
        glsl=HEAD+"layout(binding=0) uniform highp usamplerCube tex;\nconst vec3 D[%d] = vec3[](%s);\n" % (len(dirs), ",".join(f"vec3({float(x)!r},{float(y)!r},{float(z)!r})" for x, y, z in dirs)) +
             "void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ data[8u+i]=textureLod(tex, D[i], 0.0).r; } }\n")
    # 9. texture buffer (tex1Dfetch): r32ui 1000 texels; indices -40..1063 cover OOB on both sides and the tail
    vb = [rng.getrandbits(32) for _ in range(1000)]
    out['buffer_r32ui'] = dict(target='buffer', fmt='r32ui', w=1000, h=1, data=U32(vb), count=1104, filt='nearest', vals=vb,
        glsl=HEAD+"layout(binding=0) uniform highp usamplerBuffer tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " data[8u+i]=texelFetch(tex, int(i)-40).r; } }\n")
    # 10. texture buffer with a normalized format: r8 -> float (every byte value), plus 32 OOB lanes
    out['buffer_r8'] = dict(target='buffer', fmt='r8', w=256, h=1, data=bytes(range(256)), count=288, filt='nearest',
        glsl=HEAD+"layout(binding=0) uniform highp samplerBuffer tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " data[8u+i]=floatBitsToUint(texelFetch(tex, int(i)).r); } }\n")
    # 11. buffer rgba32f: the .w of an OOB fetch (is it 0 or 1?) and in-range exactness incl. NaN payloads
    vf = [0x7fc12345, 0xffbfffff, 0x00000001, 0x80000000] + [rng.getrandbits(32) for _ in range(4*63)]
    out['buffer_rgba32f'] = dict(target='buffer', fmt='rgba32f', w=64, h=1, data=U32(vf), count=4*72, filt='nearest', vals=vf,
        glsl=HEAD+"layout(binding=0) uniform highp samplerBuffer tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " vec4 v=texelFetch(tex, int(i/4u)); data[8u+i]=floatBitsToUint(v[i%4u]); } }\n")
    # 12. 2D texelFetch OOB alpha for rgba formats (CUDA border reads: is OOB alpha 0 or 1?) via r8 / rgba8 sampler
    out['oob_rgba8_alpha'] = dict(fmt='rgba8', w=4, h=4, data=bytes([200, 100, 50, 25]*16), count=8, filt='nearest',
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " vec4 v=texelFetch(tex, ivec2(i<4u ? 1 : 9, 1), 0); data[8u+i]=floatBitsToUint(v[i%4u]); } }\n")
    out['oob_r8_gba'] = dict(fmt='r8', w=4, h=4, data=bytes([200]*16), count=8, filt='nearest',
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " vec4 v=texelFetch(tex, ivec2(i<4u ? 1 : 9, 1), 0); data[8u+i]=floatBitsToUint(v[i%4u]); } }\n")
    # 13. float-format bilinear: r16f and r32f, 256 x fractions x 15 cells (does float filtering round to 12 bits?)
    hv = [rng.uniform(-4, 4) for _ in range(256)]
    hv16 = [struct.unpack('<e', struct.pack('<e', v))[0] for v in hv]
    out['bilinear_r16f'] = dict(fmt='r16f', w=16, h=16, data=F16(hv16), count=256*15, filt='linear', vals=hv16,
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float fx=float(i%256u)/256.0; float cx=float(i/256u);"
             " vec2 uv=(vec2(cx+0.5+fx, 3.5+0.375))/16.0; data[8u+i]=floatBitsToUint(textureLod(tex, uv, 0.0).r); } }\n")
    fv = [rng.uniform(-4, 4) for _ in range(256)]
    fv32 = [struct.unpack('<f', struct.pack('<f', v))[0] for v in fv]
    out['bilinear_r32f'] = dict(fmt='r32f', w=16, h=16, data=F32(fv32), count=256*15, filt='linear', vals=fv32,
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float fx=float(i%256u)/256.0; float cx=float(i/256u);"
             " vec2 uv=(vec2(cx+0.5+fx, 3.5+0.375))/16.0; data[8u+i]=floatBitsToUint(textureLod(tex, uv, 0.0).r); } }\n")
    # 14. 3D image store/load round trip (surf3Dwrite / surf3Dread) and 2D-array image layers
    out['image3d_r32ui'] = dict(target='3d', fmt='r32ui', w=8, h=8, d=8, data=bytes(4*512), count=512, filt='nearest', image=True,
        glsl=HEAD.replace("precision highp image3D;", "precision highp uimage3D;") +
             "layout(r32ui, binding=0) uniform highp uimage3D img;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec3 p=ivec3(int(i%8u),int((i/8u)%8u),int(i/64u));"
             " imageStore(img, p, uvec4(i*2654435761u)); memoryBarrierImage(); data[8u+i]=imageLoad(img, p).r; } }\n")
    out['imagearray_r32ui'] = dict(target='2darray', fmt='r32ui', w=8, h=8, d=6, data=bytes(4*384), count=384, filt='nearest', image=True,
        glsl=HEAD.replace("precision highp image2DArray;", "precision highp uimage2DArray;") +
             "layout(r32ui, binding=0) uniform highp uimage2DArray img;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec3 p=ivec3(int(i%8u),int((i/8u)%8u),int(i/64u));"
             " imageStore(img, p, uvec4(i*2246822519u+7u)); memoryBarrierImage(); data[8u+i]=imageLoad(img, p).r; } }\n")
    # 15. direct weight readout on r32f (output = filter weight): texel x=5 is 1.0, all others 0; sample x = 4.5 + k/4096
    # at a texel-centre row (fy = 0) so the result is the hardware x weight for fraction k/4096
    wt = [0.0]*256
    for y in range(16):
        wt[y*16+5] = 1.0
    out['weight_sweep_r32f'] = dict(fmt='r32f', w=16, h=16, data=F32(wt), count=4096+64, filt='linear',
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " float x = i < 4096u ? 4.5+float(i)/4096.0 : 4.5+float(i-4096u)/64.0 + 1.0/8192.0;"
             " data[8u+i]=floatBitsToUint(textureLod(tex, vec2(x, 7.5)/16.0, 0.0).r); } }\n")
    # 16. 3D: same readout along z (texel z=5 is 1.0) to confirm the third axis uses the same weight function
    w3 = [1.0 if z == 5 else 0.0 for z in range(8) for _ in range(64)]
    out['weight_sweep3d_r32f'] = dict(target='3d', fmt='r32f', w=8, h=8, d=8, data=F32(w3), count=1024, filt='linear',
        glsl=HEAD+"layout(binding=0) uniform highp sampler3D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " float z = 4.5+float(i)/1024.0; data[8u+i]=floatBitsToUint(textureLod(tex, vec3(3.5, 3.5, z)/8.0, 0.0).r); } }\n")
    # 17. mip level weight readout on r32f: L0 = 0, L1 = 1, L2.. = 1 (trilinear), lod = k/4096 in [0, 1)
    mipf = [0.0]*256 + [1.0]*64 + [1.0]*16 + [1.0]*4 + [1.0]
    out['lod_weight_r32f'] = dict(fmt='r32f', w=16, h=16, data=F32(mipf), levels=5, count=4096, filt='trilinear',
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " data[8u+i]=floatBitsToUint(textureLod(tex, vec2(8.0, 8.0)/16.0, float(i)/4096.0).r); } }\n")
    # 18. 2D trilinear off the 12-bit grid (r8): L0 random, L1 solid 101; lod = k/64 at a texel centre (single
    # level-blend rounding), then at an off-centre point where the L0 bilinear itself is off-grid (one or two roundings?)
    v2 = [rng.randrange(256) for _ in range(256)]
    mip8 = bytes(v2) + bytes([101])*64 + bytes([101])*16 + bytes([101])*4 + bytes([101])
    out['lod_offgrid_r8'] = dict(fmt='r8', w=16, h=16, data=mip8, levels=5, count=128, filt='trilinear', vals=v2,
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " vec2 p = i < 64u ? vec2(6.5, 9.5) : vec2(6.5+0.3125, 9.5+0.6875); float lod = float(i%64u)/64.0;"
             " data[8u+i]=floatBitsToUint(textureLod(tex, p/16.0, lod).r); } }\n")
    # 19. 2D bilinear r8 at 1024 random points (non-dyadic fractions; the earlier 2D suite used k/256 only)
    v2r = [rng.randrange(256) for _ in range(256)]
    p2 = [(rng.uniform(0.5, 15.5), rng.uniform(0.5, 15.5)) for _ in range(1024)]
    out['bilinear_random_r8'] = dict(fmt='r8', w=16, h=16, data=bytes(v2r), count=len(p2), filt='linear', vals=v2r, pts=p2,
        glsl=HEAD+"layout(binding=0) uniform highp sampler2D tex;\nconst vec2 P[%d] = vec2[](%s);\n" % (len(p2), ",".join(f"vec2({x!r},{y!r})" for x, y in p2)) +
             "void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ data[8u+i]=floatBitsToUint(textureLod(tex, P[i]/16.0, 0.0).r); } }\n")
    # 20. wide buffer: 70000 r32ui texels (rows y = i >> 14 up to 4); sample lanes across the 16384 boundaries + OOB tail
    vw = [(k*2654435761 + 12345) & 0xffffffff for k in range(70000)]
    idx = [k for b in (0, 16384, 32768, 49152, 65536) for k in range(b-16, b+16) if k >= 0] + list(range(69984, 70016))
    out['buffer_wide_r32ui'] = dict(target='buffer', fmt='r32ui', w=70000, h=1, data=U32(vw), count=len(idx), filt='nearest', vals=vw, idx=idx,
        glsl=HEAD+"layout(binding=0) uniform highp usamplerBuffer tex;\nconst int I[%d] = int[](%s);\n" % (len(idx), ",".join(map(str, idx))) +
             "void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ data[8u+i]=texelFetch(tex, I[i]).r; } }\n")
    # 21. mipmapped 2D array: 8x8x4 levels 0..3; level l of layer L solid = 10 + 40*l + L; nearest_mipmap, explicit lod and layer
    ma = b''.join(bytes([10+40*l+L])*((8 >> l)**2) for l in range(4) for L in range(4))
    # layout per level: all layers of the level back to back (glTexSubImage3D per level)
    out['mip_array_r8'] = dict(target='2darray', fmt='r8', w=8, h=8, d=4, levels=4, data=ma, count=64, filt='nearest_mipmap',
        glsl=HEAD+"layout(binding=0) uniform highp sampler2DArray tex;\nvoid main(){ uint i=gl_GlobalInvocationID.x; if(i<count){"
             " float lod=float(i%16u)*0.25; float L=float(i/16u); data[8u+i]=uint(textureLod(tex, vec3(0.4, 0.6, L), lod).r*255.0+0.5); } }\n")
    # 22. linear cube filtering across a face edge: 4x4 faces, face f solid value 40*f+20 (r8); directions sweep across the +X/+Z edge
    cf = b''.join(bytes([40*f+20])*16 for f in range(6))
    dirs2 = [(1.0, 0.1, 1.0 - k/32) for k in range(33)] + [(1.0 - k/32, 0.1, 1.0) for k in range(1, 33)]
    out['cube_seam_r8'] = dict(target='cube', fmt='r8', w=4, h=4, data=cf, count=len(dirs2), filt='linear', dirs=dirs2,
        glsl=HEAD+"layout(binding=0) uniform highp samplerCube tex;\nconst vec3 D[%d] = vec3[](%s);\n" % (len(dirs2), ",".join(f"vec3({x!r},{y!r},{z!r})" for x, y, z in dirs2)) +
             "void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ data[8u+i]=floatBitsToUint(textureLod(tex, D[i], 0.0).r); } }\n")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/gles-texture-targets'))
    p.add_argument('--only')
    a = p.parse_args()
    run_cases(cases(), a.out, a.only)


if __name__ == '__main__':
    sys.exit(main())
