#!/usr/bin/env python3
"""Exact (non-ftz) PTX setp.{eq,lt,gt,le,ge}.f32 from integer instructions (safe-01 part 3). Direct DRM, no loops.

The AGX float compare reads subnormal operands as +-0 (results/2026-10-18-fcmp), so default PTX compares of subnormals
need a fix-up. Compare in integer space instead, per operand x:
    m = x & 0x7fffffff
    key = x ^ (asr(x, 31) | 0x80000000)     # monotonic unsigned key of the float order (-inf .. +inf)
    key = (m == 0) ? 0x80000000 : key       # -0 == +0
    nan = m > 0x7f800000
setp.lt: !nan(a) && !nan(b) && ka < kb; gt swaps the keys; le / ge add ka == kb; eq is ka == kb (NaN false).
`min` / `max` use the raw key (no zero fix: -0 < +0) to pick an operand's bits, then let a NaN operand lose.
Same 48 x 48 edge-value pairs as run_drm_fcmp.py; each lane writes seven result words (eq lt gt le ge min max). The program is
first run in agx_run and compared with an IEEE host model (not with hardware), then on hardware.
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_fcmp import VALS, N

REPO = Path(__file__).resolve().parents[1]
NAMES = ['eq', 'lt', 'gt', 'le', 'ge', 'min', 'max']
# NaN-accepting (.u) variants and float-result set(): verified in the same lanes when extra=True.
UNAMES = ['neu', 'equ', 'ltu', 'leu', 'gtu', 'geu', 'num', 'nan']
FNAMES = ['set_lt_f', 'set_gt_f', 'set_eq_f', 'set_le_f', 'set_ge_f']
FNAMES_SRC = {'set_lt_f': 'r25', 'set_gt_f': 'r26', 'set_eq_f': 'r27', 'set_le_f': 'r28', 'set_ge_f': 'r29'}
f32 = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
isnan = lambda b: (b & 0x7f800000) == 0x7f800000 and b & 0x7fffff


def ptx_minmax(name, a, b):
    """PTX min/max.f32 (non-ftz): a NaN operand loses, -0 < +0, subnormals compare exactly; both NaN -> a NaN."""
    if isnan(a) and isnan(b):
        return 'nan'
    if isnan(a):
        return b
    if isnan(b):
        return a
    x, y = f32(a), f32(b)
    if x == y:
        if x == 0:    # +-0: min takes the negative zero, max the positive one
            return (a | b) if name == 'min' else (a & b)
        return a
    return a if (x < y) == (name == 'min') else b


def ieee(name, a, b):
    if name in ('min', 'max'):
        return ptx_minmax(name, a, b)
    if name == 'num':
        return int(not (isnan(a) or isnan(b)))
    if name == 'nan':
        return int(bool(isnan(a) or isnan(b)))
    if name in ('neu', 'equ', 'ltu', 'leu', 'gtu', 'geu'):
        if isnan(a) or isnan(b):
            return 1
        x, y = f32(a), f32(b)
        base = {'neu': x != y, 'equ': x == y, 'ltu': x < y, 'leu': x <= y, 'gtu': x > y, 'geu': x >= y}
        return int(base[name])
    if name in FNAMES:
        if isnan(a) or isnan(b):
            return 0x00000000
        x, y = f32(a), f32(b)
        rel = {'set_lt_f': x < y, 'set_gt_f': x > y, 'set_eq_f': x == y,
               'set_le_f': x <= y, 'set_ge_f': x >= y}[name]
        return 0x3f800000 if rel else 0x00000000
    if isnan(a) or isnan(b):
        return 0
    x, y = f32(a), f32(b)
    return int({'eq': x == y, 'lt': x < y, 'gt': x > y, 'le': x <= y, 'ge': x >= y}[name])


def same(name, got, want):
    """Exact equality, except that any NaN result matches the host's 'nan' (both operands NaN)."""
    return all(g == w or (w == 'nan' and isnan(g)) for g, w in zip(got, want))


