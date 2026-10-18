#!/usr/bin/env python3
"""Cost of the Mesa-emitted barriers (safe-10 step 6): unrolled chains, no loops, one SIMD group, clock keeper running.

Program = prologue + N x (context op, `wait 0`, [fence]) + epilogue. The control has the same N units without the fence,
so (test - control) / N is the cost of one fence in that context. Contexts: none (back to back fences, control is empty),
store (coherent store of the lane's word before each fence), load (coherent load). Samples are interleaved
(control, tests...) 5 times. Every program is gated in agx_run first. Firmware nanoseconds, top-clock cluster.
  probe_fence_cost.py offline | hardware [--n 32] [--samples 5] [--output result.json]
"""
import argparse, json, struct, subprocess, sys, time
from pathlib import Path
import agx_loop, gpu_safety, run_drm_compute as drm, run_drm_atomic as DA
import run_agx_timestamps as chains
from run_drm_cpu_clock import load
from run_drm_litmus import FENCES, store
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path('/scratch/apple-m2-playground/drm-compute/fence-cost')
FENCE_SET = ['f596', 'f533', 'f59d', 'f59a', 'f59e', 'f503', 'f599', 'f533+f59d', 'mesa_qf']
CONTEXTS = ['none', 'store', 'load']


def fb(spec):
    return FENCES[spec] if spec in FENCES else b''.join(FENCES[x] for x in spec.split('+'))


def body(n, ctx, fence):
    e = agx_loop.encode; mov = chains.mov_imm
    ins = [mov(5, 1), mov(4, 0)]
    for _ in range(n):
        if ctx == 'store':
            ins += [store(5, 1, True), e('wait 0')]
        elif ctx == 'load':
            ins += [load(4, 1, True), e('wait 0')]
        if fence:
            ins.append(fb(fence))
    ins.append(e('iadd r2, r4, 0'))
    split = []
    for i in ins:
        if i[:1] == b'\xf5' and len(i) % 2 == 0:
            split += [i[j:j+2] for j in range(0, len(i), 2)]
        elif i:
            split.append(i)
    DA.decode_lengths(b''.join(split), [len(i) for i in split])
    return b''.join(split)


def programs(n):
    out = {}
    for ctx in CONTEXTS:
        out[(ctx, None)] = drm.build_main(body(n, ctx, None))
        for f in FENCE_SET:
            out[(ctx, f)] = drm.build_main(body(n, ctx, f))
    return out


def gate(progs):
    for key, code in progs.items():
        out, tab = cov.simulate(code, 32, 32, 48, 0, [0]*64)
        assert out[8:40] == [0]*32 and all(x in (0, 1) for x in tab), key


def hardware(n, samples, output):
    progs = programs(n)
    gate(progs)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    exe = SCRATCH/'drm_compute'
    subprocess.run(['cc', '-std=c11', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)], check=True)
    stop = SCRATCH/'keeper-stop'; stop.unlink(missing_ok=True)
    keeper = subprocess.Popen([sys.executable, '-B', 'scripts/clock_keeper.py', '--seconds', '300', '--stop-file', str(stop)],
                              cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    rec = {'n': n, 'samples': samples, 'fences': FENCE_SET, 'contexts': CONTEXTS, 'results': [], 'keeper_pid': keeper.pid}
    try:
        for s in range(samples):
            for (ctx, f), code in progs.items():
                (SCRATCH/'c.bin').write_bytes(code+bytes(16)); (SCRATCH/'t.bin').write_bytes(bytes(4*64))
                gpu_safety.require_budget(1)
                r = subprocess.run([str(exe), '/dev/dri/renderD128', str(SCRATCH/'c.bin'), '32', str(SCRATCH/'rb'), '1', '48', str(SCRATCH/'t.bin')],
                                   capture_output=True, timeout=30, env={'PATH': '/usr/bin', 'AGX_LOCAL_X': '32', 'AGX_TABLE_OUT': str(SCRATCH/'t.out')})
                smp = [json.loads(l) for l in r.stdout.decode().splitlines() if '"rep"' in l]
                if r.returncode or len(smp) != 1 or not all(smp[0]['fw_ts']):
                    gpu_safety.record(f'fence-cost {ctx}/{f}')
                    sys.exit(f'run failed for {ctx}/{f}')
                w = struct.unpack('<40I', (SCRATCH/'rb').read_bytes()[:160])[8:40]
                rec['results'].append({'sample': s, 'ctx': ctx, 'fence': f, 'fw_ns': smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0], 'out_ok': all(x == 0 for x in w)})
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
        gate(programs(a.n)); print('all programs gated in agx_run'); return
    rec = hardware(a.n, a.samples, a.output)
    import statistics as st
    base = {}
    for r in rec['results']:
        base.setdefault((r['ctx'], r['fence']), []).append(r['fw_ns'])
    for ctx in CONTEXTS:
        c = st.median(base[(ctx, None)])
        print(f'{ctx}: control median {c} ns')
        for f in FENCE_SET:
            t = st.median(base[(ctx, f)])
            print(f'  {f:10s} median {t:8.0f} ns  per fence {(t-c)/a.n:7.1f} ns')


if __name__ == '__main__':
    main()
