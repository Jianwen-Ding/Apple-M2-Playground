#!/usr/bin/env python3
"""B43: how commands of two VMs (two processes) share the GPU. LONG = B6's loop (8 dependent iadds per trip) in every
thread of COUNT lanes (128-lane workgroups, 16 register halves: 96 SIMD groups per core, every slot full at 116,736
lanes); SHORT = the same loop with 1,000 trips in one SIMD group. Each process is drm_compute (its own VM and queue);
firmware timestamps share one GPU timebase. Usage:
  b43.py gate                      the 1,000-trip program in agx_run
  b43.py one TRIPS COUNT           one LONG alone
  b43.py pair TRIPS COUNT DELAY_MS MODE   LONG in process A, after DELAY_MS process B runs SHORT (MODE short) or LONG (MODE long)"""
import json, os, struct, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, run_drm_compute as drm, agx_loop
cov.install()
EXE = '/scratch/agxsim-runs/b1/drm_compute'
D = Path('/scratch/agxsim-runs/b43')

def program(trips):
    body, want = agx_loop.loop_body(trips, 8)
    return drm.build_main(body) + b'\x00' * 64, want

def start(name, trips, count, local):
    code, want = program(trips)
    d = D / name; d.mkdir(parents=True, exist_ok=True); (d / 'code.bin').write_bytes(code)
    env = dict(os.environ, AGX_WAIT_MS='60000', AGX_LOCAL_X=str(local))
    return subprocess.Popen([EXE, '/dev/dri/renderD128', str(d / 'code.bin'), str(count), str(d / 'out.bin'), '1', '16'],
                            stdout=subprocess.PIPE, text=True, env=env), d, want, count

def finish(p):
    proc, d, want, count = p
    out, _ = proc.communicate(timeout=120)
    rep = next((json.loads(l) for l in out.splitlines() if l.startswith('{"rep"')), {})
    w = struct.unpack('<%dI' % (os.path.getsize(d / 'out.bin') // 4), open(d / 'out.bin', 'rb').read())
    ok = all(x == want for x in w[8:8 + count])
    ts = rep.get('fw_ts') or [0, 0]
    return {'rc': proc.returncode, 'ok': ok, 'start': ts[0], 'end': ts[1], 'ms': (ts[1] - ts[0]) / 1e6}

def main():
    mode = sys.argv[1]
    if mode == 'gate':
        small, want = agx_loop.loop_body(1000, 8)
        out, _ = cov.simulate(drm.build_main(small), 256, 128, 16, 0, [0] * 16)
        assert all(w == want for w in out[8:8 + 256]); print('gate ok'); return
    import gpu_safety; gpu_safety.require_budget(1)
    trips, count = int(sys.argv[2]), int(sys.argv[3])
    if mode == 'one':
        print(json.dumps({'one': finish(start('a', trips, count, 128))})); return
    delay, kind = int(sys.argv[4]) / 1e3, sys.argv[5]
    a = start('a', trips, count, 128); time.sleep(delay)
    b = start('b', 1000, 32, 32) if kind == 'short' else start('b', trips, count, 128)
    ra, rb = finish(a), finish(b)
    rel = lambda r: {**r, 'start_rel_ms': (r['start'] - ra['start']) / 1e6, 'end_rel_ms': (r['end'] - ra['start']) / 1e6}
    print(json.dumps({'kind': kind, 'delay_ms': delay * 1e3, 'a': rel(ra), 'b': rel(rb)}))

if __name__ == '__main__':
    main()
