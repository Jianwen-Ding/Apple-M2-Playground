# B22 kernel: control prefix/suffix; body: lanes with (gid & 31) == 0 atomically add 1 to table word 0; r2 = gid.
import sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop, run_drm_atomic as DA
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
b = mov(27, 31) + e('and r24, r1, r27') + mov(27, 0) + mov(15, 1) + mov(5, 0)
b += e('if_icmp r0l, ueq, r24, r27, 1') + DA.atomic(0, 0, 5, 15, False) + e('wait 0') + e('pop_exec r0l, 1') + e('iadd r2, r1, 0')
cov.gate(b); code = drm.build_main(b)
out, tab = cov.simulate(code, 256, 64, 32, 0, [0] * 16)
assert tab[0] == 8 and all(out[8 + i] == i for i in range(256)), (tab[0], out[8:12])
open('/scratch/agxsim-runs/b22/count.bin', 'wb').write(code)
print('ok', len(code))
