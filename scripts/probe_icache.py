#!/usr/bin/env python3
"""Instruction-cache capacity probe (safe: straight-line iadd bodies in Mesa's counted-loop shape, emulator-gated).

One SIMD group (32 lanes) runs a counted loop whose body is B bytes of independent `iadd rX, rX, 1` over 4 rotating
registers (r5..r8; fewer than the 9 destinations that trigger the result-cache slowdown). Trips are chosen so every
size executes about the same number of instructions. Time per body byte (firmware timestamps, clock held by
clock_keeper.py) is flat while the body fits in the instruction cache and rises to the streaming fetch rate beyond it.
Each body is checked in the applegpu emulator at 2 trips, and every hardware run against the exact register oracle.
  probe_icache.py [--sizes 512,1024,...] [--groups 1] [--instr 4000000] [--repeats 5] [--result FILE]
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
import run_agx_timestamps as chains

REPO = Path(__file__).resolve().parents[1]
REGS = (5, 6, 7, 8)
KINDS = {   # instruction text for step i (4 independent destinations), and its oracle contribution per execution
    'iadd8': (lambda r: f'iadd r{r}, r{r}, 1', 8),
    'and6': (lambda r: f'and r{r}, r{r}, r{r}', 6),         # value unchanged: oracle counts only the iadd tail
    'mov4': (lambda r: f'mov_imm r{r}l, 1', 4),             # r5..r8 low half = 1 after the body
}
STEP = agx_loop.encode('iadd r5, r5, 1')


def loop_part(size_bytes, kind, cnt_reg, lim_reg, base, shift_at=None):
    """One counted loop over a body of size_bytes; trip counter cnt_reg vs lim_reg; base = register offset of r5..r8."""
    e = agx_loop.encode
    fn, w = KINDS[kind]
    n = size_bytes // w
    regs = [r+base for r in REGS]
    ins = [e(fn(regs[i % 4])) for i in range(n)]
    if shift_at is not None:                          # one 2-byte wait after instruction k: the rest is shifted by 2
        k = int(n*shift_at)
        ins = ins[:k] + [e('wait 0')] + ins[k:]
    loop = b''.join(ins)
    loop += e(f'iadd r{cnt_reg}, 1, r{cnt_reg}.sx') + e(f'while_icmp r0l, ult, r{cnt_reg}, r{lim_reg}, 1')
    jump = e(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}')
    return loop+jump, n, len(loop)


def body(size_bytes, trips, kind='iadd8', dual=False, tag=False, select=32, pad=0, shift_at=None):
    """dual=True: SIMD groups with (thread index & 32) == 0 run loop A, the others a different loop B of the same size
    (two code footprints of size_bytes each on one core when the workgroup is 64 lanes)."""
    e, mov = agx_loop.encode, chains.mov_imm
    head = mov(3, 0)+mov(4, trips)+b''.join(mov(r, 0) for r in REGS)
    if pad:                                         # shift the loop start by `pad` bytes (2-byte waits: no ALU state)
        assert pad % 2 == 0
        head += e('wait 0')*(pad//2)
    if not dual:
        head += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
        lp, n, lb = loop_part(size_bytes, kind, 3, 4, 0, shift_at)
        tail = e('pop_exec r0l, 1')
    else:
        head += mov(12, select) + e('and r9, r1, r12')
        lpA, n, lb = loop_part(size_bytes, kind, 3, 4, 0)
        lpB, _, _ = loop_part(size_bytes, 'iadd8' if kind != 'iadd8' else 'and6', 3, 4, 0) if False else loop_part(size_bytes, kind, 3, 4, 0)
        # B differs in bytes from A: same instructions on a rotated register order (r6, r7, r8, r5)
        fn, w = KINDS[kind]
        order = (6, 7, 8, 5)
        lpB = b''.join(e(fn(order[i % 4])) for i in range(n))
        lpB += e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
        lpB += e(f'jmp_exec_any pc-{len(lpB)}', f'jmp_exec_any pc-{len(lpB)}')
        armA = e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + lpA + e('pop_exec r0l, 1')
        armB = e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1') + lpB + e('pop_exec r0l, 1')
        head += e('if_icmp r0l, ueq, r9, 0, 1') + e(f'jmp_exec_none pc+{6+len(armA)}', f'jmp_exec_none pc+{6+len(armA)}') + armA
        head += e('else_icmp r0l, nueq, r9, 0, 1') + e(f'jmp_exec_none pc+{6+len(armB)}', f'jmp_exec_none pc+{6+len(armB)}') + armB
        head += e('pop_exec r0l, 1')
        lp, tail = b'', b''
    tail += e('iadd r2, r5, r6') + e('iadd r2, r2, r7') + e('iadd r2, r2, r8')
    # tag the output with SR20 (cluster << 4 | core) in bits 24..31: r2 += core << 24 (oracles stay below 2^24)
    if tag:
        tail += e('get_sr r10, sr20', 'get_sr r10, sr20 (core_index)') + mov(11, 1 << 24) + e('imadd r2, r10, r11, r2')
    return head+lp+tail, n, lb


def oracle(n, trips, kind='iadd8'):
    if kind == 'iadd8':
        return (n*trips) & 0xffffffff
    if kind == 'and6':
        return 0
    return 4                                       # mov4: each of r5..r8 low half = 1 (n >= 4)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sizes', default='512,1024,2048,4096,6144,8192,12288,16384,24576,32768,49152,65536,98304,131072,196608,262144')
    p.add_argument('--groups', type=int, default=1)
    p.add_argument('--instr', type=int, default=4_000_000, help='body instructions executed per run (per group)')
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--gate-only', action='store_true')
    p.add_argument('--kind', default='iadd8', choices=sorted(KINDS))
    p.add_argument('--local', type=int, default=32, help='workgroup size in lanes (64 = two SIMD groups on one core)')
    p.add_argument('--select', type=int, default=32, help='dual: thread-index bit mask choosing loop B (32 = alternate SIMD groups / 32-lane workgroups, 256 = workgroups 8-15 with local 32)')
    p.add_argument('--shift-at', type=float, default=None, help='insert one 2-byte wait after this fraction of the body (misaligns the rest)')
    p.add_argument('--pad', type=int, default=0, help='bytes of wait 0 before the loop (shifts its start address)')
    p.add_argument('--dual', action='store_true', help='the two SIMD groups of a 64-lane workgroup run different loop bodies')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/icache'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    sizes = [int(x) for x in a.sizes.split(',')]
    for s in sizes:                                   # emulator gate: exact result at 2 trips, terminates
        b, n, _ = body(s, 2, a.kind, a.dual, select=a.select, pad=a.pad, shift_at=a.shift_at)
        st = agx_loop.emulate(b, 32, max_steps=4*n+1000)
        if st['r2'] != [oracle(n, 2, a.kind)]*32:
            sys.exit(f'emulator gate failed at {s} bytes: {st["r2"][:2]} != {oracle(n, 2)}')
    print('emulator gate passed for', len(sizes), 'sizes', flush=True)
    if a.gate_only:
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    lanes = 32*a.groups
    rec = {'groups': a.groups, 'instr': a.instr, 'pad': a.pad, 'shift_at': a.shift_at, 'kind': a.kind, 'local': a.local, 'dual': a.dual, 'step_bytes': KINDS[a.kind][1], 'rows': []}
    import sim_gate
    rounded = (lanes+31)//32*32
    for s in sizes:
        n0 = s // KINDS[a.kind][1]
        trips = max(2, a.instr // n0)
        b, n, lb = body(s, trips, a.kind, a.dual, tag=True, select=a.select, pad=a.pad, shift_at=a.shift_at)
        want = oracle(n, trips, a.kind)
        code = drm.build_main(b)
        gate = sim_gate.require(drm.build_main(body(s, 3, a.kind, a.dual, select=a.select, pad=a.pad, shift_at=a.shift_at)[0]), lanes, oracle(n, 3, a.kind), regs=24)   # same body, 3 trips
        (out/'c.bin').write_bytes(code+bytes(16))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(lanes), str(out/'rb'), str(a.repeats), '24'],
                           capture_output=True, timeout=300, env={'PATH': '/usr/bin', 'AGX_LOCAL_X': str(a.local)})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != a.repeats or not all(x['fw_ts'] for x in smp):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        w = list(struct.unpack('<'+'I'*(rounded+32), (out/'rb').read_bytes()))
        ok = [x & 0xffffff for x in w[8:8+lanes]] == [want & 0xffffff]*lanes and all(x == 0xcdcdcdcd for x in w[:8])
        cores = [w[8+32*g] >> 24 for g in range(lanes//32)]
        arms = [int(bool((32*g) & a.select)) for g in range(lanes//32)] if a.dual else None
        fw = [x['fw_ts'][1]-x['fw_ts'][0] for x in smp]
        row = {'bytes': s, 'body_instr': n, 'loop_bytes': lb, 'trips': trips, 'fw_ns': fw, 'ok': ok, 'sim_gate': bool(gate), 'cores': cores, 'arms': arms}
        rec['rows'].append(row)
        print(s, n, trips, ok, [round(f/(n*trips), 4) for f in fw], 'cores', [hex(c) for c in cores][:16], flush=True)
        if not ok:
            sys.exit(f'oracle mismatch at {s} bytes: {w[8:10]} != {want}')
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
