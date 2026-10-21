#!/usr/bin/env python3
"""B29 probes 4 and 9 through Mesa's Vulkan driver (tests/vulkan_texture.c; Mesa builds every descriptor):
  unnorm_*   unnormalized (pixel) coordinates with clamp-to-edge / clamp-to-border, nearest / linear: 16x1 r32f texture
             holding 100 + i, x = -3 + k/4 (k = 0..87), y = 0.5
  pitch_*    a 33x8 r32f texture (132-byte rows) in a linear layout: Mesa's own pitch (VK_IMAGE_TILING_LINEAR), then the
             LINEAR DRM modifier with explicit row pitches 132, 136, 144, 160, 192, 256 bytes. Row padding is 0xcdcdcdcd.
             fetch: texelFetch of every texel; bilin: textureLod at 264 points straddling texel and row boundaries.
  run_vk_b29.py [--out DIR]; prints a summary per case and writes DIR/record.json"""
import argparse, json, os, struct, subprocess, sys
from pathlib import Path
EXE = '/scratch/agxsim-runs/vkt'
GLSLANG = '/scratch/agxsim-deps/root/usr/bin/glslangValidator'
HEAD = ("#version 450\nlayout(local_size_x=32) in;\nlayout(std430, binding=0) buffer O { uint d[]; };\n"
        "layout(binding=1) uniform sampler2D tex;\n")
UNNORM = HEAD + "void main(){ uint i=gl_GlobalInvocationID.x; if(i<88u){ float x=-3.0+float(i)/4.0;" \
                " d[i]=floatBitsToUint(textureLod(tex, vec2(x, 0.5), 0.0).r); } }\n"
FETCH = HEAD + "void main(){ uint i=gl_GlobalInvocationID.x; if(i<264u){ d[i]=floatBitsToUint(texelFetch(tex, ivec2(int(i%33u), int(i/33u)), 0).r); } }\n"
BILIN = HEAD + "void main(){ uint i=gl_GlobalInvocationID.x; if(i<264u){ float x=(float(i%33u)+0.25)/33.0, y=(float(i/33u)+0.75)/8.0;" \
               " d[i]=floatBitsToUint(textureLod(tex, vec2(x, y), 0.0).r); } }\n"

def run(out, name, glsl, w, h, data, count, env):
    d = out / name; d.mkdir(parents=True, exist_ok=True)
    (d / 's.comp').write_text(glsl)
    r = subprocess.run([GLSLANG, '-V', '--target-env', 'vulkan1.3', str(d / 's.comp'), '-o', str(d / 's.spv')], capture_output=True, text=True)
    if r.returncode: sys.exit('glslang: ' + r.stdout[-400:])
    (d / 'tex.bin').write_bytes(struct.pack(f'<{len(data)}f', *data))
    e = dict(os.environ, VKT_W=str(w), VKT_H=str(h), VKT_DATA=str(d / 'tex.bin'), VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/asahi_icd.aarch64.json', **env)
    r = subprocess.run([EXE, str(d / 's.spv'), str(d / 'out.bin'), str(count)], capture_output=True, text=True, timeout=60, env=e)
    lines = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
    info = {k: v for l in lines for k, v in l.items()}
    words = list(struct.unpack(f'<{count}I', (d / 'out.bin').read_bytes())) if (d / 'out.bin').exists() and r.returncode == 0 else None
    return info, words, r.returncode

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/vk-b29'))
    a = p.parse_args()
    rec = {}
    tex16 = [100.0 + i for i in range(16)]
    for addr in ('clamp', 'border'):
        for filt in ('nearest', 'linear'):
            name = f'unnorm_{addr}_{filt}'
            info, words, rc = run(a.out, name, UNNORM, 16, 1, tex16, 88, dict(VKT_UNNORM='1', VKT_ADDR=addr, VKT_FILTER=filt))
            rec[name] = dict(info=info, rc=rc, out=[struct.unpack('<f', struct.pack('<I', x))[0] for x in words] if words else None)
            print(name, rc, info.get('error'), (rec[name]['out'] or [])[:6], '...', (rec[name]['out'] or [])[-6:], flush=True)
    tex = [1000.0 * y + x for y in range(8) for x in range(33)]
    for pitch in (0, 132, 136, 144, 160, 192, 256):
        for kind, glsl, filt in (('fetch', FETCH, 'nearest'), ('bilin', BILIN, 'linear')):
            name = f'pitch{pitch}_{kind}'
            info, words, rc = run(a.out, name, glsl, 33, 8, tex, 264, dict(VKT_PITCH=str(pitch), VKT_FILTER=filt))
            vals = [struct.unpack('<f', struct.pack('<I', x))[0] for x in words] if words else None
            rec[name] = dict(info=info, rc=rc, out=vals)
            if vals and kind == 'fetch':
                wrong = sum(vals[i] != tex[i] for i in range(264))
            elif vals:
                # bilinear at (x + 0.25, y + 0.75) texel units from texel centres: weights 0.75 / 0.25 in x... computed on the host
                def at(px, py):
                    px, py = px - 0.5, py - 0.5
                    x0, y0 = int(px // 1), int(py // 1); fx, fy = px - x0, py - y0
                    g = lambda x, y: tex[min(max(y, 0), 7) * 33 + min(max(x, 0), 32)]
                    wq = lambda f: round(f * 256) / 256
                    fx, fy = wq(fx), wq(fy)
                    return (g(x0, y0) * (1 - fx) + g(x0 + 1, y0) * fx) * (1 - fy) + (g(x0, y0 + 1) * (1 - fx) + g(x0 + 1, y0 + 1) * fx) * fy
                wrong = sum(abs(vals[i] - at(i % 33 + 0.25, i // 33 + 0.75)) > 1e-3 * max(1, abs(vals[i])) for i in range(264))
            else:
                wrong = None
            rec[name]['wrong'] = wrong
            print(name, 'rc', rc, 'pitch', info.get('row_pitch'), 'rejected' if info.get('image_rejected') else '', info.get('error', ''), 'wrong', wrong, flush=True)
    (a.out / 'record.json').write_text(json.dumps(rec) + '\n')

if __name__ == '__main__':
    main()
