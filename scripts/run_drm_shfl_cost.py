#!/usr/bin/env python3
"""Cost of the shfl.sync lowerings (2026-10-18 shfl finding left this open): native single simd_shuffle forms against the
generic 21/22-instruction sequence, as dependent chains. Direct DRM, straight-line, simulator-gated.

Each lane runs K dependent shuffles: the shuffled value feeds the next iteration's source, K in {1, 64, 128}, 131,072 lanes,
firmware time; cost per shuffle = slope against K. Variants:
  iadd       : iadd r8, r8, 1 (dependent ALU reference)
  xor1 / up1 / idxreg : native simd_shuffle_xor r8, r8, 1 / simd_shuffle_up r8, r8, 1 / simd_shuffle r8, r8, r9l (uniform index)
  gen_idx / gen_up / gen_bfly : the full generic lowering (index math recomputed each iteration, as a compiler would emit it)
Offline mode runs every program (K = 1 and 64) in the Rust simulator and stores the outputs; hardware mode requires the
hardware output to equal the simulator's for K = 64 (exactness check) and records times.
  run_drm_shfl_cost.py offline|hardware [--result FILE] [--ks 1,64,128] [--kinds iadd,xor1,...]
The retained record used two hardware runs: the default (all kinds, K 1/64/128) and natives with --ks 64,1024,2048 --repeats 7.
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_shfl import generic_lines, default_c

REPO = Path(__file__).resolve().parents[1]
KS = (1, 64, 128)


def body(kind):
    if kind == 'iadd':
        return ['iadd r8, r8, 1']
    if kind == 'xor1':
        return ['simd_shuffle_xor r8, r8, 1']
    if kind == 'up1':
        return ['simd_shuffle_up r8, r8, 1']
    if kind == 'idxreg':
        return ['simd_shuffle r8, r8, r9l']
    mode = kind.split('_')[1]
    L, rd, _ = generic_lines(mode, default_c(mode))
    L = L[:-1] + [L[-1].replace('icmpsel ueq, r28,', 'icmpsel ueq, r8,')]   # final select writes the chain register
    return L


def build(kind, k, n):
    e, mov = agx_loop.encode, chains.mov_imm
    ins = [load(8, 1, True), mov(6, n), e('iadd r7, r1, r6'), load(9, 7, True), e('wait 0')]
    for _ in range(k):
        ins += [e(l) for l in body(kind)]
    ins += [mov(6, 2*n), e('iadd r7, r1, r6'), agx_loop.store(8, 8, 7), e('wait 0'), mov(2, 0)]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins), len(ins)


def table(n):
    rng = random.Random(5)
    a = [rng.getrandbits(32) for _ in range(n)]
    b = []
    for g in range(n//32):
        b += [rng.randint(0, 31)]*32           # warp-uniform shuffle amount / index (the common CUDA case)
    return a+b+[0xcdcdcdcd]*n


KINDS = ['iadd', 'xor1', 'up1', 'idxreg', 'gen_idx', 'gen_up', 'gen_bfly']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--lanes', type=int, default=131072)
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/shfl-cost'))
    p.add_argument('--sim', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/shfl-cost/sim.json'))
    p.add_argument('--result', type=Path)
    p.add_argument('--ks', default='1,64,128', help='comma-separated chain lengths (64 must be included for the exactness check)')
    p.add_argument('--kinds', default=','.join(KINDS))
    a = p.parse_args()
    n = a.lanes
    tb = table(n)
    regs = 2*32+8
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        sim = {}
        for kind in KINDS:
            prog, ni = build(kind, 64, n)
            o, t = cov.simulate(drm.build_main(prog), n, 32, regs, 0, tb)
            sim[kind] = list(t[2*n:3*n])
            print(kind, ni, 'instructions; simulated, sample', [hex(x) for x in sim[kind][:3]], flush=True)
        a.sim.parent.mkdir(parents=True, exist_ok=True)
        a.sim.write_text(json.dumps(sim)+'\n')
        return 0
    sim = json.loads(a.sim.read_text())
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'lanes': n, 'runs': [], 'exact_vs_sim': {}}
    ks = [int(x) for x in a.ks.split(',')]
    rec['ks'] = ks
    for rep in range(a.repeats):
        for kind in a.kinds.split(','):
            for k in ks:
                prog, ni = build(kind, k, n)
                (out/'c.bin').write_bytes(drm.build_main(prog)+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(regs), str(out/'t.bin')],
                                   capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
                smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                    sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
                t = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
                if k == 64:
                    rec['exact_vs_sim'].setdefault(kind, []).append(list(t[2*n:3*n]) == sim[kind])
                x = {'rep': rep, 'kind': kind, 'k': k, 'instructions': ni, 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}
                rec['runs'].append(x)
                print(rep, kind, k, ni, x['fw_ns'], rec['exact_vs_sim'].get(kind, [None])[-1] if k == 64 else '', flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
