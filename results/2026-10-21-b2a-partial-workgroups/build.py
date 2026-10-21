# B2a kernel: control prefix/suffix; body: every lane atomically adds 1 to table word 0; r2 = gid (stored at out[8 + gid]).
import sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop, run_drm_atomic as DA
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
b = mov(15, 1) + mov(5, 0) + DA.atomic(0, 0, 5, 15, False) + e('wait 0') + e('iadd r2, r1, 0')
cov.gate(b); code = drm.build_main(b)
out, tab = cov.simulate(code, 96, 32, 32, 0, [0] * 16)
assert tab[0] == 96 and all(out[8 + i] == i for i in range(96)), (tab[0], out[8:12])
open('/scratch/agxsim-runs/b2a/count.bin', 'wb').write(code)
print('ok', len(code))
