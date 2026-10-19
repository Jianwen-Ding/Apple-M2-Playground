#!/usr/bin/env python3
"""Does pop_exec restore lanes masked off by if_icmp when their SIMD group is empty? (safe)

One 64-lane workgroup. if_icmp keeps group 0 active and deactivates group 1 (same mask shape as
probe_tg_end_visible). pop_exec r0l, 1, then every lane stores a marker. If group 1's markers
appear, pop restores under an empty mask; if absent, pop under an empty mask is a no-op (lanes
stay inactive). All encodings recorded safe; straight-line; agx_run-gated; single dispatch.
  probe_pop_empty.py offline|hardware
"""
import argparse, json, struct, subprocess, sys
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
from run_drm_opcode_describe import get_sr, WAIT
import run_agx_timestamps as chains

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path('/scratch/apple-m2-playground/drm-compute/pop-empty')
N = 64
SENT = 0xcdcdcdcd
MARK = 0xcafe0001


def build():
    e = agx_loop.encode
    mov = chains.mov_imm
    ins = [get_sr(53, 4), mov(27, 0), e('if_icmp r0l, ueq, r4, r27, 1'),
           e('pop_exec r0l, 1'),
           mov(23, MARK), mov(20, 0), e('iadd r29, r1, r20'), agx_loop.store(23, 8, 29),
           e('wait 0')]
    ins += [e('iadd r2, r0, 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return drm.build_main(b''.join(ins))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['offline', 'hardware'])
    a = ap.parse_args()
    code = build()
    assert code[-2:] == b'\x88\x00'
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import coverage as cov
        o, t = cov.simulate(code, N, 64, 64, 0, [SENT]*N)
        print('simulator table all MARK:', sorted(set(t[:N])) == [MARK], [hex(v) for v in sorted(set(t[:N]))])
        print('simulator out:', list(o[8:8+N]))
        return
    SCRATCH.mkdir(parents=True, exist_ok=True)
    exe = SCRATCH/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    (SCRATCH/'c.bin').write_bytes(code+bytes(16)); (SCRATCH/'t.bin').write_bytes(struct.pack('<I', SENT)*N)
    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(SCRATCH/'c.bin'), str(N), str(SCRATCH/'rb'), '1', '64', str(SCRATCH/'t.bin')],
                       capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(SCRATCH/'t.out'), 'AGX_LOCAL_X': '64'})
    smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
    if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
        sys.exit('dispatch failed: '+r.stdout.decode()[-300:])
    t = struct.unpack(f'<{N}I', (SCRATCH/'t.out').read_bytes())
    g0 = [t[i] for i in range(N) if (i & 63) < 32]
    g1 = [t[i] for i in range(N) if (i & 63) >= 32]
    print(json.dumps({'g0_mark': sum(v == MARK for v in g0), 'g1_mark': sum(v == MARK for v in g1),
                      'g0_vals': sorted(set(g0)), 'g1_vals': sorted(set(g1)), 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0]}))


if __name__ == '__main__':
    main()
