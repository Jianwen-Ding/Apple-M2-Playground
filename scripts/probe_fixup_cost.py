#!/usr/bin/env python3
"""Cycle cost of the non-ftz setp/min fix-up sequences (safe-01 remainder), direct DRM.

Program = prologue (constants + one operand-pair load per lane) + 64 x fix-up core + store.
Control has the same prologue/store without the fix-up core. Per-fixup cost =
(median test - median control) / 64, firmware ns, clock keeper holding the top clock.
Variants: eq (the 15-instruction base: two integer keys + select + NaN gate), min (raw keys +
select + two NaN gates) and neu (eq + not + NaN force). Only encodings already recorded safe
(the exact forms of run_drm_fcmp_fixup.py); straight-line, `stop`-terminated, every program
runs in agx_run against the host oracle before submission.
  probe_fixup_cost.py offline | hardware [--n 64] [--samples 15] [--output result.json]
"""
import argparse, json, struct, subprocess, sys, time
from pathlib import Path
import agx_loop, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_litmus import store
from run_drm_fcmp_fixup import ieee

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path('/scratch/apple-m2-playground/drm-compute/fixup-cost')
VARIANTS = ['eq', 'min', 'neu']
NPAIRS = 32


def core(variant):
    """One fix-up core on r6/r7 -> r36 (temps r8-r11, r18-r20, r23-r29, consts r12-r15, r21/r22).
    Same instruction forms as run_drm_fcmp_fixup.body."""
    e = agx_loop.encode
    k = [e('and r8, r6, r12'), e('asr r10, r6, r15'), e('or r10, r10, r13'), e('xor r32, r6, r10'),
         e('icmpsel ueq, r9, r8, 0, r13, r32'), e('icmpsel ugt, r11, r8, r14, 1, 0'),
         e('and r18, r7, r12'), e('asr r20, r7, r15'), e('or r20, r20, r13'), e('xor r33, r7, r20'),
         e('icmpsel ueq, r19, r18, 0, r13, r33'), e('icmpsel ugt, r23, r18, r14, 1, 0'),
         e('or r24, r11, r23')]
    if variant == 'eq':
        k += [e('icmpsel ult, r25, r9, r19, 1, 0'), e('icmpsel ueq, r27, r9, r19, 1, 0'),
              e('icmpsel ueq, r36, r24, 0, r27, 0')]
    elif variant == 'min':
        k += [e('icmpsel ult, r36, r32, r33, r6, r7'),
              e('icmpsel ueq, r36, r23, 0, r36, r6'),
              e('icmpsel ueq, r36, r11, 0, r36, r7')]
    elif variant == 'neu':
        k += [e('icmpsel ueq, r27, r9, r19, 1, 0'), e('icmpsel ueq, r36, r27, 0, r21, r22'),
              e('or r36, r36, r24')]
    else:
        raise ValueError(variant)
    return k


def body(n, variant):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(12, 0x7fffffff), mov(13, 0x80000000), mov(14, 0x7f800000), mov(15, 31), mov(21, 1), mov(22, 0),
           mov(16, NPAIRS), e('iadd r17, r1, r16'), load(6, 1, True), load(7, 17, True), e('wait 0')]
    if variant:
        for _ in range(n):
            ins += core(variant)
    ins += [mov(30, 2*NPAIRS), e('iadd r31, r1, r30'), agx_loop.store(36 if variant else 22, 8, 31),
            e('wait 0'), e('iadd r2, r22, 0')]
    DA.decode_lengths(b''.join(ins), [len(i) for i in ins])
    return b''.join(ins)


def programs(n):
    return {v: drm.build_main(body(n, v)) for v in [None] + VARIANTS}


