# B9 kernels: thread i outputs i + u_K (32-bit uniform K) for K in KS.
import subprocess, sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import run_drm_compute as r
A = '/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_asm'
for K in (69, 127, 128, 255):
    h = subprocess.run([A], input=f'iadd r2, r1.sx, u{K}.sx\n', capture_output=True, text=True, check=True).stdout.split('\t')[0].strip()
    open(f'u{K}.bin', 'wb').write(r.build_main(bytes.fromhex(h)))
