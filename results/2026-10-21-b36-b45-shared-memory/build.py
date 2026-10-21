# B36 / B45 kernels (both checked in agx_run):
#   reader.bin  r2 = table[gid] (u8_u9 + 4 gid), stored at out[8 + gid]
#   writer.bin  B6's loop (TRIPS trips of 8 dependent iadds), then out[8 + gid] = WANT in every lane
import sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
e = lambda *a: agx_loop.encode(*a)
b = e('device_load 0, i32, x, r6, u8_u9, r1, unsigned') + e('wait 0') + e('iadd r2, r6, 0')
cov.gate(b); code = drm.build_main(b)
t = [0x5000 + i for i in range(64)]
out, _ = cov.simulate(code, 64, 32, 32, 0, t)
assert all(out[8 + i] == 0x5000 + i for i in range(64))
open('/scratch/agxsim-runs/b36/reader.bin', 'wb').write(code)
small, want_small = agx_loop.loop_body(1000, 8)
out, _ = cov.simulate(drm.build_main(small), 64, 32, 16, 0, [0] * 16)
assert all(w == want_small for w in out[8:8 + 64])
body, want = agx_loop.loop_body(200000, 8)
assert len(body) == len(small)
open('/scratch/agxsim-runs/b36/writer.bin', 'wb').write(drm.build_main(body))
print('ok writer want', hex(want))