def body(n, extra=False):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(12, 0x7fffffff), mov(13, 0x80000000), mov(14, 0x7f800000), mov(15, 31), mov(21, 1), mov(22, 0),
           mov(16, n), e('iadd r17, r1, r16'), load(6, 1, True), load(7, 17, True), e('wait 0')]
    for x, (m, k, t, nn) in (('r6', ('r8', 'r9', 'r10', 'r11')), ('r7', ('r18', 'r19', 'r20', 'r23'))):
        raw = 'r32' if x == 'r6' else 'r33'
        ins += [e(f'and {m}, {x}, r12'), e(f'asr {t}, {x}, r15'), e(f'or {t}, {t}, r13'), e(f'xor {raw}, {x}, {t}'),
                e(f'icmpsel ueq, {k}, {m}, 0, r13, {raw}'),                    # key = (m == 0) ? 0x80000000 : raw key
                e(f'icmpsel ugt, {nn}, {m}, r14, 1, 0')]                      # nan flag
    # r9 = ka, r19 = kb, r11 = nan(a), r23 = nan(b); r24 = nan(a) | nan(b)
    ins += [e('or r24, r11, r23'),
            e('icmpsel ult, r25, r9, r19, 1, 0'),            # lt raw
            e('icmpsel ugt, r26, r9, r19, 1, 0'),            # gt raw
            e('icmpsel ueq, r27, r9, r19, 1, 0')]            # eq raw
    out = [('eq', 'r27'), ('lt', 'r25'), ('gt', 'r26')]
    ins += [e('or r28, r25, r27'), e('or r29, r26, r27')]    # le raw, ge raw
    out += [('le', 'r28'), ('ge', 'r29')]
    for i, (name, reg) in enumerate(out):
        ins += [e(f'icmpsel ueq, {reg}, r24, 0, {reg}, 0'),                        # NaN -> 0
                mov(30, (2+i)*n), e('iadd r31, r1, r30'), agx_loop.store(int(reg[1:]), 8, 31)]
    # min / max: raw keys pick an operand's bits (ties are identical bits), then a NaN operand loses
    for i, (name, cc, reg) in enumerate((('min', 'ult', 'r34'), ('max', 'ugt', 'r35'))):
        ins += [e(f'icmpsel {cc}, {reg}, r32, r33, r6, r7'),
                e(f'icmpsel ueq, {reg}, r23, 0, {reg}, r6'),                      # b is NaN -> a
                e(f'icmpsel ueq, {reg}, r11, 0, {reg}, r7'),                      # a is NaN -> b
                mov(30, (7+i)*n), e('iadd r31, r1, r30'), agx_loop.store(int(reg[1:]), 8, 31)]
    ins += [e('wait 0'), e('iadd r2, r27, 0')]
    if extra:
        # NaN-accepting variants: same raw relations, NaN forces true (literals/regs only, all forms used above)
        ins += [e('icmpsel ueq, r36, r27, 0, r21, r22'), e('or r36, r36, r24'),          # neu = !eq_raw | nan
                mov(30, 9*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                e('or r36, r27, r24'),                                                    # equ = eq_raw | nan
                mov(30, 10*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                e('or r36, r25, r24'),                                                    # ltu
                mov(30, 11*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                e('or r36, r28, r24'),                                                    # leu
                mov(30, 12*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                e('or r36, r26, r24'),                                                    # gtu
                mov(30, 13*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                e('or r36, r29, r24'),                                                    # geu
                mov(30, 14*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                e('icmpsel ueq, r36, r24, 0, r21, r22'),                                  # num = !nan
                mov(30, 15*n), e('iadd r31, r1, r30'), agx_loop.store(36, 8, 31),
                mov(30, 16*n), e('iadd r31, r1, r30'), agx_loop.store(24, 8, 31),         # nan = nan mask
                mov(30, 22*n), load(37, 30, True), e('wait 0')]                           # float 1.0 from the table
        for i, (fname, src) in enumerate(FNAMES_SRC.items()):                             # (mov_imm cannot target r32+)
            ins += [e(f'icmpsel ueq, r38, {src}, 0, r22, r37'),                           # rel ? 1.0 : 0.0
                    mov(30, (17+i)*n), e('iadd r31, r1, r30'), agx_loop.store(38, 8, 31)]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--extra', action='store_true', help='also verify NaN-accepting (.u) variants and float-result set')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fcmp-fixup'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    n = N*N
    A = [VALS[i//N] for i in range(n)]; B = [VALS[i % N] for i in range(n)]
    names = NAMES if not a.extra else NAMES + UNAMES + FNAMES
    if not a.extra:
        table = A+B+[0xcdcdcdcd]*(7*n)
    else:
        table = A+B+[0xcdcdcdcd]*(20*n)+[0x3f800000]*n  # outputs at 2..21n, float 1.0 word at 22n
    nwords = len(table)//n
    want = {nm: [ieee(nm, x, y) for x, y in zip(A, B)] for nm in names}
    code = drm.build_main(body(n, extra=a.extra))
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        o, t = cov.simulate(code, n, 32, 80, 0, table)
        for i, nm in enumerate(names):
            got = t[(2+i)*n:(3+i)*n]
            ok = same(nm, got, want[nm])
            print(nm, 'simulator == host model on all pairs:', ok)
            assert ok, nm
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'vals': VALS, 'names': names, 'extra': a.extra, 'results': []}
    for rep in range(a.repeats):
        (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{nwords*n}I', *table))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '80', str(out/'t.bin')],
                           capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        t = struct.unpack(f'<{nwords*n}I', (out/'t.out').read_bytes())
        res = {'rep': rep, 'out': {nm: list(t[(2+i)*n:(3+i)*n]) for i, nm in enumerate(names)}}
        rec['results'].append(res)
        print(rep, {nm: same(nm, res['out'][nm], want[nm]) for nm in names}, flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