def gate(progs, pairs):
    sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
    import coverage as cov
    A = [p[0] for p in pairs]; B = [p[1] for p in pairs]
    table = A+B+[0xcdcdcdcd]*NPAIRS
    for v, code in progs.items():
        if code[-2:] != b'\x88\x00':
            raise RuntimeError(f'no stop: {v}')
    o, t = cov.simulate(progs[None], NPAIRS, 32, 80, 0, table)
    assert o[8:8+NPAIRS] == [0]*NPAIRS, 'control must store 0'
    for v in VARIANTS:
        o, t = cov.simulate(progs[v], NPAIRS, 32, 80, 0, table)
        want = [ieee(v, x, y) for x, y in pairs]
        assert list(t[2*NPAIRS:3*NPAIRS]) == want, v
    print('all 4 programs terminate in agx_run; fix-up outputs match the IEEE host model')


def hardware(n, samples, output):
    import run_drm_fcmp_fixup as FX
    pairs = [(FX.VALS[i], FX.VALS[len(FX.VALS)-1-i]) for i in range(NPAIRS)]
    progs = programs(n)
    gate(progs, pairs)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    exe = SCRATCH/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    try:
        import gpu_safety
    except ImportError:
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        import gpu_safety
    stop = SCRATCH/'keeper-stop'; stop.unlink(missing_ok=True)
    keeper = subprocess.Popen([sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '300', '--stop-file', str(stop)],
                              cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    A = [p[0] for p in pairs]; B = [p[1] for p in pairs]
    table = struct.pack(f'<{3*NPAIRS}I', *(A+B+[0xcdcdcdcd]*NPAIRS))
    want = {v: [ieee(v, x, y) for x, y in pairs] for v in VARIANTS}
    rec = {'n': n, 'samples': samples, 'variants': VARIANTS, 'results': [], 'keeper_pid': keeper.pid}
    try:
        for s in range(samples):
            for v, code in progs.items():
                (SCRATCH/'c.bin').write_bytes(code+bytes(16)); (SCRATCH/'t.bin').write_bytes(table)
                gpu_safety.require_budget(1)
                import os
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(SCRATCH/'c.bin'), str(NPAIRS), str(SCRATCH/'rb'), '1', '80', str(SCRATCH/'t.bin')],
                                   capture_output=True, timeout=60,
                                   env={'PATH': '/usr/bin', 'AGX_TABLE_OUT': str(SCRATCH/'t.out')})
                smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                    gpu_safety.record(f'fixup-cost {v}')
                    sys.exit(f'run failed for {v}')
                w = struct.unpack(f'<{3*NPAIRS}I', (SCRATCH/'t.out').read_bytes())
                ok = True if v is None else list(w[2*NPAIRS:3*NPAIRS]) == want[v]
                rec['results'].append({'sample': s, 'variant': v, 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'out_ok': ok})
                if not ok:
                    sys.exit(f'oracle mismatch for {v}')
    finally:
        stop.touch()
        try:
            keeper.wait(timeout=60)
        except subprocess.TimeoutExpired:
            keeper.kill()
    rec['keeper_stopped'] = keeper.poll() is not None
    if output:
        output.write_text(json.dumps(rec)+'\n')
    return rec


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['offline', 'hardware'])
    p.add_argument('--n', type=int, default=64)
    p.add_argument('--samples', type=int, default=15)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    import run_drm_fcmp_fixup as FX
    pairs = [(FX.VALS[i], FX.VALS[len(FX.VALS)-1-i]) for i in range(NPAIRS)]
    if a.mode == 'offline':
        sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
        gate(programs(a.n), pairs); return
    rec = hardware(a.n, a.samples, a.output)
    import statistics as st
    base = {}
    for r in rec['results']:
        base.setdefault(r['variant'], []).append(r['fw_ns'])
    c = st.median(base[None])
    print(f'control median {c} ns')
    for v in VARIANTS:
        t = st.median(base[v])
        print(f'  {v:5s} median {t:8.0f} ns  per fix-up {(t-c)/a.n:7.1f} ns')


if __name__ == '__main__':
    main()
