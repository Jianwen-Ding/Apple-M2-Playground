#!/usr/bin/env python3
"""Instruction-cache associativity / set probe (safe: straight-line iadds, forward jmp_exec_any between blocks, Mesa's
counted-loop back edge; emulator + simulator gated, oracle-checked; one SIMD group, no clock keeper).

The loop is n blocks, each one 64-byte line starting on a line boundary: 7 x `iadd` (56 B) + `jmp_exec_any` (6 B) to the
next block S bytes later (+ 2 B wait filler). The last block holds the trip counter and the backward jump instead. Unused
bytes between blocks are `wait 0` filler (never executed). Blocks mapping to one cache set compete for its ways: with
S = (sets x 64) every block maps to the same set, and the loop stays in cache only while n <= ways.
  probe_icache_assoc.py --stride S --blocks 1,2,4,... [--repeats 16] [--result FILE]
"""
import argparse, json, statistics as st, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
import run_agx_timestamps as chains

REPO = Path(__file__).resolve().parents[1]
REGS = (5, 6, 7, 8)
WAIT = agx_loop.encode('wait 0')


def body(stride, nblocks, trips, tag=True, lines=1, dual=False, jkind='any'):
    e, mov = agx_loop.encode, chains.mov_imm
    head = mov(3, 0)+mov(4, trips)+b''.join(mov(r, 0) for r in REGS)
    head += e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    # align the first block to a 64-byte line: control prefix site is at code offset 22
    lead = (64 - (22 + len(head)) % 64) % 64
    assert lead % 2 == 0
    head += WAIT*(lead//2)
    def chain(base, code):
        starts = [base + i*stride for i in range(nblocks)]
        n_iadd = 0
        for i, s_ in enumerate(starts):
            code += WAIT*((s_ - len(code))//2)                 # filler up to the block start
            assert len(code) == s_
            if jkind in ('taken6', 'untaken6', 'nojump'):     # exact 64-byte line, no filler: 6 iadd + mov_imm + and + 6-byte slot
                k_n = 6
                blk = b''.join(e(f'iadd r{REGS[(i*k_n+k) % 4]}, r{REGS[(i*k_n+k) % 4]}, 1') for k in range(k_n))
                blk += e('mov_imm r9l, 1') + e('and r9, r9, r9')
            else:
                k_n = (64*lines - 8) // 8                        # iadds per block: the block plus its jump fits in `lines` lines
                blk = b''.join(e(f'iadd r{REGS[(i*k_n+k) % 4]}, r{REGS[(i*k_n+k) % 4]}, 1') for k in range(k_n))
            n_iadd += k_n
            if i < nblocks-1:
                off = starts[i+1] - (s_ + len(blk))
                if jkind == 'any':                     # taken (lanes active) to the next block
                    blk += e(f'jmp_exec_any pc+{off}', f'jmp_exec_any pc+{off}')
                elif jkind == 'none':                  # never taken (lanes active): falls through the filler
                    blk += e(f'jmp_exec_none pc+{off}', f'jmp_exec_none pc+{off}')
                elif jkind in ('next', 'taken6'):       # taken, to the instruction right after the jump
                    blk += e('jmp_exec_any pc+6', 'jmp_exec_any pc+6')
                elif jkind == 'untaken6':               # never taken (lanes active), same bytes otherwise
                    blk += e('jmp_exec_none pc+6', 'jmp_exec_none pc+6')
                else:                                   # 'nojump': a 6-byte ALU op in the jump's place
                    blk += e('and r9, r9, r9')
            else:
                blk += e('iadd r3, 1, r3.sx') + e('while_icmp r0l, ult, r3, r4, 1')
                back = s_ + len(blk) - starts[0]
                blk += e(f'jmp_exec_any pc-{back}', f'jmp_exec_any pc-{back}')
            code += blk
        return n_iadd
    PUSH = e('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    code = bytearray()
    if not dual:
        n_iadd = chain(0, code)
    else:
        # Mesa's structured if/else: lanes with (r1 & 32) == 0 run chain A, the others chain B; each arm wraps its
        # counted loop in its own push_exec / pop_exec (the head's push is undone first).
        code += e('pop_exec r0l, 1') + e('and r9, r1, 32') + e('if_icmp r0l, ueq, r9, 0, 1')
        jA = len(code); code += bytes(6)
        code += PUSH
        code += WAIT*(((64 - (22 + len(head) + len(code)) % 64) % 64)//2)
        n_iadd = chain(len(code), code)
        code += e('pop_exec r0l, 1')
        armA_end = len(code)
        code += e('else_icmp r0l, nueq, r9, 0, 1')
        jB = len(code); code += bytes(6)
        code += PUSH
        code += WAIT*(((64 - (22 + len(head) + len(code)) % 64) % 64)//2)
        chain(len(code), code)
        code += e('pop_exec r0l, 1')
        join = len(code)
        code += e('pop_exec r0l, 1')                          # closes the if/else
        code += PUSH                                          # re-balance: the common tail pops once
        def patch(at, txt):
            bb = e(txt, txt); assert len(bb) == 6; code[at:at+6] = bb
        patch(jA, f'jmp_exec_none pc+{armA_end - jA}')
        patch(jB, f'jmp_exec_none pc+{join - jB}')
    tail = e('pop_exec r0l, 1') + e('iadd r2, r5, r6') + e('iadd r2, r2, r7') + e('iadd r2, r2, r8')
    if tag:
        tail += e('get_sr r10, sr20', 'get_sr r10, sr20 (core_index)') + mov(11, 1 << 24) + e('imadd r2, r10, r11, r2')
    return head+bytes(code)+tail, n_iadd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stride', type=int, required=True)
    p.add_argument('--blocks', default='1,2,3,4,5,6,8,12,16')
    p.add_argument('--lines', type=int, default=1, help='64-byte lines per block (sequential code after each jump)')
    p.add_argument('--jkind', default='any', choices=['any', 'none', 'next', 'taken6', 'untaken6', 'nojump'], help='forward jumps: taken to the next block, never taken, or taken to the next instruction')
    p.add_argument('--dual', action='store_true', help='two separate jump chains; the second SIMD group of a 64-lane workgroup runs chain B')
    p.add_argument('--local', type=int, default=32)
    p.add_argument('--trips', type=int, default=0, help='0: ~2M iadds per run')
    p.add_argument('--repeats', type=int, default=16)
    p.add_argument('--gate-only', action='store_true')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/icache-assoc'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    assert a.stride % 64 == 0 and a.stride >= 64
    blocks = [int(x) for x in a.blocks.split(',')]
    import sim_gate
    for nb in blocks:                                           # emulator gate (2 trips) on the untagged program
        b, n = body(a.stride, nb, 2, tag=False, lines=a.lines, dual=a.dual, jkind=a.jkind)
        stt = agx_loop.emulate(b, 32, max_steps=50*n*2+5000)
        if stt['r2'] != [(n*2) & 0xffffffff]*32:
            sys.exit(f'emulator gate failed: blocks {nb}')
    print('emulator gate passed', flush=True)
    if a.gate_only:
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'stride': a.stride, 'lines': a.lines, 'jkind': a.jkind, 'dual': a.dual, 'local': a.local, 'rows': []}
    for nb in blocks:
        trips = a.trips or max(2, 2_000_000 // (7*a.lines*nb))
        b, n = body(a.stride, nb, trips, lines=a.lines, dual=a.dual, jkind=a.jkind)
        sim_gate.require(drm.build_main(body(a.stride, nb, 3, tag=False, lines=a.lines, dual=a.dual, jkind=a.jkind)[0]), a.local, (n*3) & 0xffffffff, regs=24)
        (out/'c.bin').write_bytes(drm.build_main(b)+bytes(16))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(a.local), str(out/'rb'), str(a.repeats), '24'],
                           capture_output=True, timeout=300, env={'PATH': '/usr/bin', 'AGX_LOCAL_X': str(a.local)})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != a.repeats:
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        nw = (a.local+31)//32*32+32
        w = list(struct.unpack('<'+'I'*nw, (out/'rb').read_bytes()[:4*nw]))
        ok = [x & 0xffffff for x in w[8:8+a.local]] == [(n*trips) & 0xffffff]*a.local
        fw = [x['fw_ts'][1]-x['fw_ts'][0] for x in smp]
        per_block = st.median(fw[len(fw)//2:])/(nb*trips)
        rec['rows'].append({'blocks': nb, 'iadds': n, 'trips': trips, 'fw_ns': fw, 'ok': ok, 'core': w[8] >> 24, 'ns_per_block': per_block})
        print(a.stride, nb, ok, round(per_block, 2), round(st.median(fw[len(fw)//2:])/(n*trips), 3), hex(w[8] >> 24), flush=True)
        if not ok:
            sys.exit('oracle mismatch')
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
