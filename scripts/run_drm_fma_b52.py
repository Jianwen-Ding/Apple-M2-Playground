#!/usr/bin/env python3
"""Bit 52 of the 8-byte fmadd32 over every triple of 24 special values (safe-07 open question). Direct DRM, straight-line, no loops.

The earlier finding fitted a rule over 31 float triples: B = 1.0 -> A; else A = 1.0 -> 1.0; else C (a zero C takes the sign of A). This
runs all 24^3 = 13,824 triples (+-0, the smallest and largest subnormals, the smallest normal, +-0.5, +-1, +-2, +-3.5, the largest finite,
+-inf, three NaNs) through `fmadd32_b52 r14, r6, r7, r8` (the exact bit pattern that ran cleanly: bit 52, 8 bytes) with A, B, C from the
table, and records every result word. The analysis (verify_fma_b52.py) classifies each result against A, B, C, 1.0, the fused fma and a
canonical NaN and fits a rule.
  run_drm_fma_b52.py offline|hardware
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
SIM = Path(__file__).resolve().parents[2]/'AGX-Performance-Simulator/scripts'
sys.path.append(str(SIM))
import run_drm_compute as drm
import record_suite as RS

REPO = Path(__file__).resolve().parents[1]
VALS = [0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007fffff, 0x807fffff, 0x00800000, 0x80800000, 0x3f000000, 0xbf000000,
        0x3f800000, 0xbf800000, 0x40000000, 0xc0000000, 0x40600000, 0xc0600000, 0x7f7fffff, 0xff7fffff, 0x7f800000, 0xff800000,
        0x7fc00000, 0xffc00000, 0x7f800001, 0x3fc00000]
assert len(VALS) == 24
TEXT = 'fmadd32_b52 r14, r6, r7, r8'     # assembled by the Rust assembler; applegpu does not know the form, so the bytes are patched below


def instr():
    b = bytearray(RS.e('fmadd32 r14, r6, r7, r8'))
    b += bytes(8-len(b)); b[1] |= 0x80          # 8-byte form (bit 15)
    b[6] |= 1 << (52-48)                        # bit 52
    return bytes(b)
N, WG = 24**3, 256
# second set: integers (odd / even, small and at the 2^23 / 2^24 boundary) and near-integers as B, signs and specials as A, four C values
F = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
VALS2_A = [0x00000000, 0x80000000, 0x80000001, 0x80800000, 0xbf000000, 0xbf800000, 0xc0000000, 0xc0600000, 0xff7fffff, 0xff800000,
           0x3f000000, 0x3f800000, 0x40000000, 0x7f800000, 0x7fc00000, 0xffc00000]
VALS2_B = [F(x) for x in (3.0, -3.0, 5.0, 4.0, -4.0, 7.0, 2.0**23+1, 2.0**23+2, 2.0**24, 2.0**24+2, 1.0000001, 0.99999994, 2.5, -2.5, 3.0000002, -7.0)]
VALS2_C = [0x3f000000, 0xc0000000, 0x00000000, 0x7fc00000]


def triples(second=False):
    if second:
        return [(a, b, c) for a in VALS2_A for b in VALS2_B for c in VALS2_C]
    return [(a, b, c) for a in VALS for b in VALS for c in VALS]


def program(second=False):
    n = len(triples(second))
    n_pad = (n+31)//32*32
    return RS.alu_body(instr(), n_pad), n_pad


def table(n_pad, second=False):
    t = []
    ts = triples(second)
    for i in range(n_pad):
        a, b, c = ts[i] if i < len(ts) else ts[0]
        t += [a, b, c, 0, 0, 0, 0, 0]
    return t+[0]*(2*n_pad)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--set', type=int, default=1, choices=[1, 2], help='1: 24^3 special triples; 2: integers / near-integers as B')
    p.add_argument('--result', type=Path)
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/fma-b52'))
    a = p.parse_args()
    second = a.set == 2
    body, n = program(second)
    code = drm.build_main(body)
    tb = table(n, second)
    NN = len(triples(second))
    asm = subprocess.run([str(SIM.parent/'rust/target/release/agx_asm')], input=TEXT+'\n', capture_output=True, text=True).stdout.split()[0]
    assert asm == instr().hex() and (int.from_bytes(instr(), 'little') >> 52) & 1 == 1 and len(instr()) == 8, (asm, instr().hex())
    if a.mode == 'offline':
        sys.path.insert(0, str(SIM))
        import coverage as cov
        try:
            cov.simulate(code, n, 32, 64, 0, tb)
        except RuntimeError as e:
            print('simulator refuses the bit-52 form as designed:', str(e)[-90:])
        # gate: the same program with the plain fmadd32 must run to the end (structure, table layout, termination)
        plain = bytearray(instr()); plain[6] &= ~(1 << 4)
        pcode = drm.build_main(RS.alu_body(bytes(plain), n))
        o, t = cov.simulate(pcode, n, 32, 64, 0, tb)
        print('gate: plain fmadd32 program ran, first results', [hex(t[8*n+2*i]) for i in range(3)])
        return
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    rec = {'text': TEXT, 'vals': VALS, 'n': NN, 'set': a.set, 'triples': triples(second), 'runs': []}
    for rep in range(a.repeats):
        (out/'c.bin').write_bytes(code+bytes(16)); (out/'t.bin').write_bytes(struct.pack(f'<{len(tb)}I', *tb))
        r = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'c.bin'), str(n), str(out/'rb'), '1', '64', str(out/'t.bin')],
                           capture_output=True, timeout=60, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(out/'t.out'), 'AGX_LOCAL_X': '256'})
        smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
        if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
            sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
        t = struct.unpack(f'<{len(tb)}I', (out/'t.out').read_bytes())
        res = [t[8*n+2*i] for i in range(NN)]
        rec['runs'].append(res)
        print('run', rep, 'results', len(res), 'distinct', len(set(res)), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')


if __name__ == '__main__':
    main()
