# B44 programs (whole programs, control prefix / suffix): control.bin (the control kernel), deadlock.bin (B26's
# 1,024-thread / 112-halves kernel with a threadgroup barrier: over the register budget, it deadlocks until the firmware
# ends it after ~0.5 s). The barrier-free variant of deadlock.bin is checked in agx_run (the simulator cannot model
# the residency deadlock); B26 ran exactly this program on the GPU.
import sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, record_suite as RS, run_drm_compute as drm, agx_loop
cov.install()
mov = RS.mov; e = lambda *a: agx_loop.encode(*a)
ctrl = drm.build_main(b'')
out, _ = cov.simulate(ctrl, 256, 32, 16, 0, [0] * 16)
open('/scratch/agxsim-runs/b44/control.bin', 'wb').write(ctrl)
top = 112 // 2 - 1
nobar = mov(28, 0x3c3c0000) + e(f'xor r{top}, r1, r28') + e('wait 0') + e(f'iadd r2, r{top}, 0')
bar = mov(28, 0x3c3c0000) + e(f'xor r{top}, r1, r28') + e('wait 0') + bytes.fromhex('6800') + e(f'iadd r2, r{top}, 0')
out, _ = cov.simulate(drm.build_main(nobar), 1024, 1024, 112, 0, [0] * 16)
assert all(out[8 + i] == i ^ 0x3c3c0000 for i in range(1024))
open('/scratch/agxsim-runs/b44/deadlock.bin', 'wb').write(drm.build_main(bar))
print('ok control', ctrl[22:28].hex())
