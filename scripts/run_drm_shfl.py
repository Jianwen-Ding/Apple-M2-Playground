#!/usr/bin/env python3
"""PTX shfl.sync (up / down / bfly / idx, any clamp c and segment mask) lowered to AGX simd_shuffle forms, checked against the
PTX semantics on hardware (safe, straight-line, direct DRM).

PTX reference (membermask = all lanes): lane = laneid; bval = b[4:0]; cval = c[4:0]; segmask = c[12:8];
  maxLane = (lane & segmask) | (cval & ~segmask); minLane = lane & segmask;
  up: j = lane - bval, p = j >= maxLane | down: j = lane + bval, p = j <= maxLane | bfly: j = lane ^ bval, p = j <= maxLane |
  idx: j = minLane | (bval & ~segmask), p = j <= maxLane;  d = p ? a[j] : a (the lane's own value).
AGX `simd_shuffle` takes the low two bits of the lane index from the OR over the *source* quad's index operands (the
simulator models it; coverage cases pass), so a per-lane index is exact only when those bits are uniform. Generic lowering: compute j
and p with integer ops, then four simd_shuffles with the low index bits forced to 0..3 and a select on (j & 3); `fast` lowering for a
compile-time-constant b and the default clamp uses simd_shuffle_up / _down / _xor / simd_shuffle directly.
  run_drm_shfl.py offline|hardware
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
M32 = 0xffffffff
MODES = ['up', 'down', 'bfly', 'idx']


def default_c(mode, width=32):
    return ((32-width) << 8) | (0 if mode == 'up' else 31)


def ptx_shfl(mode, a, b, c):
    """a, b: 32 per-lane values -> (d[32], p[32])."""
    d, p = [], []
    cval, seg = c & 31, (c >> 8) & 31
    for lane in range(32):
        bval = b[lane] & 31
        maxl = (lane & seg) | (cval & ~seg & 31)
        minl = lane & seg
        if mode == 'up':
            j = lane - bval; pv = j >= maxl
        elif mode == 'down':
            j = lane + bval; pv = j <= maxl
        elif mode == 'bfly':
            j = lane ^ bval; pv = j <= maxl
        else:
            j = minl | (bval & ~seg & 31); pv = j <= maxl
        d.append(a[j] if pv else a[lane]); p.append(int(pv))
    return d, p


def generic_lines(mode, c):
    cval, seg = c & 31, (c >> 8) & 31
    L = ['and r10, r1, 31', 'and r11, r9, 31',
         f'and r12, r10, {seg}', f'and r13, r10, {seg}', f'or r13, r13, {cval & ~seg & 31}']
    if mode == 'idx':
        L += [f'and r14, r11, {~seg & 31}', 'or r14, r14, r12', 'icmpsel ugt, r15, r14, r13, 0, 1']
    elif mode == 'down':
        L += ['iadd r14, r10, r11', 'icmpsel ugt, r15, r14, r13, 0, 1']
    elif mode == 'bfly':
        L += ['xor r14, r10, r11', 'icmpsel ugt, r15, r14, r13, 0, 1']
    else:
        L += ['isub r14, r10, r11', 'icmpsel slt, r15, r14, r13, 0, 1']
    L += ['icmpsel ueq, r16, r15, 0, r10, r14',                       # index to use: j if p else the lane itself
          'and r17, r16, 3', 'and r18, r16, 28']
    for k in range(4):
        L += [f'or r{19+k}, r18, {k}', f'simd_shuffle r{23+k}, r8, r{19+k}l']
    L += ['icmpsel ueq, r28, r17, 2, r25, r26', 'icmpsel ueq, r28, r17, 1, r24, r28', 'icmpsel ueq, r28, r17, 0, r23, r28']
    return L, 28, 15


def naive_lines(mode, c):
    """Negative control: one simd_shuffle with the per-lane index (low bits not uniform within a quad)."""
    L, rd, rp = generic_lines(mode, c)
    k = L.index('icmpsel ueq, r16, r15, 0, r10, r14')
    return L[:k+1]+['simd_shuffle r28, r8, r16l'], 28, 15


def fast_lines(mode, b):
    b &= 31
    op = {'up': 'simd_shuffle_up', 'down': 'simd_shuffle_down', 'bfly': 'simd_shuffle_xor', 'idx': 'simd_shuffle'}[mode]
    return [f'{op} r28, r8, {b}'], 28, None


def build(n, lines, rd, rp):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [load(8, 1, True), mov(6, n), e('iadd r7, r1, r6'), load(9, 7, True), e('wait 0')]
    ins += [e(l) for l in lines]
    ins += [mov(6, 2*n), e('iadd r7, r1, r6'), agx_loop.store(rd, 8, 7)]
    if rp is not None:
        ins += [mov(6, 3*n), e('iadd r7, r1, r6'), agx_loop.store(rp, 8, 7)]
    ins += [e('wait 0'), mov(2, 0)]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def data(groups, seed):
    rng = random.Random(seed)
    a, b = [], []
    for g in range(groups):
        kind = g % 6
        a += [rng.getrandbits(32) for _ in range(32)]
        if kind == 0:   b += [rng.randint(0, 40)]*32                       # warp-uniform
        elif kind == 1: b += [rng.randint(0, 40) for _ in range(32)]       # per-lane, small
        elif kind == 2: b += [rng.getrandbits(32) for _ in range(32)]      # per-lane, full width
        elif kind == 3: b += rng.sample(range(32), 32)                     # a permutation of the lanes
        elif kind == 4: b += [rng.choice([0, 1, 2, 3, 31, 32, 33, 63])]*32   # uniform edge amounts
        else:           b += [(l*5+rng.randint(0, 3)) & 63 for l in range(32)]
    return a, b


def configs():
    cs = []
    for mode in MODES:
        for w in (32, 16, 8, 4, 2, 1):
            cs.append((mode, default_c(mode, w)))
    rng = random.Random(5)
    for mode in MODES:
        for _ in range(6):
            cs.append((mode, rng.getrandbits(13)))
    return cs


def run_hw(exe, out, code, n, tb):
    (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '80', str(out/'t.bin')],
                       capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
    smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
    if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
        sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
    return list(struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--groups', type=int, default=240)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/shfl'))
    a = p.parse_args()
    n = a.groups*32
    A, B = data(a.groups, 11)
    tb = A+B+[0xcdcdcdcd]*(2*n)
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    if a.mode == 'hardware':
        subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    else:
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
    rec = {'groups': a.groups, 'results': []}
    total_bad = 0

    def evaluate(name, lines, rd, rp, mode, c, fast_b=None):
        code = drm.build_main(build(n, *( [lines, rd, rp] )))
        if a.mode == 'offline':
            o, t = cov.simulate(code, n, 32, 80, 0, tb)
        else:
            t = run_hw(exe, out, code, n, tb)
        bad = 0; bad_groups = {}
        for g in range(a.groups):
            sl = slice(32*g, 32*g+32)
            bb = [fast_b]*32 if fast_b is not None else B[sl]
            d, pv = ptx_shfl(mode, A[sl], bb, c)
            ok = t[2*n+32*g:2*n+32*g+32] == d and (rp is None or t[3*n+32*g:3*n+32*g+32] == pv)
            if not ok:
                bad += 1; bad_groups[g % 6] = bad_groups.get(g % 6, 0)+1
        res = {'name': name, 'mode': mode, 'c': c, 'groups_bad': bad, 'bad_by_kind': bad_groups, 'instructions': len(lines)}
        rec['results'].append(res)
        return bad

    for mode, c in configs():
        L, rd, rp = generic_lines(mode, c)
        total_bad += evaluate(f'generic-{mode}-c{c:#x}', L, rd, rp, mode, c)
    # negative control: the naive lowering must fail exactly on groups whose index low bits differ inside a quad
    for mode in MODES:
        L, rd, rp = naive_lines(mode, default_c(mode))
        evaluate(f'naive-{mode}', L, rd, rp, mode, default_c(mode))
    # fast lowering: compile-time constant amount, default clamp, all amounts 0..63
    nfast = 0
    for mode in MODES:
        for b in range(64):
            L, rd, rp = fast_lines(mode, b)
            # the data set for the fast programs: reuse A; b is the constant (PTX masks it to 5 bits)
            total_bad += evaluate(f'fast-{mode}-b{b}', L, rd, rp, mode, default_c(mode), fast_b=b)
            nfast += 1
    print(f'{a.mode}: {len(configs())} generic configs + {nfast} fast programs, groups={a.groups}, mismatching groups total {total_bad}')
    for r in rec['results']:
        if r['groups_bad'] and not r['name'].startswith('naive'):
            print('  BAD', r)
        if r['name'].startswith('naive'):
            print('  control', r['name'], 'groups wrong', r['groups_bad'], 'by group kind', r['bad_by_kind'])
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 1 if total_bad else 0


if __name__ == '__main__':
    sys.exit(main())
