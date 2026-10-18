#!/usr/bin/env python3
"""fmadd lane-offset (10-byte form) with inactive source lanes (safe-07 open question). Direct DRM, straight-line, no loops.

Per SIMD group: A[lane] = float(lane + 1) is written to r9 before the exec mask changes; the mask comes from a per-lane table word
(`if_icmp r0l, ugt, mask, 0, 1`: active when the word is nonzero); an active lane then runs `fmadd32 r5, r9, r7, r8` in its 10-byte
lane form with offset k (bits 75-79; default 16-lane groups, no other gap bits) with B = 1.0, C = 0.0, so D = A[lane - k] (0 when the
source falls below the half). `pop_exec` restores the mask and r5 is stored for every lane (inactive lanes keep a sentinel).
For every active lane whose source lane is inactive the result is classified: reads A[src] (the register file regardless of the mask),
reads 0, or other. `after` = the instruction following the fmadd: `alu` (an iadd) or `wait`.
  run_drm_fmadd_mask.py offline|hardware
"""
import argparse, json, random, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
SENT = 0xdeadbeef
KS = [1, 2, 4, 8, 15]
MASKS = ['random', 'even', 'odd', 'low16', 'high16', 'not0', 'quads01']


def fmadd_lane(k):
    b = bytearray(agx_loop.encode('fmadd32 r5, r9, r7, r8'))
    b += bytes(8-len(b)); b[1] |= 0x80      # force the 8-byte form (bit 15)
    b[6] |= 1 << (53-48)                    # bit 53: 10-byte form
    return bytes(b)+(k << 11).to_bytes(2, 'little')


def body(n, k, after):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(12, 31), e('and r13, r1, r12'), e('iadd r14, r13, 1'), e('convert u32_to_f, r9, r14, rte'),   # A = float(lane + 1)
           mov(7, 0x3f800000), mov(8, 0), mov(5, SENT), load(16, 1, True), e('wait 0'),
           e('if_icmp r0l, ugt, r16, 0, 1'), fmadd_lane(k)]
    ins += [e('iadd r20, r20, 1')] if after == 'alu' else [e('wait 0')]
    ins += [e('pop_exec r0l, 1'), e('wait 0'), mov(6, 2*n), e('iadd r15, r1, r6'), agx_loop.store(5, 8, 15), e('wait 0'), mov(2, 0)]
    # applegpu cannot decode the 10-byte lane form as such; walk the program with the lane form replaced by an 8-byte one + 2 skipped bytes
    parts = [i if len(i) != 10 else i[:8] for i in ins]
    DA.decode_lengths(b''.join(parts), [len(p) for p in parts])
    return b''.join(ins)


def masks(groups, seed):
    rng = random.Random(seed)
    out = []
    for g in range(groups):
        kind = MASKS[g % len(MASKS)]
        if kind == 'random': m = [rng.randint(0, 1) for _ in range(32)]
        elif kind == 'even': m = [1-(l & 1) for l in range(32)]
        elif kind == 'odd': m = [l & 1 for l in range(32)]
        elif kind == 'low16': m = [int(l < 16) for l in range(32)]
        elif kind == 'high16': m = [int(l >= 16) for l in range(32)]
        elif kind == 'not0': m = [int(l != 0) for l in range(32)]
        else: m = [int(l % 4 in (0, 1)) for l in range(32)]
        out += m
    return out


def classify(mask, d, k):
    """Per group: counts of active lanes whose source is inactive -> reads register / zero / other; plus checks of the rest."""
    cnt = {'src_inactive_reads_register': 0, 'src_inactive_reads_zero': 0, 'src_inactive_other': 0, 'src_active_ok': 0, 'src_active_bad': 0,
           'below_half_zero': 0, 'below_half_bad_lo': 0, 'below_half_bad_hi': 0, 'inactive_untouched': 0, 'inactive_changed': 0}
    f = lambda x: struct.unpack('<f', struct.pack('<I', x))[0]
    for lane in range(32):
        if not mask[lane]:
            cnt['inactive_untouched' if d[lane] == SENT else 'inactive_changed'] += 1
            continue
        half = lane & ~15
        s = lane-k
        if s < half:
            cnt['below_half_zero' if d[lane] == 0 else 'below_half_bad_lo' if lane < 16 else 'below_half_bad_hi'] += 1
        elif mask[s]:
            cnt['src_active_ok' if f(d[lane]) == float(s+1) else 'src_active_bad'] += 1
        else:
            v = f(d[lane])
            key = 'src_inactive_reads_register' if v == float(s+1) else 'src_inactive_reads_zero' if d[lane] == 0 else 'src_inactive_other'
            cnt[key] += 1
    return cnt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--groups', type=int, default=210)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fmadd-mask'))
    a = p.parse_args()
    n = a.groups*32
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        mk = [1]*n    # the simulator models only the fully active case (inactive source lanes are refused)
        for k in KS:
            o, t = cov.simulate(drm.build_main(body(n, k, 'alu')), n, 32, 64, 0, mk+[0]*(2*n))
            d = t[2*n:3*n]
            bad = sum(classify([1]*32, d[32*g:32*g+32], k)['src_active_bad'] + classify([1]*32, d[32*g:32*g+32], k)['below_half_bad_lo'] + classify([1]*32, d[32*g:32*g+32], k)['below_half_bad_hi'] for g in range(a.groups))
            print(f'simulator, all lanes active, k={k}: groups with a wrong lane read: {bad}')
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'groups': a.groups, 'results': []}
    for rep in range(a.repeats):
        mk = masks(a.groups, 40+rep)
        for k in KS:
            for after in ('alu', 'wait'):
                code = drm.build_main(body(n, k, after))
                words = 3*n
                (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{words}I', *(mk+[0]*(2*n))))
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '64', str(out/'t.bin')],
                                   capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
                smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                    sys.exit(f'dispatch failed k={k}: '+r.stdout.decode()[-300:])
                t = struct.unpack(f'<{words}I', (out/'t.out').read_bytes())
                d = t[2*n:3*n]
                tot = {}
                by_mask = {m: {} for m in MASKS}
                for g in range(a.groups):
                    c = classify(mk[32*g:32*g+32], d[32*g:32*g+32], k)
                    for key, v in c.items():
                        tot[key] = tot.get(key, 0)+v
                        by_mask[MASKS[g % len(MASKS)]][key] = by_mask[MASKS[g % len(MASKS)]].get(key, 0)+v
                res = {'rep': rep, 'k': k, 'after': after, 'totals': tot, 'by_mask': by_mask}
                rec['results'].append(res)
                print(json.dumps({'rep': rep, 'k': k, 'after': after, **tot}), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
