#!/usr/bin/env python3
"""atom.add.u64 emulated with two 32-bit device atomics (safe-gap: 64-bit atomics). Direct DRM, straight-line, no loops, no locks.

AGX has no 64-bit add / CAS / exchange (results/2026-10-17-atomic-variants; Honeykrisp reports shaderBufferInt64Atomics = 0). Emulation of
atomicAdd on a 64-bit word at table words (t, t + 1) = (lo, hi):
    old_lo = atomic_add(lo, v_lo)           (returned)
    carry  = (old_lo + v_lo) <u v_lo
    old_hi = atomic_add(hi, v_hi + carry)   (returned)           ->  old = (old_hi, old_lo)
The final 64-bit value is exact (addition commutes); the returned old value is exact only when no other lane touches the word
between the two adds, so under contention it can be torn. This measures how.
Modes: distinct (every lane its own word), shared (all lanes one word, random 64-bit addends), ticket (all lanes add 1 to a word that
starts 256 below a 2^32 boundary: the returned values should be 4,096 distinct consecutive numbers), nored (same as shared, no return).
  run_drm_atom64.py offline|hardware
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
M32, M64 = 0xffffffff, (1 << 64)-1


def body(n, ret=True):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [load(8, 1, True)]                                                    # v_lo
    for k, r in ((1, 9), (2, 10)):
        ins += [mov(6, k*n), e('iadd r7, r1, r6'), load(r, 7, True)]            # v_hi, t (the lo word index; hi = t + 1)
    ins += [e('wait 0'), e('iadd r11, r10, 1'),
            DA.atomic(0, 12, 10, 8, True), e('wait 0'),                         # old_lo -> r12 (the carry needs it even if the result is unused)
            e('iadd r13, r12, r8'), e('icmpsel ult, r14, r13, r8, 1, 0'), e('iadd r15, r9, r14'),   # carry; v_hi + carry
            DA.atomic(0, 16, 11, 15, True), e('wait 0')]                        # old_hi -> r16
    ins += [mov(6, 3*n), e('iadd r7, r1, r6'), agx_loop.store(12, 8, 7),
            mov(6, 4*n), e('iadd r7, r1, r6'), agx_loop.store(16, 8, 7), e('wait 0'), mov(2, 0)]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def make(mode, n, rng):
    vals, tgt, init = [], [], {}
    base = 5*n
    if mode == 'distinct':
        for i in range(n):
            vals.append(rng.getrandbits(64)); tgt.append(base+2*i); init[base+2*i] = rng.getrandbits(64)
    elif mode == 'shared':
        for i in range(n):
            vals.append(rng.getrandbits(64)); tgt.append(base)
        init[base] = rng.getrandbits(64)
    elif mode == 'ticket':
        for i in range(n):
            vals.append(1); tgt.append(base)
        init[base] = 0xffffff00
    else:   # wrap: addends of exactly 2^31 + small, so the low word wraps at nearly every add
        for i in range(n):
            vals.append((1 << 31)+rng.getrandbits(8)); tgt.append(base)
        init[base] = rng.getrandbits(64)
    return vals, tgt, init


def table(vals, tgt, init, n, words_total):
    t = [0xcdcdcdcd]*words_total
    for i, v in enumerate(vals):
        t[i] = v & M32; t[n+i] = v >> 32; t[2*n+i] = tgt[i]
    for k in range(5*n, words_total):
        t[k] = 0
    for k, v in init.items():
        t[k] = v & M32; t[k+1] = v >> 32
    return t


def analyse(mode, vals, tgt, init, t, n):
    olo, ohi = t[3*n:4*n], t[4*n:5*n]
    olds = [(ohi[i] << 32) | olo[i] for i in range(n)]
    final = {k: (t[k+1] << 32) | t[k] for k in init}
    exp_final = {}
    for i, v in enumerate(vals):
        exp_final[tgt[i]] = (exp_final.get(tgt[i], init[tgt[i]]) + v) & M64
    final_ok = all(final[k] == exp_final[k] for k in init)
    res = {'mode': mode, 'lanes': n, 'final_exact': final_ok}
    if mode == 'distinct':
        res['old_exact'] = all(olds[i] == init[tgt[i]] for i in range(n))
    elif mode == 'ticket':
        want = set(range(init[tgt[0]], init[tgt[0]]+n))
        got = set(olds)
        res['distinct_returned'] = len(got); res['in_expected_range'] = len(got & want); res['duplicates'] = n-len(got)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--lanes', type=int, default=4096)
    p.add_argument('--repeats', type=int, default=8)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/atom64'))
    a = p.parse_args()
    n = a.lanes
    code = drm.build_main(body(n, True))
    modes = ['distinct', 'shared', 'ticket', 'wrap']
    rng = random.Random(9)
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        for mode in modes:
            vals, tgt, init = make(mode, n, rng)
            words = 5*n+2*n+4
            o, t = cov.simulate(code, n, 32, 64, 0, table(vals, tgt, init, n, words))
            print('simulator', analyse(mode, vals, tgt, init, t, n))
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'lanes': n, 'results': []}
    for rep in range(a.repeats):
        for mode in modes:
            vals, tgt, init = make(mode, n, random.Random(100*rep+len(mode)))
            words = 5*n+2*n+4
            tb = table(vals, tgt, init, n, words)
            (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{words}I', *tb))
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '64', str(out/'t.bin')],
                               capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
            smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
            if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
            t = list(struct.unpack(f'<{words}I', (out/'t.out').read_bytes()))
            res = {'rep': rep, **analyse(mode, vals, tgt, init, t, n)}
            rec['results'].append(res)
            print(json.dumps(res), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
