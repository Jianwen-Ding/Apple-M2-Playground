#!/usr/bin/env python3
"""64-bit pointer arithmetic feeding a register-base device_load (direct DRM).

Step 1 reads uniforms u8 and u9 into the output with no memory access and checks
them against the table VA the harness prints (u8 = low word, u9 = high word), so a
misread numbering can never produce a bad address. Step 2 loads through register
bases built with Mesa-emitted 64-bit adds; every address stays inside the table.
"""
import json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA

REPO = Path(__file__).resolve().parents[1]
S = Path(sys.argv[1] if len(sys.argv) > 1 else '/scratch/apple-m2-playground/drm-compute/int64/ptr-run')
S.mkdir(parents=True, exist_ok=True)
subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(S/'drm_compute')], check=True)
e = agx_loop.encode; mov = agx_loop.chains.mov_imm
T = [w*7+3 for w in range(320)]


def run(code, lanes):
    (S/'c.bin').write_bytes(drm.build_main(code)+bytes(16)); (S/'t.bin').write_bytes(struct.pack('<320I', *T))
    r = subprocess.run([str(S/'drm_compute'), '/dev/dri/renderD128', str(S/'c.bin'), str(lanes), str(S/'rb'), '1', '64', str(S/'t.bin')],
                       capture_output=True, timeout=20)
    lines = r.stdout.decode().splitlines()
    if r.returncode or not any('"rep"' in l for l in lines): sys.exit('dispatch failed')
    va = [json.loads(l)['table']['va'] for l in lines if '"table"' in l][0]
    return list(struct.unpack(f'<{lanes+32}I', (S/'rb').read_bytes()))[8:8+lanes], va


rec = {'T_formula': 'T[w] = 7w + 3', 'cases': {}}
lo, va = run(e('iadd r2, u8, 0'), 32); hi, _ = run(e('iadd r2, u9, 0'), 32)
rec['uniform_split'] = {'va': va, 'u8': lo[0], 'u9': hi[0], 'ok': set(lo) == {va & 0xffffffff} and set(hi) == {va >> 32}}
if not rec['uniform_split']['ok']: sys.exit('uniform numbering differs; not dereferencing')
pre = [e('iadd r12, u8, 0'), e('iadd r13, u9, 0')]
cases = {
    'regbase+lane<<2': (pre+[e('iadd r14_r15, r12_r13, r1, lsl 2'), e('device_load 0, i32, x, r2, r14_r15, 0, unsigned'), e('wait 0')], lambda i: i),
    'regbase,index r1': (pre+[e('device_load 0, i32, x, r2, r12_r13, r1, unsigned'), e('wait 0')], lambda i: i),
    'regbase+1024+sx(lane-64)<<2': (pre+[mov(10, 1024), e('iadd r14_r15, r12_r13, r10'), mov(11, 64), e('isub r16, r1, r11'),
                                        e('iadd r14_r15, r14_r15, r16.sx, lsl 2'), e('device_load 0, i32, x, r2, r14_r15, 0, unsigned'), e('wait 0')], lambda i: 192+i),
}
for name, (ins, idx) in cases.items():
    DA.decode_lengths(b''.join(ins), [len(x) for x in ins])
    w, _ = run(b''.join(ins), 64)
    rec['cases'][name] = {'ok': w == [T[idx(i)] for i in range(64)], 'out': w, 'body': b''.join(ins).hex()}
    print(name, rec['cases'][name]['ok'])
(S/'record.json').write_text(json.dumps(rec)+'\n')
print(json.dumps({'uniform_split_ok': rec['uniform_split']['ok'], 'all_ok': all(c['ok'] for c in rec['cases'].values()), 'output': str(S)}))
