#!/usr/bin/env python3
"""Same-address device-atomic contention (simulator task safe-02 step 1), direct DRM.

Each of L lanes runs R device `atomic add` without return (agx_loop.atomic_add, validated in sr-direct-drm / atomics)
in a counted loop on table word (gid mod K) * spacing, adding 1. Exact table oracle: word j = (lanes mapped to j) * R.
Modes: 'all' (every lane), 'lane0' (only lane 0 of each SIMD group runs the loop: tests whether a group's 32 lanes
are combined into one access). spacing 16 words = one address per 64-byte line; spacing 1 = adjacent words.
Every kernel + table runs in the simulator's agx_run first (out and table must match the oracle). Run with
scripts/clock_keeper.py in the background.
"""
import argparse, array, datetime, importlib.util, json, os, shlex, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import agx_loop, gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402

spec = importlib.util.spec_from_file_location('sim_coverage', sim_gate.SIM/'scripts/coverage.py')
simcov = importlib.util.module_from_spec(spec); spec.loader.exec_module(simcov)


def body(K, spacing, R, mode):
    enc, mov = agx_loop.encode, agx_loop.chains.mov_imm
    b = mov(27, K-1)+enc('and r7, r1, r27')+mov(27, spacing)+enc('imadd r5, r7, r27, 0')+mov(6, 1)
    loop_head = mov(3, 0)+mov(4, R)
    lp = agx_loop.atomic_add(8, 5, 6)+enc('iadd r3, 1, r3.sx')+enc('while_icmp r0l, ult, r3, r4, 1')
    jump = enc(f'jmp_exec_any pc-{len(lp)}', f'jmp_exec_any pc-{len(lp)}')
    core = loop_head+enc('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')+lp+jump+enc('pop_exec r0l, 1')
    if mode == 'lane0':
        core = mov(27, 31)+enc('and r24, r1, r27')+enc('if_icmp r0l, ueq, r24, 0, 1')+core+enc('pop_exec r0l, 1')
    return b+core+enc('wait 0')+mov(2, 0x12345678)


def oracle(L, K, spacing, R, mode, words):
    t = [0]*words
    for g in range(L):
        if mode == 'lane0' and g % 32: continue
        t[(g % K)*spacing] += R
    return [x & 0xffffffff for x in t]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--configs', default='32:1,1024:1,1024:32,1024:1024,32768:1,32768:32,32768:1024,32768:32768,65536:1,65536:65536')
    p.add_argument('--modes', default='all,lane0')
    p.add_argument('--spacings', default='16,1')
    p.add_argument('--r', type=int, default=64)
    p.add_argument('--repeats', type=int, default=4)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    p.add_argument('--sim-max-lanes', type=int, default=4096, help='simulate with min(L, this) lanes (same code; K kept)')
    a = p.parse_args()
    cfgs = [tuple(map(int, c.split(':'))) for c in a.configs.split(',')]
    if not (all(32 <= L <= 1 << 20 and L % 32 == 0 and 1 <= K <= L and K & (K-1) == 0 for L, K in cfgs) and 1 <= a.r <= 4096):
        sys.exit('refusing: bounded L (multiple of 32), K power of two <= L, R <= 4096')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/atomic-contend')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-pthread', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    state = {'utc': stamp, 'r': a.r, 'repeats': a.repeats, 'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(), 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    for mode in a.modes.split(','):
        for sp in map(int, a.spacings.split(',')):
            for L, K in cfgs:
                words = max(K*sp, 64)
                code = drm.build_main(body(K, sp, a.r, mode))
                # simulator gate: same code, min(L, sim-max-lanes) lanes, exact output and table
                Ls = min(L, a.sim_max_lanes)
                sout, stab = simcov.simulate(code, Ls, 32, 32, 0, [0]*words)
                sim_ok = sim_gate.oracle_ok(sout, Ls, 0x12345678) and stab == oracle(Ls, K, sp, a.r, mode, words)
                if not sim_ok:
                    sys.exit(f'refusing: simulator differs from the oracle for {mode} sp{sp} L{L} K{K}')
                gpu_safety.require_budget(1)
                tp, tout = out/'t.bin', out/'t.out'
                fws, ok = [], True
                want = oracle(L, K, sp, a.r, mode, words)
                (out/'k.bin').write_bytes(code+bytes(16))
                for rep in range(a.repeats):    # one dispatch per process: the table must start at zero each time
                    tp.write_bytes(bytes(4*words))
                    try:
                        res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(L), str(out/'rb'), '1', '32', str(tp)],
                                             capture_output=True, timeout=60, env=dict(os.environ, AGX_TABLE_OUT=str(tout)))
                    except subprocess.TimeoutExpired:
                        gpu_safety.record(f'run_drm_atomic_contend {mode} L{L} K{K}: timeout'); save(); sys.exit('timeout: stopping')
                    smp = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{"rep"')]
                    w = len((out/'rb').read_bytes())//4 if (out/'rb').exists() else 0
                    ok &= res.returncode == 0 and w > 0 and sim_gate.oracle_ok(list(struct.unpack(f'<{w}I', (out/'rb').read_bytes())), L, 0x12345678)
                    ok &= list(array.array('I', tout.read_bytes())) == want if res.returncode == 0 else False
                    if smp: fws.append(smp[0]['fw_ts'][1]-smp[0]['fw_ts'][0])
                    if not ok: break
                n_atomics = (L if mode == 'all' else L//32)*a.r
                per_addr = n_atomics/K
                rec = {'mode': mode, 'spacing': sp, 'lanes': L, 'addresses': K, 'atomics': n_atomics, 'per_address': per_addr,
                       'oracle_ok': bool(ok), 'fw_ns': fws, 'sim_lanes': Ls}
                state['runs'].append(rec); save()
                mn = min(fws) if fws else 0
                print(json.dumps({'mode': mode, 'sp': sp, 'L': L, 'K': K, 'ok': bool(ok), 'fw_us': round(mn/1e3, 1),
                                  'ns_per_atomic_per_address': round(mn/per_addr, 2) if per_addr else None,
                                  'atomics_per_ns': round(n_atomics/mn, 3) if mn else None}), flush=True)
                if not ok:
                    sys.exit('stopping on failure')


if __name__ == '__main__':
    sys.exit(main())
