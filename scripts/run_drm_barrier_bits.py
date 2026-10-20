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


def split(b_lo, b_hi, half=128):
    """Group-uniform if/else inside the stress loop: lanes with local index < half execute barrier b_lo, the others b_hi
    (r25 = local index, set before the loop by run_drm_barrier_stress.body)."""
    e = BS.enc
    return (e(f'if_icmp r0l, ult, r25, {half}, 1') + e(f'jmp_exec_none pc+{6+len(b_lo)}', f'jmp_exec_none pc+{6+len(b_lo)}') + b_lo +
            e(f'else_icmp r0l, ugt, r25, {half-1}, 1') + e(f'jmp_exec_none pc+{6+len(b_hi)}', f'jmp_exec_none pc+{6+len(b_hi)}') + b_hi +
            e('pop_exec r0l, 1'))


def split_variants(pairs):
    v = [('split-6800-6800', split(bytes([0x68, 0]), bytes([0x68, 0])))]
    v += [(f'split-6800-{b:04x}', split(bytes([0x68, 0]), bytes([0x68, b >> 8 if b > 0xff else 0]) if False else bytes([0x68, b & 0xff]))) for b in pairs]
    # positive control: 0x78 synchronizes aligned blocks of 4 SIMD groups = exactly the two halves, i.e. two separate barriers;
    # cross-half readers (groups 3 and 7) must show errors, so the split test can detect a barrier-ID separation
    v += [('split-7809-7809', split(bytes([0x78, 0x09]), bytes([0x78, 0x09])))]
    v += [('split-6800-6800-after', split(bytes([0x68, 0]), bytes([0x68, 0])))]
    return v


def variants(bits, op=0x68, extra=()):
    base = bytes([op, 0x09 if op == 0x78 else 0])          # 0x78's known form is 7809 (7800 behaves the same)
    v = [('wait', BS.WAIT), (base.hex(), base)]
    v += [(f'{op:02x}{1 << b:02x}', bytes([op, 1 << b])) for b in bits]
    v += [(f'{op:02x}{x:02x}', bytes([op, x])) for x in extra]
    v += [(base.hex()+'-after', base)]               # control repeated after the sweep: the device still behaves
    return v


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bits', default='0,1,2,3,4,5,6,7', help='byte-1 bit positions (gap bits 8-15 = bits 0-7 of byte 1)')
    p.add_argument('--size', type=int, default=256, help='workgroup lanes (SIMD groups = size / 32)')
    p.add_argument('--trips', type=int, default=200)
    p.add_argument('--total', type=int, default=2048)
    p.add_argument('--timeout', type=int, default=20)
    p.add_argument('--sim-only', action='store_true')
    p.add_argument('--pre', default='wait+mb', choices=['none', 'wait', 'mb', 'wait+mb'], help='sequence before barrier A (none: the barrier alone must order memory)')
    p.add_argument('--mem', default='tg', choices=['tg', 'dev'])
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--op', default='0x68', help='0x68 or 0x78')
    p.add_argument('--extra', default='', help='extra byte-1 values (comma separated), e.g. 0xff')
    p.add_argument('--split', default=None, help='comma-separated byte-1 values: groups 4-7 use 68XX, groups 0-3 6800 (barrier-ID test)')
    p.add_argument('--output', type=Path, default=Path('/scratch/apple-m2-playground/drm-compute/barrier-bits'))
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    bits = [int(x) for x in a.bits.split(',')]
    sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
    import coverage as cov
    jobs = []
    op = int(a.op, 0); assert op in (0x68, 0x78)
    extra = [int(x, 0) for x in a.extra.split(',') if x]
    vs = split_variants([int(x, 0) for x in a.split.split(',')]) if a.split else variants(bits, op, extra)
    for name, enc_bar in vs:
        # 0x78 with an unknown byte 1: pad with five 2-byte waits so a longer-than-2-byte decoding swallows padding, not code
        pad78 = op == 0x78 and name not in ('wait',) and enc_bar[:1] == b'\x78'
        BS.BARRIERS[name] = enc_bar + (BS.WAIT*5 if pad78 else b'')
        body = BS.body(a.mem, name, a.pre if name != 'wait' else 'none', a.size, a.trips, a.total)
        code = drm.build_main(body)
        # simulator layout / termination check (one workgroup); the bits themselves are not modelled
        sim_code = code
        if pad78 and enc_bar != bytes([0x78, 0x09]):          # the simulator only decodes 7809: gate the identical layout with 7809
            BS.BARRIERS[name+'-gate'] = bytes([0x78, 0x09]) + BS.WAIT*5
            sim_code = drm.build_main(BS.body(a.mem, name+'-gate', a.pre, a.size, a.trips, a.total))
            assert len(sim_code) == len(code)
        try:
            o, t = cov.simulate(sim_code, a.size, a.size, BS.GPRS, BS.SHARED_32K, [BS.SENT]*((8*a.total if a.mem == 'dev' else 0)+2*a.total))
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
    words = (8*a.total if a.mem == 'dev' else 0)+2*a.total
    base = 8*a.total if a.mem == 'dev' else 0
    rec = {'size': a.size, 'trips': a.trips, 'total': a.total, 'pre': a.pre, 'mem': a.mem, 'repeats': a.repeats, 'op': a.op, 'results': []}
    save = lambda: a.result and a.result.write_text(json.dumps(rec)+'\n')
    for jb in jobs:
        gpu_safety.require_budget(1)
        (out/'code.bin').write_bytes(jb['code']+bytes(16))
        (out/'table.bin').write_bytes(struct.pack('<I', BS.SENT)*words)
        env = dict(os.environ, AGX_LOCAL_X=str(a.size), AGX_TABLE_OUT=str(out/'table.out'))
        if a.mem == 'tg':
            env['AGX_SHARED_WORD'] = str(BS.SHARED_32K)
        r = {'name': jb['name'], 'sim': jb['sim']}
        try:
            res = subprocess.run([str(exe), '/dev/dri/renderD128', str(out/'code.bin'), str(a.total), str(out/'rb'), str(a.repeats), str(BS.GPRS), str(out/'table.bin')],
                                 capture_output=True, timeout=a.timeout, env=env)
            smp = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{"rep"')]
            ok = res.returncode == 0 and len(smp) == a.repeats and all(all(x['fw_ts']) for x in smp)
            r['fw_ms'] = (smp[-1]['fw_ts'][1]-smp[-1]['fw_ts'][0])/1e6 if ok else None
            if ok:
                t = struct.unpack(f'<{words}I', (out/'table.out').read_bytes())
                cnt = t[base:base+a.total]     # counts are from the last submission (the table persists across repeats)
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
