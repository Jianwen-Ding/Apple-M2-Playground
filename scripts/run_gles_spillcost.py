#!/usr/bin/env python3
"""Cost of register spills, measured through Mesa's GLES driver (safe-02 spill item). A dependent chain keeps NV values live to the end
(as run_gles_stack2.spill); NV is swept. Per NV: Mesa's spill / fill counts from the captured listing, and the host-side fence time of a
262,144-lane dispatch (5 runs, median). The time includes driver overhead, so only differences between NV are meaningful.
  run_gles_spillcost.py [--out DIR]
"""
import argparse, json, re, statistics, struct, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_gles_stack2 as S

REPO = Path(__file__).resolve().parents[1]
INC = Path('/save/workspace/AGX_Probe/mesa/include')
M = 0xffffffff


def src(nv):
    L = ["uint pick(uint i) {", "  uint a0 = i * 2654435761u + 12345u;"]
    for k in range(1, nv):
        L.append(f"  uint a{k} = (a{k-1} ^ (a{k-1} >> {1+k%13}u)) * {1664525+2*k}u + {1013904223+k}u + i;")
    L.append(f"  uint r = a{nv-1};")
    for k in range(nv-2, -1, -1):
        L.append(f"  r = (r ^ a{k}) * 16777619u;")
    L += ["  return r;", "}"]
    return "\n".join(L)+"\n"


def model(nv, i):
    a = [(i*2654435761+12345) & M]
    for k in range(1, nv):
        p = a[-1]
        a.append(((p ^ (p >> (1+k % 13)))*(1664525+2*k) + (1013904223+k) + i) & M)
    r = a[-1]
    for k in range(nv-2, -1, -1):
        r = ((r ^ a[k])*16777619) & M
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('/scratch/apple-m2-playground/gles-spillcost'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    out = a.out; out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cc', '-std=c11', '-O2', f'-I{INC}', str(REPO/'tests/gles_compute.c'), '-o', str(out/'gles_compute'), '-ldl'], check=True)
    count = 262144
    res = []
    for nv in (16, 32, 48, 64, 96, 128, 192, 256, 384):
        d = out/f'nv{nv}'; subprocess.run(['rm', '-rf', str(d)], check=True); d.mkdir(); (d/'cache').mkdir()
        (d/'shader.glsl').write_text(S.HEAD+src(nv)+S.TAIL)
        env = {'PATH': '/usr/bin', 'GLES_SHADER_FILE': str(d/'shader.glsl'), 'MESA_SHADER_CACHE_DIR': str(d/'cache'), 'MESA_SHADER_CACHE_DISABLE': 'false'}
        times, ok = [], None
        for rep in range(5):
            r = subprocess.run([str(out/'gles_compute'), 'index', str(count), '/dev/dri/renderD128'], cwd=d, capture_output=True, timeout=300, env=env)
            if r.returncode:
                ok = False; break
            t = [float(x) for x in re.findall(r'fence_wait=\d+ status=0x\w+ elapsed_s=([0-9.]+)', r.stdout.decode())]
            times.append(t[-1])
            if rep == 0:
                w = struct.unpack(f'<{8+count+8}I', (d/'output.bin').read_bytes())
                ok = all(w[8+i] == model(nv, i) for i in range(0, count, 997)) and all(x == 0xcdcdcdcd for x in w[:8])
        subprocess.run([sys.executable, '-B', str(REPO/'scripts/agx_capture.py'), '--cache', str(d/'cache'), '--out', str(d/'cap'), '--quiet'], capture_output=True)
        lst = (d/'cap/listing.txt').read_text() if (d/'cap/listing.txt').exists() else ''
        st = re.findall(r'instrs (\d+).*?spills (\d+)\s+fills (\d+)', lst)
        r = {'nv': nv, 'ok': ok, 'fence_s': times, 'mesa_stats': st[:1]}
        res.append(r); print(json.dumps(r), flush=True)
    if a.result:
        a.result.write_text(json.dumps(res)+'\n')


if __name__ == '__main__':
    main()
