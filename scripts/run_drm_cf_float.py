#!/usr/bin/env python3
"""else_fcmp / while_fcmp against their mapped integer twins, straight-line only (direct DRM).

No jumps: every structure is if / else / while exec-mask updates followed by the
matching pop_exec, so nothing can loop. Lane values x = lane & 31 and thresholds
are small non-negative integers; the float twin compares float(x) with float(t), which
orders identically. For every structure and condition pair, the per-lane final r2
and r0l snapshots must equal the integer twin's bit for bit.

Structures (A/B/C/D are distinct markers written only by active lanes):
  ifelse : mov A; if(c1); mov B; snap; else(c2); mov C; snap; pop 1
  while  : mov A; if(always); mov B; while(c1); mov C; snap; pop 1
  nested : mov A; if(c1); if(c2); mov B; snap; else(c1); mov C; snap; pop 1; mov D; snap; pop 1
"""
import itertools, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains

REPO = Path(__file__).resolve().parents[1]
CC = {'lt': 'ult', 'gt': 'ugt', 'eq': 'ueq'}     # float cc -> integer twin on non-negative ints


def body(struct_, fl, c1, c2, t1, t2):
    e = agx_loop.encode; mov = chains.mov_imm
    k = 'f' if fl else 'i'
    cc = (lambda c: c) if fl else (lambda c: CC[c])
    a1, b1 = ('r8', 'r9') if fl else ('r6', 'r7')
    a2, b2 = ('r8', 'r11') if fl else ('r6', 'r10')
    ins = [mov(12, 31), e('and r6, r1, r12'), mov(7, t1), mov(10, t2),
           e('convert u32_to_f, r8, r6, rte'), e('convert u32_to_f, r9, r7, rte'), e('convert u32_to_f, r11, r10, rte'),
           mov(13, 0xdead), mov(14, 0xdead), mov(15, 0xdead)]
    snap = lambda r: e(f'iadd r{r}, r0l, 0')
    c = lambda kind, cnd, a, b: e(f'{kind}_{k}cmp r0l, {cc(cnd)}, {a}, {b}, 1')
    if struct_ == 'ifelse':
        ins += [mov(2, 0xa), c('if', c1, a1, b1), mov(2, 0xb), snap(13), c('else', c2, a2, b2), mov(2, 0xc), snap(14), e('pop_exec r0l, 1')]
    elif struct_ == 'while':
        ins += [mov(2, 0xa), e(f'if_{k}cmp r0l, {cc("eq")}, {a1}, {a1}, 1'), mov(2, 0xb), c('while', c1, a1, b1), mov(2, 0xc), snap(13), e('pop_exec r0l, 1')]
    else:
        ins += [mov(2, 0xa), c('if', c1, a1, b1), c('if', c2, a2, b2), mov(2, 0xb), snap(13), c('else', c1, a1, b1), mov(2, 0xc), snap(14),
                e('pop_exec r0l, 1'), mov(2, 0xd), snap(15), e('pop_exec r0l, 1')]
    ins += [snap(16), mov(17, 32), e('iadd r17, r1, r17'), agx_loop.store(13, 8, 17), mov(17, 64), e('iadd r17, r1, r17'), agx_loop.store(14, 8, 17),
            mov(17, 96), e('iadd r17, r1, r17'), agx_loop.store(15, 8, 17), mov(17, 128), e('iadd r17, r1, r17'), agx_loop.store(16, 8, 17), e('wait 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '/scratch/apple-m2-playground/drm-compute/cf-float'); out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)

    def run(code):
        (out/'c.bin').write_bytes(drm.build_main(code)+bytes(16)); (out/'t.bin').write_bytes(bytes(4*160))
        try:
            r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), '32', str(out/'rb'), '1', '48', str(out/'t.bin')],
                               capture_output=True, timeout=20, env={'AGX_TABLE_OUT': str(out/'t.out'), 'PATH': '/usr/bin'})
        except subprocess.TimeoutExpired:
            sys.exit('timeout; stopping')
        if r.returncode or '"rep"' not in r.stdout.decode(): sys.exit('dispatch failed')
        w = struct.unpack('<64I', (out/'rb').read_bytes())[8:40]
        t = struct.unpack('<160I', (out/'t.out').read_bytes())
        return {'r2': list(w), 'snaps': [list(t[32*j:32*j+32]) for j in range(1, 5)]}

    rec = {'cases': []}
    bad = 0
    for st in ('ifelse', 'while', 'nested'):
        for c1, c2 in itertools.product(CC, CC):
            if st == 'while' and c2 != 'lt': continue
            for t1, t2 in ((13, 20), (0, 31)):
                ri, rf = run(body(st, False, c1, c2, t1, t2)), run(body(st, True, c1, c2, t1, t2))
                same = ri == rf
                bad += not same
                rec['cases'].append({'struct': st, 'c1': c1, 'c2': c2, 't1': t1, 't2': t2, 'same': same, 'int': ri, 'float': rf})
                print(json.dumps({'struct': st, 'c1': c1, 'c2': c2, 't': [t1, t2], 'same': same,
                                  'r2_int': ''.join('%x' % (v & 15) for v in ri['r2'])}), flush=True)
    (out/'record.json').write_text(json.dumps(rec)+'\n')
    print(json.dumps({'cases': len(rec['cases']), 'mismatches': bad}))


if __name__ == '__main__':
    main()
