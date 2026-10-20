# B1 step 2 kernel: stack_adjust, then per thread store A=3i+1 at scratch byte 0 and B=5i+7 at byte 4,
# clobber both registers, reload them and output A+B = 8i+8. Every form is one Mesa emitted (2026-10-18-stack-mesa).
import subprocess, sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import run_drm_compute as r
A = '/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_asm'
def asm(lines):
    out = subprocess.run([A], input='\n'.join(lines) + '\n', capture_output=True, text=True, check=True).stdout.split('\n')
    bad = [l for l in out if l.startswith('ERROR')]
    assert not bad, bad
    return bytes.fromhex(''.join(l.split('\t')[0] for l in out if l.strip()))
adjust = bytes.fromhex('b500010525800000')  # Mesa's exact 'stack_adjust #80' (spill shader)
body = asm([
    'imadd r3, r1.sx, 3, 1',
    'stack_store i32, 1, 0, x, 4, r3, 0, 0',
    'imadd r4, r1.sx, 5, 7',
    'stack_store i32, 1, 0, x, 4, r4, 4, 1',
    'wait 0', 'wait 1',
    'mov_imm r3, 0, 0b0', 'mov_imm r4, 0, 0b0',
    'stack_load r3, i32, 1, 0, x, 4, 0, 0',
    'stack_load r4, i32, 1, 0, x, 4, 4, 1',
    'wait 0', 'wait 1',
    'iadd r2, r3.sx, r4.sx',
])
code = adjust + r.build_main(body)
open('scratch_rt.bin', 'wb').write(code)
d = subprocess.run([A], input='!' + code.hex() + '\n', capture_output=True, text=True).stdout
print(d.replace(' | ', '\n'))
