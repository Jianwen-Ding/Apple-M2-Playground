#!/usr/bin/env python3
"""Stack / scratch encodings from Mesa-compiled GLSL (safe-gap: stack through Mesa only). Runs each shader through Mesa's GLES driver on
the GPU (Mesa sets up scratch and the helper program itself, nothing is hand-built), checks every output against a host model, and
captures the AGX binary from Mesa's shader cache (scripts/agx_capture.py) to list the stack instructions.

Shaders (tests/gles_compute.c with GLES_SHADER_FILE; 32-lane workgroups, `data[8u + i]` outputs):
  spill   192 dependent uint values kept live to the end (register spills, no arrays)
  priv_u  1,024-entry dynamically indexed uint array (the earlier finding's shader)
  priv_v4 64-entry dynamically indexed uvec4 array
  priv_f  512-entry dynamically indexed float array
  priv_h  512-entry dynamically indexed mediump float array (fp16 if Mesa lowers it)
  run_gles_stack2.py [--out DIR] [--count 64]
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INC = Path('/save/workspace/AGX_Probe/mesa/include')
M = 0xffffffff
HEAD = "#version 320 es\nprecision highp int;\nprecision highp float;\nlayout(local_size_x=32, local_size_y=1, local_size_z=1) in;\nlayout(std430, binding=0) buffer Output { uint data[]; };\nuniform uint count;\n"
TAIL = "void main() { uint i=gl_GlobalInvocationID.x; if (i < count) data[8u+i]=pick(i); }\n"


def f2u(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


NV = 192


def spill_src():
    L = ["uint pick(uint i) {", "  uint a0 = i * 2654435761u + 12345u;"]
    for k in range(1, NV):
        L.append(f"  uint a{k} = (a{k-1} ^ (a{k-1} >> {1+k%13}u)) * {1664525+2*k}u + {1013904223+k}u + i;")
    L.append(f"  uint r = a{NV-1};")
    for k in range(NV-2, -1, -1):
        L.append(f"  r = (r ^ a{k}) * 16777619u;")
    L += ["  return r;", "}"]
    return "\n".join(L)+"\n"


def spill_model(i):
    a = [(i*2654435761+12345) & M]
    for k in range(1, NV):
        p = a[-1]
        a.append(((p ^ (p >> (1+k % 13)))*(1664525+2*k) + (1013904223+k) + i) & M)
    r = a[-1]
    for k in range(NV-2, -1, -1):
        r = ((r ^ a[k])*16777619) & M
    return r


SHADERS = {
    'spill': (HEAD+spill_src()+TAIL, spill_model),
    'priv_u': (HEAD+"uint pick(uint i) { uint a[1024]; for (uint k=0u; k<1024u; k++) a[k] = (i*k) ^ (0x1234u*k); return a[(i*7u)&1023u] + a[(i*13u+5u)&1023u]; }\n"+TAIL,
               lambda i: (((i*((i*7) & 1023)) ^ (0x1234*((i*7) & 1023))) + ((i*((i*13+5) & 1023)) ^ (0x1234*((i*13+5) & 1023)))) & M),
    'priv_v4': (HEAD+"uint pick(uint i) { uvec4 a[64]; for (uint k=0u; k<64u; k++) a[k] = uvec4(i*k, i^k, i+k*3u, i*5u+k); uvec4 r = a[(i*7u)&63u] + a[(i*13u+5u)&63u]; return r.x ^ r.y ^ r.z ^ r.w; }\n"+TAIL,
                lambda i: (lambda ka, kb: ((((i*ka) + (i*kb)) ^ ((i ^ ka) + (i ^ kb)) ^ ((i+ka*3) + (i+kb*3)) ^ ((i*5+ka) + (i*5+kb))) & M))((i*7) & 63, (i*13+5) & 63)),
    'priv_f': (HEAD+"uint pick(uint i) { float a[512]; for (uint k=0u; k<512u; k++) a[k] = float((i*k)&255u) * 0.5; return floatBitsToUint(a[(i*7u)&511u] + a[(i*13u+5u)&511u]); }\n"+TAIL,
               lambda i: f2u(((i*((i*7) & 511)) & 255)*0.5 + ((i*((i*13+5) & 511)) & 255)*0.5)),
    'priv_h': (HEAD+"uint pick(uint i) { mediump float a[512]; for (uint k=0u; k<512u; k++) a[k] = float((i*k)&255u) * 0.5; return floatBitsToUint(float(a[(i*7u)&511u] + a[(i*13u+5u)&511u])); }\n"+TAIL,
               lambda i: f2u(((i*((i*7) & 511)) & 255)*0.5 + ((i*((i*13+5) & 511)) & 255)*0.5)),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/gles-stack2'))
    p.add_argument('--count', type=int, default=64)
    p.add_argument('--only')
    a = p.parse_args()
    out = a.out; out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', f'-I{INC}', str(REPO/'tests/gles_compute.c'), '-o', str(out/'gles_compute'), '-ldl'], check=True)
    rec = {'count': a.count, 'shaders': {}}
    for name, (src, model) in SHADERS.items():
        if a.only and name != a.only:
            continue
        d = out/name; subprocess.run(['rm', '-rf', str(d)], check=True); d.mkdir()
        (d/'shader.glsl').write_text(src)
        cache = d/'cache'; cache.mkdir()
        env = {'PATH': '/usr/bin', 'GLES_SHADER_FILE': str(d/'shader.glsl'), 'MESA_SHADER_CACHE_DIR': str(cache), 'MESA_SHADER_CACHE_DISABLE': 'false'}
        r = subprocess.run([str(out/'gles_compute'), 'index', str(a.count), '/dev/dri/renderD128'], cwd=d, capture_output=True, timeout=120, env=env)
        (d/'stdout.txt').write_bytes(r.stdout)
        ok = r.returncode == 0 and (d/'output.bin').exists()
        res = {'run_ok': ok}
        if ok:
            w = struct.unpack(f'<{a.count//32*32+16 if a.count%32==0 else (a.count+31)//32*32+16}I', (d/'output.bin').read_bytes())
            got = list(w[8:8+a.count])
            want = [model(i) for i in range(a.count)]
            res['outputs_exact'] = got == want
            res['wrong'] = sum(x != y for x, y in zip(got, want))
            res['guards_intact'] = all(x == 0xcdcdcdcd for x in w[:8])
        else:
            res['stderr'] = r.stderr.decode()[-300:]
        rec['shaders'][name] = res
        print(name, res, flush=True)
    (out/'record.json').write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    sys.exit(main())
