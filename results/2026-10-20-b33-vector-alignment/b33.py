#!/usr/bin/env python3
"""B33: alignment of 64/128-bit device loads and stores. Table word w = 0xa0000000 | w. Lane i uses element index
idx_i (byte address 4 * idx_i). Load cases copy the n loaded components to table[3072 + 4i + c] with plain stores;
store cases write 0xb0000000 | i << 4 | c with one n-wide store at idx_i in region 2048+. Usage: b33.py sim|gpu CASE
CASE: load2 load4 store2 store4 (idx_i = 16 i + i % 4: byte offsets 0/4/8/12 mod 16), load4x / store4x (lanes 0-15:
idx = 15 + 16 k crossing 64-byte lines; lanes 16-31: idx = 1021 + 1024 k - ... crossing 4 KiB pages)"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a); st = agx_loop.store
A = '/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_asm'
def asm(line): return bytes.fromhex(subprocess.run([A], input=line + '\n', capture_output=True, text=True).stdout.split('\t')[0].strip())
N = 32
def idx(case, i):
    if case.endswith('x'):
        return 15 + 16 * i if i < 16 else 1022 + 1024 * (i - 16)     # 64 B lines (bytes 60..75 + 64k) / 4 KiB pages (bytes 4088..4103 + 4096k)
    return 16 * i + i % 4

def body(case):
    n = 4 if '4' in case else 2
    store = case.startswith('store')
    b = mov(5, 0)
    # r5 = idx_i, computed from lane id with a small table lookup: idx stored at table[4000 + i]
    b += mov(26, 4000) + e('iadd r6, r1, r26') + e('device_load 0, i32, x, r5, u8_u9, r6, unsigned') + e('wait 0')
    if store:
        b += mov(26, 2048) + e('iadd r5, r5, r26')
        for c in range(n):
            b += mov(26, 0xb0000000 | c) + mov(27, 4) + e(f'imadd r{12 + c}, r1, r27, r26')   # 0xb0000000 | 4i + c ... unique
        x = int('45112c0e00c01200', 16)
        b += asm(f'@mask={(1 << n) - 1},R=24,A=16,O=10\t!45112c0e00c01200') + e('wait 0')
    else:
        regs = '_'.join(f'r{8 + c}' for c in range(n))
        b += e(f'device_load 0, i32, {"xy" if n == 2 else "xyzw"}, {regs}, u8_u9, r5, unsigned') + e('wait 0')
        b += mov(26, 4) + mov(27, 3072) + e('imadd r20, r1, r26, r27')
        for c in range(n):
            b += st(8 + c, 8, 20) + mov(26, 1) + e('iadd r20, r20, r26')
        b += e('wait 0')
    return b + e('iadd r2, r1, 0')

def main():
    mode, case = sys.argv[1], sys.argv[2]
    n = 4 if '4' in case else 2
    t = [0xa0000000 | w for w in range(40000)]
    for i in range(N): t[4000 + i] = idx(case, i)
    bd = body(case); cov.gate(bd); code = drm.build_main(bd)
    if mode == 'sim':
        out, tab = cov.simulate(code, N, N, 64, 0, t)
    else:
        import run_bench as B, gpu_safety; gpu_safety.require_budget(1)
        out, tab, fw, _ = RS.run(B.Runner(Path('/scratch/agxsim-runs/b33/run')), code, N, N, t, 64)
    res = {'mode': mode, 'case': case}
    if case.startswith('load'):
        got = [[tab[3072 + 4 * i + c] for c in range(n)] for i in range(N)]
        byte = [[t[idx(case, i) + c] for c in range(n)] for i in range(N)]
        down = [[t[(idx(case, i) & ~(n - 1)) + c] for c in range(n)] for i in range(N)]
        res.update(byte_model=sum(got[i] == byte[i] for i in range(N)), rounded_model=sum(got[i] == down[i] for i in range(N)),
                   by_offset={k: [got[i] == byte[i] for i in range(N) if idx(case, i) % 4 == k].count(True) for k in range(4)})
    else:
        ch = {w: tab[w] for w in range(2048, 40000) if tab[w] != t[w]}
        byte = sum(all(tab[2048 + idx(case, i) + c] == 0xb0000000 | (4 * i + c) for c in range(n)) for i in range(N))
        down = sum(all(tab[2048 + (idx(case, i) & ~(n - 1)) + c] == 0xb0000000 | (4 * i + c) for c in range(n)) for i in range(N))
        res.update(byte_model=byte, rounded_model=down, words_changed=len(ch))
    print(json.dumps(res))
main()
