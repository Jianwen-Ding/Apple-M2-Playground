#!/usr/bin/env python3
"""UNSAFE (owner-approved 2026-10-20): threadgroup_barrier 0x68 with its unexplored byte-1 bits (gap bits 8-15) set, under
the message-passing stress test of run_drm_barrier_stress.py with several SIMD groups per workgroup.

Every SIMD group executes every barrier with uniform control flow, so a plain barrier cannot deadlock. A bit that makes the
barrier wait for FEWER groups shows mismatches; one that waits for MORE (or for another barrier ID that never completes)
hangs until the driver timeout. Controls: 6800 (Mesa) must give 0 mismatches, `wait` (no barrier) must give many.
One variant per submission, a short loop, the GPU fault budget checked before every run, stop at the first fault.
Each body is run in the Rust simulator first (layout / termination check; the simulator treats 0x68 as a barrier).
  CONFIRM_GPU_FAULTS=1 run_drm_barrier_bits.py [--bits 0,1,...,7] [--size 256] [--trips 200] [--result FILE]
"""
import argparse, json, os, struct, subprocess, sys
from pathlib import Path
import run_drm_barrier_stress as BS
import run_drm_compute as drm
import gpu_safety

REPO = Path(__file__).resolve().parents[1]


def variants(bits):
    v = [('wait', BS.WAIT), ('6800', bytes([0x68, 0]))]
    v += [(f'68{1 << b:02x}', bytes([0x68, 1 << b])) for b in bits]
    v += [('6800-after', bytes([0x68, 0]))]          # control repeated after the sweep: the device still behaves
    return v


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bits', default='0,1,2,3,4,5,6,7', help='byte-1 bit positions (gap bits 8-15 = bits 0-7 of byte 1)')
    p.add_argument('--size', type=int, default=256, help='workgroup lanes (SIMD groups = size / 32)')
    p.add_argument('--trips', type=int, default=200)
    p.add_argument('--total', type=int, default=2048)
    p.add_argument('--timeout', type=int, default=20)
    p.add_argument('--sim-only', action='store_true')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/barrier-bits'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    bits = [int(x) for x in a.bits.split(',')]
    sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
    import coverage as cov
    jobs = []
    for name, enc_bar in variants(bits):
        BS.BARRIERS[name] = enc_bar
        body = BS.body('tg', name, 'wait+mb' if name != 'wait' else 'none', a.size, a.trips, a.total)
        code = drm.build_main(body)
        # simulator layout / termination check (one workgroup); the bits themselves are not modelled
        try:
            o, t = cov.simulate(code, a.size, a.size, BS.GPRS, BS.SHARED_32K, [BS.SENT]*(2*a.total))
            sim = 'ok'
        except Exception as e:                                # an undecodable gap bit is reported, not fatal
            sim = f'simulator: {type(e).__name__}: {str(e)[:120]}'
        jobs.append(dict(name=name, code=code, sim=sim))
        print(json.dumps({'variant': name, 'bytes': enc_bar.hex(), 'sim': sim}), flush=True)
    if a.sim_only:
        return 0
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1':
        sys.exit('refusing to run without CONFIRM_GPU_FAULTS=1')
    out = a.output; out.mkdir(parents=True, exist_ok=True)
    exe = out/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    words = 2*a.total
    rec = {'size': a.size, 'trips': a.trips, 'total': a.total, 'results': []}
    save = lambda: a.result and a.result.write_text(json.dumps(rec)+'\n')
    for jb in jobs:
        gpu_safety.require_budget(1)
        (out/'code.bin').write_bytes(jb['code']+bytes(16))
        (out/'table.bin').write_bytes(struct.pack('<I', BS.SENT)*words)
        env = dict(os.environ, AGX_LOCAL_X=str(a.size), AGX_SHARED_WORD=str(BS.SHARED_32K), AGX_TABLE_OUT=str(out/'table.out'))
        r = {'name': jb['name'], 'sim': jb['sim']}
        try:
            res = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'code.bin'), str(a.total), str(out/'rb'), '1', str(BS.GPRS), str(out/'table.bin')],
                                 capture_output=True, timeout=a.timeout, env=env)
            smp = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{"rep"')]
            ok = res.returncode == 0 and len(smp) == 1 and all(smp[0]['fw_ts'])
            r['fw_ms'] = (smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0])/1e6 if ok else None
            if ok:
                t = struct.unpack(f'<{words}I', (out/'table.out').read_bytes())
                cnt = t[:a.total]
                r['mismatches'] = sum(cnt); r['lanes_with_errors'] = sum(c > 0 for c in cnt)
                n = a.size
                r['err_lanes_by_group'] = [sum(1 for i, c in enumerate(cnt) if c and (i % n)//32 == g) for g in range(n//32)]
            else:
                r['stdout_tail'] = res.stdout.decode(errors='replace')[-300:]
            r['fault'] = not ok
        except subprocess.TimeoutExpired:
            r['fault'] = True; r['timed_out'] = True
        if r['fault']:
            gpu_safety.record(f"run_drm_barrier_bits {jb['name']}: fault / timeout")
        rec['results'].append(r); save()
        print(json.dumps(r), flush=True)
        if r['fault']:
            print('stopping at the first fault', flush=True)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
