#!/usr/bin/env python3
"""B6: one SIMD group runs agx_loop.loop_body(TRIPS, 8) (8 dependent iadds per trip; output = preload + 8 * TRIPS).
The same program with 1,000 trips is checked in agx_run first (only the trip-count immediate differs).
Usage: b6.py TRIPS [WAIT_MS]"""
import json, os, struct, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, run_drm_compute as drm, agx_loop
cov.install()
trips = int(sys.argv[1]); wait_ms = int(sys.argv[2]) if len(sys.argv) > 2 else 60000
small, want_small = agx_loop.loop_body(1000, 8)
out, _ = cov.simulate(drm.build_main(small), 32, 32, 16, 0, [0] * 16)
assert all(w == want_small for w in out[8:40]), 'gate'
body, want = agx_loop.loop_body(trips, 8)
assert len(body) == len(small)
import gpu_safety; gpu_safety.require_budget(1)
d = Path('/scratch/agxsim-runs/b6/run'); d.mkdir(parents=True, exist_ok=True)
(d / 'code.bin').write_bytes(drm.build_main(body) + b'\x00' * 64)
t0 = time.time()
r = subprocess.run(['/scratch/agxsim-runs/b1/drm_compute', '/dev/dri/renderD128', str(d / 'code.bin'), '32', str(d / 'out.bin'), '1', '16'],
                   capture_output=True, text=True, timeout=wait_ms / 1000 + 60, env=dict(os.environ, AGX_WAIT_MS=str(wait_ms)))
host = time.time() - t0
rep = next((json.loads(l) for l in r.stdout.splitlines() if l.startswith('{"rep"')), {})
w = struct.unpack('<%dI' % (os.path.getsize(d / 'out.bin') // 4), open(d / 'out.bin', 'rb').read()) if (d / 'out.bin').exists() else []
ok = bool(w) and all(x == want for x in w[8:40])
fw = (rep.get('fw_ts') or [0, 0])
res = {'trips': trips, 'rc': r.returncode, 'wait': rep.get('wait'), 'errno': rep.get('errno'), 'fw_ms': (fw[1] - fw[0]) / 1e6,
       'host_s': round(host, 3), 'output_ok': ok, 'stdout_tail': r.stdout[-200:] if r.returncode else ''}
if not ok or fw == [0, 0]: gpu_safety.record(f'B6 trips={trips}: {json.dumps(res)[:150]}')
print(json.dumps(res))
