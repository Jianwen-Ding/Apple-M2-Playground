#!/usr/bin/env python3
"""Mesa-compiled stack (scratch) shader: run through Mesa's GLES driver, verify, extract binary.

Mesa sets up scratch itself (helper program + per-core block list), so this path is
safe. Steps: build tests/gles_compute.c, run mode `private` (1024-entry dynamically
indexed private array) with the shader cache pointed at a fresh directory, check
all outputs against the host model, carve the zstd frames out of the cache DB,
find Mesa's stack_adjust prologue (built from Mesa's agx_pack.c formula) and
disassemble the main shader with applegpu.
"""
import json, struct, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agx_loop

REPO = Path(__file__).resolve().parents[1]
INC = Path('/save/workspace/AGX_Probe/mesa/include')
out = Path(sys.argv[1] if len(sys.argv) > 1 else '/scratch/apple-m2-playground/gles-stack')
out.mkdir(parents=True, exist_ok=True)
subprocess.run(['cc', '-std=c11', '-O2', '-Wall', f'-I{INC}', str(REPO/'tests/gles_compute.c'), '-o', str(out/'gles_compute'), '-ldl'], check=True)
cache = out/'cache'
subprocess.run(['rm', '-rf', str(cache)], check=True); cache.mkdir()
# run 1: Mesa IR dump (AGX_MESA_DEBUG bypasses the shader cache); run 2: cache capture
d = subprocess.run([str(out/'gles_compute'), 'private', '64', '/dev/dri/renderD128'], cwd=out, capture_output=True, timeout=60,
                   env={'PATH': '/usr/bin', 'MESA_SHADER_CACHE_DISABLE': 'true', 'AGX_MESA_DEBUG': 'shaders'})
(out/'ir-dump.txt').write_bytes(d.stdout)
r = subprocess.run([str(out/'gles_compute'), 'private', '64', '/dev/dri/renderD128'], cwd=out, capture_output=True, timeout=60,
                   env={'PATH': '/usr/bin', 'MESA_SHADER_CACHE_DIR': str(cache), 'MESA_SHADER_CACHE_DISABLE': 'false'})
(out/'stdout.txt').write_bytes(r.stdout)
if r.returncode or d.returncode: sys.exit('GLES run failed')
w = struct.unpack(f'<{len((out/"output.bin").read_bytes())//4}I', (out/'output.bin').read_bytes())
def pick(i):
    a = [((i*k) ^ (0x1234*k)) & 0xffffffff for k in range(1024)]
    return (a[(i*7) & 1023]+a[(i*13+5) & 1023]) & 0xffffffff
exact = list(w[8:72]) == [pick(i) for i in range(64)]
air = [l.strip() for l in d.stdout.decode().splitlines() if 'stack_' in l]

ss = 1024 + 10; ss = (ss + 3) & ~3                       # Mesa: align(DIV_ROUND_UP(4096 B, 4) + 10, 4)
sa = (0x10100b5 | 1 << 26 | 2 << 36 | (ss & 0xf) << 20 | ((ss >> 4) & 0xf) << 32 | 1 << 47 | (ss >> 8) << 56).to_bytes(8, 'little')
main = None
for db in cache.rglob('mesa_cache.db'):
    b = db.read_bytes()
    pos = [i for i in range(len(b)) if b[i:i+4] == b'\x28\xb5\x2f\xfd']
    for s, e in zip(pos, pos[1:]+[len(b)]):
        for cut in range(e, s+8, -1):
            z = subprocess.run(['zstd', '-d', '-q', '-c'], input=b[s:cut], capture_output=True)
            if z.returncode == 0 and z.stdout:
                d = z.stdout; i = d.find(sa)
                if i >= 0:
                    j = d.find(b'\x88\x00', i)
                    main = d[i:j+2]
                break
_, g = agx_loop._tools()
dis = []
p = 0
while main and p < len(main):
    n = g.opcode_to_number(main[p:p+16]); de = g.get_instruction_descriptor(n); s = de.decode_size(n)
    dis.append([p, main[p:p+s].hex(), ' '.join(str(de.disassemble(n & ((1 << 8*s)-1))).split())]); p += s
rec = {'outputs_exact': exact, 'stack_words': ss, 'stack_adjust_hex': sa.hex(), 'main_hex': main.hex() if main else None,
       'disassembly': dis, 'air_stack_lines': air}
(out/'record.json').write_text(json.dumps(rec, indent=1)+'\n')
print(json.dumps({'outputs_exact': exact, 'main_found': main is not None, 'main_bytes': len(main or b''),
                  'stack_ops': [x[2].split()[0] for x in dis if x[1][:2] in ('b5', '35')], 'output': str(out)}))
sys.exit(0 if exact and main else 1)
