# B32 kernels: control (5.6 us class) and counter (thread 0: load table[0], +1, store; non-atomic, so overlapping or
# unordered commands lose increments).
import sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
ctl = drm.build_main(e('mov_imm r2, 305419896, 0b0'))
b = mov(27, 0) + mov(5, 0) + e('if_icmp r0l, ueq, r1, r27, 1') + e('device_load 0, i32, x, r10, u8_u9, r5, unsigned') + e('wait 0')
b += mov(26, 1) + e('iadd r10, r10, r26') + agx_loop.store(10, 8, 5) + e('wait 0') + e('pop_exec r0l, 1') + e('iadd r2, r1, 0')
cov.gate(b); cnt = drm.build_main(b)
out, tab = cov.simulate(cnt, 32, 32, 32, 0, [0] * 16); assert tab[0] == 1
open('/scratch/agxsim-runs/b32/control.bin', 'wb').write(ctl + b'\0' * 64)
open('/scratch/agxsim-runs/b32/counter.bin', 'wb').write(cnt + b'\0' * 64)
open('/scratch/agxsim-runs/b32/table.bin', 'wb').write(b'\0' * 64)
print('ok')
