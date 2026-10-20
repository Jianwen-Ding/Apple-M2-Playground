#!/usr/bin/env python3
"""IEEE rcp.rn.f32 on AGX: y0 = rcp(b); y1 = fma(fma(-b, y0, 1), y0, y0) (3 native ops), on the GPU for every f32 in [1, 2)
(2^23 inputs: every mantissa; correct rounding of 1/b depends only on it) and over all 256 exponents x 32,768 mantissas
of both signs, against an exact integer reference. 'raw' is the bare rcp (rcp.approx). Offline: Rust simulator gate.
  run_drm_frcp32.py offline|hardware --seq raw|newton [--data binade|sweep] [--result FILE]
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm
import run_agx_timestamps as chains
from run_drm_cpu_clock import load

REPO = Path(__file__).resolve().parents[1]
CHUNK = 1 << 20
SEQ = {'raw': ['rcp r13, r8'], 'newton': ['rcp r12, r8', 'fmadd32 r13, r8.neg, r12, 1.0', 'fmadd32 r13, r13, r12, r12']}


def exact_rcp(x):
    """Correctly rounded (rn) 1/x bits for normal x whose reciprocal is normal; None otherwise (not compared)."""
    ex, mn, sg = (x >> 23) & 0xff, x & 0x7fffff, x & 0x80000000
    if ex in (0, 255):
        return None
    B = mn | 0x800000                                   # x = B * 2^(ex-150); 1/x = 2^(150-ex) / B
    q, r = divmod(1 << 47, B)                           # 2^47 / B in (2^23, 2^24]
    q += 2*r > B or (2*r == B and q & 1)
    e = 127 + (127 - ex) - 1                            # 1/x = (q * 2^-24) * 2^(127-ex+1) ... exponent of q*2^-24 in [0.5, 1]
    if q >> 24:                                         # exactly 1.0 (B = 2^23)
        q >>= 1; e += 1
    if not 1 <= e <= 254:
        return None
    return sg | (e << 23) | (q & 0x7fffff)


def inputs(data, c):
    if data == 'binade':
        return [0x3f800000 + i for i in range(c*CHUNK, min((c+1)*CHUNK, 1 << 23))]
    xs = []                                             # sweep chunk c: exponents 16c..16c+15, 32,768 mantissas, both signs
    for ex in range(16*c, 16*c+16):
        off = (ex*41) % 256
        xs += [(s << 31) | (ex << 23) | (j*256 + off) for s in (0, 1) for j in range(32768)]
    return xs


def build(seq, n):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [load(8, 1, True), e('wait 0')] + [e(l) for l in SEQ[seq]]
    ins += [mov(6, n), e('iadd r7, r1, r6'), agx_loop.store(13, 8, 7), e('wait 0'), mov(2, 0)]
    return b''.join(ins)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--seq', default='newton', choices=sorted(SEQ))
    p.add_argument('--data', default='binade', choices=['binade', 'sweep'])
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/frcp32'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    nchunks = 8 if a.data == 'binade' else 16
    rec = {'seq': a.seq, 'data': a.data, 'compared': 0, 'skipped': 0, 'wrong': 0, 'hist': {}, 'wrong_exponents': {}, 'first_wrong': []}

    def tally(xs, outs):
        for x, g in zip(xs, outs):
            w = exact_rcp(x)
            if w is None:
                rec['skipped'] += 1; continue
            rec['compared'] += 1
            if g != w:
                rec['wrong'] += 1
                k = str(g-w); rec['hist'][k] = rec['hist'].get(k, 0)+1
                k = str((x >> 23) & 0xff); rec['wrong_exponents'][k] = rec['wrong_exponents'].get(k, 0)+1
                if len(rec['first_wrong']) < 10:
                    rec['first_wrong'].append([x, g, w])
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        xs = [x for c in range(nchunks) for x in inputs(a.data, c)[::64]][:65536]
        n = len(xs)
        o, t = cov.simulate(drm.build_main(build(a.seq, n)), n, 32, 40, 0, xs+[0xcdcdcdcd]*n)
        tally(xs, t[n:2*n])
        print(f"simulator {a.seq} {a.data}: compared {rec['compared']}, wrong {rec['wrong']}, hist {rec['hist']}")
        return 0
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    for c in range(nchunks):
        xs = inputs(a.data, c); n = len(xs)
        (out/'c.bin').write_bytes(drm.build_main(build(a.seq, n))+bytes(16))
        (out/'t.bin').write_bytes(struct.pack(f'<{2*n}I', *xs, *([0xcdcdcdcd]*n)))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '40', str(out/'t.bin')],
                           capture_output=True, timeout=120, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out')})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        t = struct.unpack(f'<{2*n}I', (out/'t.out').read_bytes())
        tally(xs, t[n:])
    print(f"hardware {a.seq} {a.data}: compared {rec['compared']:,}, skipped {rec['skipped']:,}, wrong {rec['wrong']:,}, hist {rec['hist']}, wrong exponents {sorted(map(int, rec['wrong_exponents']))[:8]}")
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
