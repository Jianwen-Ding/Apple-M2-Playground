#!/usr/bin/env python3
"""CPU <-> GPU visibility latency on unified memory (simulator task safe-03 step 4), direct DRM.

Ping-pong with fixed counts only (no spin-waits anywhere). One SIMD group runs N iterations of:
  store token k+1 -> T   [variant 'release': then f533]
  f59d; coherent load E (the CPU's echo) and C (the CPU's CNTVCT word); wait
  store E, C -> R[2k], R[2k+1]
tests/drm_compute.c AGX_CPU_ECHO=T,E,C runs a CPU thread that, on each new token, logs (token, CNTVCT) and writes
E = token, and writes C = CNTVCT on every poll. GPU firmware timestamps share the CNTVCT timebase (1 GHz = CNTVCT *
1e9/24e6; checked on the host), so with iteration k's time t(k) = fw_start + k * (fw_end - fw_start) / N:
  GPU -> CPU   cpu_seen(token k+1) - t(k)
  CPU -> GPU   t(first iteration whose E >= k+1) - cpu_seen(token k+1)
  clock age    t(j) - C(j)
Every kernel + table passes sim_gate (agx_run; with no CPU thread, E and C stay at their initial values) first.
"""
import argparse, array, datetime, json, os, shlex, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import agx_loop, gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402
from run_drm_cpu_clock import load  # noqa: E402  coherent device_load (Mesa u4 = 7)
from run_drm_litmus import store as litmus_store, FENCES  # noqa: E402  Mesa store forms (u4 = 4 / 7) and fence sequences

# variant -> (coherent store, fence after the token store); all Mesa-emitted forms, run in the memory-ordering litmus
VARIANTS = {'plain': (False, b''), 'release': (False, bytes.fromhex('f533')), 'coherent': (True, b''),
            'coherent_release': (True, bytes.fromhex('f533')), 'mesa_qf': (False, FENCES['mesa_qf']),
            'coherent_mesa_qf': (True, FENCES['mesa_qf'])}

T, E, C, RBASE = 0, 32, 64, 1024
ECHO0, CLOCK0 = 0xe0e0e0e0, 0xc0c0c0c0


def body(n, variant):
    coherent, fence = VARIANTS[variant]
    enc, mov = agx_loop.encode, agx_loop.chains.mov_imm
    head = mov(3, 0)+mov(4, n)+mov(10, T)+mov(11, E)+mov(12, C)+mov(13, RBASE)+enc('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    lp = enc('iadd r6, r3, 1')+(litmus_store(6, 10, True) if coherent else agx_loop.store(6, 8, 10))+enc('wait 0')+fence
    lp += bytes.fromhex('f59d')+load(7, 11, True)+load(8, 12, True)+enc('wait 0')
    lp += enc('iadd r14, r13, r3')+enc('iadd r14, r14, r3')+agx_loop.store(7, 8, 14)+enc('iadd r15, r14, 1')+agx_loop.store(8, 8, 15)+enc('wait 0')
    lp += enc('iadd r3, 1, r3.sx')+enc('while_icmp r0l, ult, r3, r4, 1')
    jump = enc(f'jmp_exec_any pc-{len(lp)}', f'jmp_exec_any pc-{len(lp)}')
    return head+lp+jump+enc('pop_exec r0l, 1')+mov(2, 0x12345678)


def table(n):
    t = array.array('I', [0])*(RBASE+2*n)
    t[E] = ECHO0; t[C] = CLOCK0
    return t


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--n', type=int, default=4096)
    p.add_argument('--variants', default=','.join(VARIANTS))
    p.add_argument('--trials', type=int, default=4)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if not (16 <= a.n <= 65536 and 1 <= a.trials <= 16):
        sys.exit('refusing: bounded n / trials')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/visibility')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-pthread', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    tp = out/'t.bin'; tp.write_bytes(table(a.n).tobytes())
    state = {'utc': stamp, 'n': a.n, 'words': {'T': T, 'E': E, 'C': C, 'R': RBASE}, 'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(), 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    for v in a.variants.split(','):
        code = drm.build_main(body(a.n, v))
        gate = sim_gate.require(code, 32, 0x12345678, regs=32, table=tp)
        # the simulator has no CPU thread: check its table too (tokens stored, E / C recorded unchanged)
        st = out/'sim-t.bin'
        state.setdefault('simulator', {})[v] = gate
        (out/f'{v}.bin').write_bytes(code+bytes(16))
        for trial in range(a.trials):
            gpu_safety.require_budget(1)
            tout, eout = out/f'{v}-{trial}.table', out/f'{v}-{trial}.echo'
            env = dict(os.environ, AGX_CPU_ECHO=f'{T},{E},{C}', AGX_CPU_ECHO_OUT=str(eout), AGX_TABLE_OUT=str(tout))
            try:
                res = subprocess.run([str(exe), a.device, str(out/f'{v}.bin'), '32', str(out/'rb'), '1', '32', str(tp)],
                                     capture_output=True, timeout=60, env=env)
            except subprocess.TimeoutExpired:
                gpu_safety.record(f'run_drm_visibility {v}: timeout'); save(); sys.exit('timeout: stopping')
            lines = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{')]
            rep = [l for l in lines if 'rep' in l]
            w = len((out/'rb').read_bytes())//4 if (out/'rb').exists() else 0
            ok = res.returncode == 0 and w and sim_gate.oracle_ok(list(struct.unpack(f'<{w}I', (out/'rb').read_bytes())), 32, 0x12345678)
            if not ok:
                state['runs'].append({'variant': v, 'trial': trial, 'ok': False, 'stdout': res.stdout.decode()[-400:]}); save()
                sys.exit('stopping on failure')
            tab = array.array('I', tout.read_bytes())
            ev = array.array('Q', eout.read_bytes())
            state['runs'].append({'variant': v, 'trial': trial, 'ok': True, 'fw_ts': rep[0]['fw_ts'],
                                  'echo_seen': [int(x) for x in ev[1::2]], 'tokens_seen': [int(x) for x in ev[0::2]],
                                  'R': [int(x) for x in tab[RBASE:RBASE+2*a.n]], 'final_T': int(tab[T])})
            save()
            print(json.dumps({'variant': v, 'trial': trial, 'ok': True, 'fw_us': (rep[0]['fw_ts'][1]-rep[0]['fw_ts'][0])/1e3,
                              'tokens_seen_by_cpu': len(ev)//2, 'final_T': int(tab[T])}), flush=True)


if __name__ == '__main__':
    sys.exit(main())
