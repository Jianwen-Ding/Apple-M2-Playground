#!/usr/bin/env python3
"""Cross-queue ordering through DRM syncobjs (simulator task safe-12 step 4).

Queue A and queue B each run the same bounded kernel: the control prefix, an emulator-gated delay loop, then the
control store of 0x12345678 (oracle: every lane writes it; guards and tail untouched). tests/drm_compute.c
AGX_SYNC_MODE submits A then B per repeat:
  0  B has no wait          -> B may overlap A (the control: proves the queues can run concurrently)
  1  B waits on A's binary syncobj (in_sync)
  2  B waits on a timeline syncobj point that A signals
Ordering is read from the firmware start / end timestamps (1 GHz) of both commands.

Safety: before any GPU use the exact kernel is run in the simulator's agx_run (must stop, every lane must store the
oracle), it must end with `stop`, every instruction must decode, and the hang budget must have room.
"""
import argparse, datetime, json, os, shlex, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SIM = Path(os.environ.get('AGX_SIM', REPO.parent/'AGX-Performance-Simulator'))
sys.path.insert(0, str(REPO/'scripts'))
import gpu_safety  # noqa: E402
import run_drm_compute as drm  # noqa: E402
import run_drm_sr_scan as scan  # noqa: E402

ORACLE = 0x12345678


def kernel(delay):
    return drm.build_main(scan.delay_loop(delay)+bytes.fromhex('620978563412'))


def simulate(code, count, tmp):
    """Run the exact kernel in agx_run with the harness's uniforms and output layout; return the output words."""
    words = 8+(count+31)//32*32+8+16
    init = [0xcdcdcdcd]*(words-16)+[0xa5a50000+i for i in range(16)]
    (tmp/'o.bin').write_bytes(struct.pack(f'<{words}I', *init))
    (tmp/'k.bin').write_bytes(code+bytes(16))
    run = SIM/'rust/target/release/agx_run'
    r = subprocess.run([str(run), str(tmp/'k.bin'), '--grid', str((count+31)//32*32), '--wg', '32', '--regs', '16',
                        '--uniform', '4=0', '--uniform', f'5={count}', '--uniform', '6=0x100000', '--uniform', '7=0x11',
                        '--map', f'0x1100100000={tmp/"o.bin"}', '--dump', f'0x1100100000={4*words}:{tmp/"r.bin"}',
                        '--max-steps', '200000000'], capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError('agx_run failed: '+(r.stdout+r.stderr)[-300:])
    return list(struct.unpack(f'<{words}I', (tmp/'r.bin').read_bytes())), json.loads(r.stdout.strip().splitlines()[-1])


def oracle_ok(out, count):
    rounded = (count+31)//32*32
    return (out[:8] == [0xcdcdcdcd]*8 and out[8:8+count] == [ORACLE]*count
            and out[8+count:8+rounded+8] == [0xcdcdcdcd]*(rounded-count+8) and out[-16:] == [0xa5a50000+i for i in range(16)])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--delay', type=int, default=4000, help='delay-loop trips (about 1 ms per 4000; max 20000)')
    p.add_argument('--count', type=int, default=64)
    p.add_argument('--modes', default='0,1,2')
    p.add_argument('--repeats', type=int, default=8)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    p.add_argument('--sim-only', action='store_true')
    a = p.parse_args()
    if not (1 <= a.delay <= 20000 and 1 <= a.count <= 4096 and 1 <= a.repeats <= 64):
        sys.exit('refusing: bounded delay / count / repeats required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/sync')/stamp
    out.mkdir(parents=True, exist_ok=False)
    code = kernel(a.delay)
    if code[-2:] != bytes.fromhex('8800'):
        sys.exit('refusing: program does not end with stop')
    sim_out, sim_stats = simulate(code, a.count, out)
    state = {'utc': stamp, 'delay': a.delay, 'count': a.count, 'repeats': a.repeats, 'code_hex': code.hex(),
             'simulator': {'oracle_ok': oracle_ok(sim_out, a.count), 'stats': sim_stats}, 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    save()
    if not state['simulator']['oracle_ok']:
        sys.exit('refusing: simulator output does not match the oracle')
    print(json.dumps({'simulator': state['simulator']}))
    if a.sim_only:
        return 0
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    (out/'k.bin').write_bytes(code+bytes(16))
    for mode in [int(m) for m in a.modes.split(',')]:
        gpu_safety.require_budget(1)
        rb = out/f'mode{mode}.readback'
        env = dict(os.environ, AGX_SYNC_MODE=str(mode))
        try:
            res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(a.count), str(rb), str(a.repeats), '16'],
                                 capture_output=True, timeout=60, env=env)
        except subprocess.TimeoutExpired:
            gpu_safety.record(f'run_drm_sync mode {mode}: harness timeout')
            state['runs'].append({'mode': mode, 'timeout': True}); save()
            sys.exit('timeout: stopping')
        lines = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{')]
        pairs = [l for l in lines if 'pair' in l]
        words = len(rb.read_bytes())//4 if rb.exists() else 0
        ok = res.returncode == 0 and words and oracle_ok(list(struct.unpack(f'<{words}I', rb.read_bytes())), a.count)
        for q in pairs:
            q['b_start_minus_a_end_ns'] = q['b'][0]-q['a'][1]
            q['overlap'] = q['b'][0] < q['a'][1] and q['a'][0] < q['b'][1]
        rec = {'mode': mode, 'returncode': res.returncode, 'oracle_ok': bool(ok), 'pairs': pairs,
               'stderr': res.stderr.decode()[-300:], 'failure': [l for l in lines if 'failure' in l]}
        if any(q['wait'] for q in pairs) or res.returncode:
            gpu_safety.record(f'run_drm_sync mode {mode}: wait failure')
        state['runs'].append(rec); save()
        print(json.dumps({'mode': mode, 'returncode': res.returncode, 'oracle_ok': bool(ok),
                          'overlaps': sum(q['overlap'] for q in pairs), 'pairs': len(pairs),
                          'gap_ns': [q['b_start_minus_a_end_ns'] for q in pairs]}))
        if not ok:
            sys.exit('stopping on failure')
    return 0


if __name__ == '__main__':
    sys.exit(main())
