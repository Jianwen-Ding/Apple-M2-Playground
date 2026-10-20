# B1 large-scratch kernel: Mesa's 'stack_adjust #1036' (priv_u), a register-offset store at byte 4000 and an
# immediate store at byte 0, which land in different 64 KiB blocks (block 0 and block 2). Output A+B = 8i+8.
import subprocess, sys
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import run_drm_compute as r
A = '/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_asm'
def asm(lines):
    out = subprocess.run([A], input='\n'.join(lines) + '\n', capture_output=True, text=True, check=True).stdout.split('\n')
    assert not [l for l in out if l.startswith('ERROR')], out
    return bytes.fromhex(''.join(l.split('\t')[0] for l in out if l.strip()))
adjust = bytes.fromhex('b500c10520800004')   # Mesa's exact 'stack_adjust #1036'
off = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
body = asm([
    'imadd r3, r1.sx, 3, 1',
    f'mov_imm r5, {off}, 0b0',
    'stack_store i32, 1, 0, x, 4, r3, r5, 0',
    'imadd r4, r1.sx, 5, 7',
    'stack_store i32, 1, 0, x, 4, r4, 0, 1',
    'wait 0', 'wait 1',
    'mov_imm r3, 0, 0b0', 'mov_imm r4, 0, 0b0',
    'stack_load r3, i32, 1, 0, x, 4, r5, 0',
    'stack_load r4, i32, 1, 0, x, 4, 0, 1',
    'wait 0', 'wait 1',
    'iadd r2, r3.sx, r4.sx',
])
open(f'scratch_big_{off}.bin', 'wb').write(adjust + r.build_main(body))
