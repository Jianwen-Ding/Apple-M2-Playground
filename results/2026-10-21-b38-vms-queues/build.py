# B38/B43 kernel: every lane atomically adds 1 to table word 0; r2 = SR21 (VM slot; agx_run's --vm-slot 0), stored at out[8 + gid].
import sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
sys.path.insert(0, '/save/workspace/apple-documentation-playground/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop, run_drm_atomic as DA
import run_drm_sr_scan as scan
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
b = mov(15, 1) + mov(5, 0) + DA.atomic(0, 0, 5, 15, False) + e('wait 0') + scan.get_sr(21, 2)
cov.gate(b); code = drm.build_main(b)
out, tab = cov.simulate(code, 64, 32, 32, 0, [0] * 16)
assert tab[0] == 64 and all(out[8 + i] == 0 for i in range(64)), (tab[0], out[8:12])
open('/scratch/agxsim-runs/b38/sr21count.bin', 'wb').write(code)
print('ok', len(code))
