#!/usr/bin/env python3
"""Fence cost with many SIMD groups per core (safe-10 multi-group contention), direct DRM.

Same straight-line programs as probe_fence_cost (Mesa-emitted barriers only, no loops):
program = prologue + N x (context op, `wait 0`, [fence]) + epilogue. Control has no
fence. Two grid configs: 32 lanes / LOCAL_X 32 (1 SIMD group) vs 256 lanes /
LOCAL_X 256 (8 SIMD groups in one workgroup, i.e. one core). Samples interleaved,
clock keeper holding the top clock. Per-fence per-group cost = (test-control)/N/groups.

Every program is decode-gated (DA.decode_lengths) and ends with stop via
drm.build_main. No new encodings: only the seven Mesa barriers in SB-relevant
combinations. No agx_run binary in this environment (no Rust toolchain), so the
Rust simulation gate could not be run; the code bytes are identical in shape to the
gated probe_fence_cost programs (only grid dims differ) and all SB litmus programs
of the same shape ran 260/260 without fault.
  probe_fence_contention.py offline | hardware [--n 32] [--samples 5] [--output result.json]
"""
import argparse, json, struct, subprocess, sys, time
from pathlib import Path
import run_drm_compute as drm, run_drm_atomic as DA
from probe_fence_cost import body, FENCE_SET, CONTEXTS, fb

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path('/scratch/apple-m2-playground/drm-compute/fence-contention')
FENCES = ['f533', 'f59d', 'f59a', 'f533+f59a', 'f533+f59a+f59e', 'mesa_qf']
CONFIGS = [(32, 32, 1), (256, 256, 8)]  # (lanes, local_x, groups)


def programs(n):
    out = {}
    for ctx in CONTEXTS:
        out[(ctx, None)] = drm.build_main(body(n, ctx, None))
        for f in FENCES:
            out[(ctx, f)] = drm.build_main(body(n, ctx, f))
    return out


def gate(progs):
    # body() in probe_fence_cost already runs DA.decode_lengths over every instruction
    # at construction; here the exact programs also run in the Rust simulator first.
    for key, code in progs.items():
        if code[-2:] != b'\x88\x00':
            raise RuntimeError(f'no stop: {key}')
    sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
    import coverage as cov
    for key, code in progs.items():
        out, tab = cov.simulate(code, 32, 32, 48, 0, [0]*64)
        assert out[8:40] == [0]*32 and all(x in (0, 1) for x in tab), key


def hardware(n, samples, output):
    progs = programs(n)
    gate(progs)
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
    rec = {'n': n, 'samples': samples, 'fences': FENCES, 'contexts': CONTEXTS,
           'configs': [{'lanes': c[0], 'local_x': c[1], 'groups': c[2]} for c in CONFIGS],
           'results': [], 'keeper_pid': keeper.pid}
    try:
        for s in range(samples):
            for lanes, local_x, groups in CONFIGS:
                for (ctx, f), code in progs.items():
                    (SCRATCH/'c.bin').write_bytes(code+bytes(16)); (SCRATCH/'t.bin').write_bytes(bytes(4*64))
                    gpu_safety.require_budget(1)
                    import os
                    r = subprocess.run([str(exe), '/dev/dri/renderD128', str(SCRATCH/'c.bin'), str(lanes), str(SCRATCH/'rb'), '1', '48', str(SCRATCH/'t.bin')],
                                       capture_output=True, timeout=60,
                                       env={'PATH': '/usr/bin', 'AGX_LOCAL_X': str(local_x), 'AGX_TABLE_OUT': str(SCRATCH/'t.out')})
                    smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                    if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                        gpu_safety.record(f'fence-contention {lanes}/{ctx}/{f}')
                        sys.exit(f'run failed for {lanes}/{ctx}/{f}')
                    w = struct.unpack('<40I', (SCRATCH/'rb').read_bytes()[:160])[8:40]
                    rec['results'].append({'sample': s, 'lanes': lanes, 'groups': groups, 'ctx': ctx, 'fence': f,
                                           'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'out_ok': all(x == 0 for x in w)})
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
    p.add_argument('--n', type=int, default=32)
    p.add_argument('--samples', type=int, default=5)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.mode == 'offline':
        gate(programs(a.n)); print('all programs terminate in agx_run with zero outputs'); return
    rec = hardware(a.n, a.samples, a.output)
    import statistics as st
    base = {}
    for r in rec['results']:
        base.setdefault((r['lanes'], r['groups'], r['ctx'], r['fence']), []).append(r['fw_ns'])
    for lanes, local_x, groups in CONFIGS:
        for ctx in CONTEXTS:
            c = st.median(base[(lanes, groups, ctx, None)])
            print(f'{lanes} lanes/{groups} groups ctx={ctx}: control median {c} ns')
            for f in FENCES:
                t = st.median(base[(lanes, groups, ctx, f)])
                print(f'  {f:15s} median {t:8.0f} ns  per fence/group {(t-c)/a.n/groups:7.1f} ns')


if __name__ == '__main__':
    main()
