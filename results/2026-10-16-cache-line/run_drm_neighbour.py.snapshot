#!/usr/bin/env python3
"""Cache line size per level by the "is the neighbour free?" test (simulator task safe-03 step 1), direct DRM.

Elements are 1 KiB apart and visited in a random single cycle. Each hop makes two dependent loads:
  r5 = T[r2]            (word at the element start; holds 0)
  r6 = r2 + r5 + d/4    (depends on the first load)
  r2 = T[r6]            (word at offset d holds the next element's index)
If offset d is in the line the first load brought in, the second load hits; once d reaches the line size it misses
too, and the hop cost rises by one access latency. Element counts set the level: 64 (64 KiB span, L1-sized lines),
1,024 (L2), 65,536 (64 MiB span: SLC / DRAM). Many passes per dispatch keep the level warm. Run with
scripts/clock_keeper.py in the background. Every kernel + table passes sim_gate (agx_run) first.
"""
import argparse, array, datetime, json, os, random, shlex, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import agx_loop, gpu_safety, sim_gate  # noqa: E402
import run_drm_compute as drm  # noqa: E402

ELEM = 1024  # bytes between elements


def table(n, d, seed=1):
    rng = random.Random(seed)
    order = list(range(n))
    for i in range(n-1, 0, -1):
        j = rng.randrange(i); order[i], order[j] = order[j], order[i]
    w = ELEM//4
    t = array.array('I', [0xffffffff])*(n*w)
    for i in range(n):
        t[i*w] = 0                      # first load's word
        t[i*w+d//4] = order[i]*w        # next element (word index)
    return t


def oracle(t, hops, d):
    x = 0
    for _ in range(hops):
        x = t[x+t[x]+d//4]
    return x


def body(trips, d):
    enc, mov = agx_loop.encode, agx_loop.chains.mov_imm
    head = mov(3, 0)+mov(4, trips)+mov(2, 0)+mov(7, d//4)+enc('if_fcmp r0l, eq, 0.0, 0.0, 1', 'push_exec r0l, 1')
    loop = enc('device_load 0, i32, x, r5, u8_u9, r2, unsigned')+enc('wait 0')
    loop += enc('iadd r6, r2, r5')+enc('iadd r6, r6, r7')
    loop += enc('device_load 0, i32, x, r2, u8_u9, r6, unsigned')+enc('wait 0')
    loop += enc('iadd r3, 1, r3.sx')+enc('while_icmp r0l, ult, r3, r4, 1')
    jump = enc(f'jmp_exec_any pc-{len(loop)}', f'jmp_exec_any pc-{len(loop)}')
    return head+loop+jump+enc('pop_exec r0l, 1')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elements', default='64,1024,65536')
    p.add_argument('--offsets', default='4,16,32,48,60,64,96,124,128,192,256,384,508,512')
    p.add_argument('--hops', type=int, default=200000)
    p.add_argument('--repeats', type=int, default=4)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    els = [int(x) for x in a.elements.split(',')]; offs = [int(x) for x in a.offsets.split(',')]
    if not (all(2 <= n <= 1 << 18 for n in els) and all(4 <= d < ELEM and d % 4 == 0 for d in offs) and 1 <= a.hops <= 1 << 22):
        sys.exit('refusing: bounded elements / offsets / hops required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/neighbour')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    state = {'utc': stamp, 'hops': a.hops, 'repeats': a.repeats, 'elem_bytes': ELEM,
             'power_ac': Path('/sys/class/power_supply/macsmc-ac/online').read_text().strip(), 'runs': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    for n in els:
        for d in offs:
            t = table(n, d); tp = out/'t.bin'; tp.write_bytes(t.tobytes())
            code = drm.build_main(body(a.hops, d)); want = oracle(t, a.hops, d)
            gate = sim_gate.require(code, 32, want, regs=16, table=tp)
            gpu_safety.require_budget(1)
            (out/'k.bin').write_bytes(code+bytes(16))
            try:
                res = subprocess.run([str(exe), a.device, str(out/'k.bin'), '32', str(out/'rb'), str(a.repeats), '16', str(tp)],
                                     capture_output=True, timeout=120)
            except subprocess.TimeoutExpired:
                gpu_safety.record(f'run_drm_neighbour {n}/{d}: timeout'); save(); sys.exit('timeout: stopping')
            reps = [json.loads(l) for l in res.stdout.decode().splitlines() if l.startswith('{"rep"')]
            w = len((out/'rb').read_bytes())//4 if (out/'rb').exists() else 0
            ok = res.returncode == 0 and w and sim_gate.oracle_ok(list(struct.unpack(f'<{w}I', (out/'rb').read_bytes())), 32, want)
            fw = [q['fw_ts'][1]-q['fw_ts'][0] for q in reps]
            state['runs'].append({'elements': n, 'offset': d, 'oracle_ok': bool(ok), 'fw_ns': fw, 'simulator': gate}); save()
            print(json.dumps({'elements': n, 'offset': d, 'ok': bool(ok), 'ns_per_hop': [round(x/a.hops, 1) for x in fw]}), flush=True)
            if not ok:
                sys.exit('stopping on failure')
            tp.unlink()


if __name__ == '__main__':
    sys.exit(main())
