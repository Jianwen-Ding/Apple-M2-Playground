#!/usr/bin/env python3
"""Software binary32 fma (softfp32.py) on AGX: bit-exactness with subnormals and rn/rz/rm/rp, and cost.

Each lane computes r = fma(a, b, c) on operands from the table and stores r. Operands: the 30 x 30 x 10 edge cube
(signed zeros, smallest/largest subnormals, min normal and neighbours, 1 and neighbours, max finite, inf, NaN,
binade edges) plus random triples with exponents biased to the subnormal boundary and near-cancelling addends.
Expected results: softfp32.ref_fma32 (exact Fractions). The 'hw' op is one native fmadd32 (round to nearest, flushes
subnormals): it is used to cross-check the reference where the hardware is known exact (normal inputs, normal result).
Offline mode replays the program in the Rust simulator (the safety gate); hardware mode runs it on the GPU.
  run_drm_softfp32.py offline|hardware --op soft|hw|hybrid [--round rn|rz|rm|rp] [--chain K --lanes N for cost]
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
import softfp32 as S

REPO = Path(__file__).resolve().parents[1]
EDGE = [0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x807fffff, 0x400000, 0x800000, 0x80800000, 0x800001, 0x00ffffff, 0x3f800000,
        0xbf800000, 0x3f800001, 0x3f7fffff, 0x7f7fffff, 0xff7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001, 0x34000000,
        0x33800000, 0x0d800000, 0x1f800000, 0x5f800000, 0x40000000, 0x3effffff, 0x00000003, 0x26000000]


def dataset(nrand, seed=1):
    rng = random.Random(seed)
    t = [(x, y, z) for x in EDGE for y in EDGE for z in EDGE[::3]]

    def rf():
        e = rng.choice([0, 0, 1, 2, 3, rng.randint(0, 254), rng.randint(100, 140), rng.randint(40, 90)])
        return (rng.getrandbits(1) << 31) | (e << 23) | rng.getrandbits(23)
    for _ in range(nrand):
        a, b = rf(), rf()
        c = rf()
        va, vb = S.f32val(a), S.f32val(b)
        if rng.random() < 0.35 and not isinstance(va, (str, tuple)) and not isinstance(vb, (str, tuple)) and va*vb != 0:
            c = (S.round32(-va*vb, 'rn', 0) + rng.randint(-3, 3)) & 0xffffffff     # near-cancelling addend
        t.append((a, b, c))
    while len(t) % 32:
        t.append((0x3f800000,)*3)
    return t


def hybrid_lines(chain):
    """Non-ftz round-to-nearest fma: native fmadd32, then the soft fma only on lanes where needs_ieee() is set
    (structured if: if_icmp / jmp_exec_none / pop_exec, as Mesa emits). x lives in r12; returns (lines, used)."""
    L = ['iadd r12, r8, 0']
    used = 14
    for _ in range(chain):
        L.append('fmadd32 r13, r12, r9, r10')
        P = S.Prog()
        a, b, c, r = P.input('a'), P.input('b'), P.input('c'), P.input('r')
        nd = S.needs_ieee(P, a, b, c, r)
        chk, loc, u1 = S.emit(P, {'a': 12, 'b': 9, 'c': 10, 'r': 13}, [nd], first=14)
        L += chk
        L.append(f'if_icmp r0l, nueq, r{loc[nd.id]}, 0, 1')
        P = S.Prog()
        a, b, c = P.input('a'), P.input('b'), P.input('c')
        x = S.ffma32(P, a, b, c, 'rn')
        soft, loc2, u2 = S.emit(P, {'a': 12, 'b': 9, 'c': 10}, [x], first=14)
        soft = soft + [f'iadd r13, r{loc2[x.id]}, 0']
        L.append(('JMP', soft))
        L.append('pop_exec r0l, 1')
        L.append('iadd r12, r13, 0')
        used = max(used, u1, u2)
    return L, 12, used


CHECK9 = [   # needs-IEEE test in 9 ops; r30 = 0xffffffff and r31 = 0x00fffffe are hoisted constants. t = 2|x| - 1
    'iadd r16, r30, r12, lsl 1', 'iadd r17, r30, r9, lsl 1', 'iadd r18, r30, r10, lsl 1',
    'icmpsel ult, r19, r16, r17, r16, r17', 'icmpsel ugt, r20, r16, r17, r16, r17', 'icmpsel ult, r19, r19, r18, r19, r18',
    'iadd r21, r13, r13', 'icmpsel ueq, r21, r21, 0, r20, r30', 'icmpsel ult, r21, r19, r31, 0, r21']


def probe_lines(chain, kind):
    """Cost decomposition of the hybrid fast path (all-normal data only): 'nocf' = fma + CHECK9 (no control flow),
    'cfonly' = fma + if_icmp/jmp_exec_none(1-instruction block)/pop_exec (no check), 'fma2' = fma + one iadd copy."""
    L = ['iadd r12, r8, 0', ('IMM', 30, 0xffffffff), ('IMM', 31, 0x00fffffe)]
    for _ in range(chain):
        L.append('fmadd32 r13, r12, r9, r10')
        if kind == 'nocf':
            L += CHECK9
        elif kind == 'cfonly':
            L += ['if_icmp r0l, nueq, r13, r30, 1', ('JMP', ['iadd r13, r13, 0']), 'pop_exec r0l, 1']
        elif kind == 'cftaken':           # no lane passes (r13 is never 0xffffffff): jmp_exec_none is taken
            L += ['if_icmp r0l, ueq, r13, r30, 1', ('JMP', ['iadd r13, r13, 0']), 'pop_exec r0l, 1']
        elif kind == 'cfnojmp':           # the same if / pop with no jump over the (executed-by-none) block
            L += ['if_icmp r0l, ueq, r13, r30, 1', 'iadd r13, r13, 0', 'pop_exec r0l, 1']
        L.append('iadd r12, r13, 0')
    return L, 12, 32


def hybrid3_lines(chain):
    """Out-of-line slow path: the common case falls through an untaken jmp_exec_any; flagged groups jump to a block
    after the main body and jump back. Lines may hold ('LABEL', name) and ('JANY', name) (resolved by build)."""
    L = ['iadd r12, r8, 0', ('IMM', 30, 0xffffffff), ('IMM', 31, 0x00fffffe)]
    ool = []
    used = 32
    for i in range(chain):
        L.append('fmadd32 r13, r12, r9, r10')
        L += CHECK9
        L += ['if_icmp r0l, nueq, r21, r30, 1', ('JANY', f'ool{i}'), ('LABEL', f'ret{i}'), 'pop_exec r0l, 1', 'iadd r12, r13, 0']
        P = S.Prog()
        a, b, c = P.input('a'), P.input('b'), P.input('c')
        x = S.ffma32(P, a, b, c, 'rn')
        soft, loc2, u2 = S.emit(P, {'a': 12, 'b': 9, 'c': 10}, [x], first=32)
        ool += [('LABEL', f'ool{i}')] + soft + [f'iadd r13, r{loc2[x.id]}, 0', ('JANY', f'ret{i}')]
        used = max(used, u2)
    return L + [('JANY', 'tail')] + ool + [('LABEL', 'tail')], 12, used


def hybrid2_lines(chain, stub=False):
    """As hybrid_lines, with the 9-op CHECK9 folded into if_icmp (nueq against 0xffffffff) and hoisted constants.
    stub=True replaces the soft block by one instruction (a fetch-cost probe: exact only when no lane is flagged)."""
    L = ['iadd r12, r8, 0', ('IMM', 30, 0xffffffff), ('IMM', 31, 0x00fffffe)]
    used = 32
    for _ in range(chain):
        L.append('fmadd32 r13, r12, r9, r10')
        L += CHECK9
        L.append('if_icmp r0l, nueq, r21, r30, 1')
        P = S.Prog()
        a, b, c = P.input('a'), P.input('b'), P.input('c')
        x = S.ffma32(P, a, b, c, 'rn')
        soft, loc2, u2 = S.emit(P, {'a': 12, 'b': 9, 'c': 10}, [x], first=32)
        L.append(('JMP', ['iadd r13, r13, 0'] if stub else soft + [f'iadd r13, r{loc2[x.id]}, 0']))
        L.append('pop_exec r0l, 1')
        L.append('iadd r12, r13, 0')
        used = max(used, u2)
    return L, 12, used


def cost_dataset(n, kind, seed=2):
    """Cost data: x = fma(x, b, c) stays normal (b in [0.999, 1.001], c in [-1, 1], x0 in [1, 2]); 'sparse' gives lane 0
    of every SIMD group a subnormal c (that group's lanes all take the soft path), 'dense' gives every lane one."""
    rng = random.Random(seed)
    f = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
    t = [(f(rng.uniform(1, 2)), f(rng.uniform(0.999, 1.001)), f(rng.uniform(-1, 1))) for _ in range(n)]
    if kind in ('sparse', 'dense'):
        for i in range(0, n, 32 if kind == 'sparse' else 1):
            t[i] = (t[i][0], t[i][1], rng.randint(1, 0x7fffff) | (rng.getrandbits(1) << 31))
    return t


def build(op, n, chain=1, mode='rn'):
    if op == 'hw':
        lines = ['fmadd32 r8, r8, r9, r10']*chain
        rr, used = 8, 12
    elif op == 'hybrid':
        lines, rr, used = hybrid_lines(chain)
    elif op == 'hybrid3':
        lines, rr, used = hybrid3_lines(chain)
    elif op in ('nocf', 'cfonly', 'fma2', 'cftaken', 'cfnojmp', 'hybrid3'):
        lines, rr, used = probe_lines(chain, op)
    elif op in ('hybrid2', 'stub'):
        lines, rr, used = hybrid2_lines(chain, op == 'stub')
    else:
        P = S.Prog()
        a, b, c = P.input('a'), P.input('b'), P.input('c')
        x = a
        for _ in range(chain):                      # x = fma(x, b, c): a dependent chain
            x = S.ffma32(P, x, b, c, mode)
        lines, loc, used = S.emit(P, {'a': 8, 'b': 9, 'c': 10}, [x], first=11)
        rr = loc[x.id]
    lines0 = list(lines)
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [load(8, 1, True), mov(6, n), e('iadd r7, r1, r6'), load(9, 7, True), mov(6, 2*n), e('iadd r7, r1, r6'), load(10, 7, True), e('wait 0')]
    body = []
    if any(isinstance(l, tuple) and l[0] == 'LABEL' for l in lines):     # two-pass label resolution (jumps are 6 bytes)
        pos, at, items = {}, 0, []
        for l in lines:
            if isinstance(l, tuple) and l[0] == 'LABEL':
                pos[l[1]] = at
            elif isinstance(l, tuple) and l[0] == 'JANY':
                items.append(('J', l[1], at)); at += 6
            else:
                bts = mov(l[1], l[2]) if isinstance(l, tuple) else e(l)
                items.append(('B', bts, at)); at += len(bts)
        for kind, v, where in items:
            if kind == 'B':
                body.append(v)
            else:
                off = pos[v] - where
                txt = f'jmp_exec_any pc+{off}' if off >= 0 else f'jmp_exec_any pc-{-off}'
                body.append(e(txt, txt))
        lines = []
    for l in lines:
        if isinstance(l, tuple) and l[0] == 'IMM':
            body.append(mov(l[1], l[2]))
        elif isinstance(l, tuple):                  # ('JMP', then-lines): jmp_exec_none over the then block
            then = b''.join(e(x) for x in l[1])
            jt = 6+len(then)
            body += [e(f'jmp_exec_none pc+{jt}', f'jmp_exec_none pc+{jt}'), then]
        else:
            body.append(e(l))
    tail = [mov(6, 3*n), e('iadd r7, r1, r6'), agx_loop.store(rr, 8, 7), e('wait 0'), mov(2, 0)]
    allb = ins+body+tail
    DA.decode_lengths(b''.join(allb), [len(i) for i in allb]) if op not in ('hybrid', 'hybrid2', 'stub', 'nocf', 'cfonly', 'fma2', 'cftaken', 'cfnojmp', 'hybrid3') else None
    ninstr = sum(0 if isinstance(l, tuple) and l[0] == 'LABEL' else 1 if isinstance(l, tuple) and l[0] in ('IMM', 'JANY') else len(l[1])+1 if isinstance(l, tuple) else 1 for l in lines0)
    return b''.join(allb), ninstr, used


def table(tuples):
    n = len(tuples)
    return [t[0] for t in tuples]+[t[1] for t in tuples]+[t[2] for t in tuples]+[0xcdcdcdcd]*n


def expected(tuples, mode, chain=1):
    out = []
    for a, b, c in tuples:
        x = a
        for _ in range(chain):
            x = S.ref_fma32(x, b, c, mode)
        out.append(x)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--op', default='soft', choices=['soft', 'hw', 'hybrid', 'hybrid2', 'stub', 'nocf', 'cfonly', 'fma2', 'cftaken', 'cfnojmp', 'hybrid3'])
    p.add_argument('--round', default='rn', choices=['rn', 'rz', 'rm', 'rp'])
    p.add_argument('--random', type=int, default=12000)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--chain', type=int, default=1)
    p.add_argument('--lanes', type=int, default=0, help='repeat the dataset to this many lanes (cost runs); the check covers the first block')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/softfp32'))
    p.add_argument('--result', type=Path)
    p.add_argument('--data', default='edge', choices=['edge', 'normal', 'sparse', 'dense'],
                   help='edge: the exactness dataset; others: cost data (--lanes lanes, the first --check lanes are verified)')
    p.add_argument('--check', type=int, default=1024)
    a = p.parse_args()
    if a.data == 'edge':
        tuples = dataset(a.random)
        base = len(tuples)
    else:
        tuples = cost_dataset(a.lanes, a.data)
        base = min(a.check, len(tuples))
    if a.data == 'edge' and a.lanes > base:
        tuples = (tuples*(a.lanes//base+1))[:a.lanes//32*32]
    n = len(tuples)
    prog, ninstr, used = build(a.op, n, a.chain, a.round)
    code = drm.build_main(prog)
    tb = table(tuples)
    regs = 2*used+8
    exp = expected(tuples[:base], 'rn' if a.op in ('hybrid', 'hybrid2', 'stub', 'nocf', 'cfonly', 'fma2', 'cftaken', 'cfnojmp', 'hybrid3') else a.round, a.chain) if a.op != 'hw' else None
    print(f'{a.op} {a.round}: {n} lanes, {ninstr} instructions, registers up to r{used-1}', flush=True)
    rec = {'op': a.op, 'data': a.data, 'round': a.round, 'lanes': n, 'checked_lanes': base, 'instructions': ninstr, 'registers': used, 'chain': a.chain, 'runs': []}
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        o, t = cov.simulate(code, n, 32, regs, 0, tb)
        got = list(t[3*n:3*n+base])
        bad = [i for i in range(base) if exp and got[i] != exp[i]]
        print('simulator replay:', base, 'lanes checked,', len(bad), 'differ from the exact reference')
        rec['sim_out'] = got
        if a.result:
            a.result.write_text(json.dumps(rec)+'\n')
        return 1 if bad else 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    for rep in range(a.repeats):
        (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', str(regs), str(out/'t.bin')],
                           capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        t = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
        got = list(t[3*n:3*n+base])
        bad = [i for i in range(base) if exp and got[i] != exp[i]]
        run = {'rep': rep, 'bad': len(bad), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0],
               'first_bad': [[list(tuples[i]), got[i], exp[i]] for i in bad[:5]]}
        if rep == 0:
            rec['out'] = got
        rec['runs'].append(run)
        print('hardware run', rep, 'lanes differing:', len(bad), 'fw_ns', run['fw_ns'], flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
