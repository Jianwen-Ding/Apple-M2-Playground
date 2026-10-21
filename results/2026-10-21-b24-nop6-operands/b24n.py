#!/usr/bin/env python3
"""B24 item 6: are the 31 six-byte low-0b11 opcodes (0x03, 0x07, ... 0x7f without 0x6f) still no-ops with operand bytes
2-5 other than the recorded 38 00 62 40? Each opcode's recorded 'base' halfword with 8 new operand patterns (all zeros,
all ones, 6 seeded random), in the coverage suite's alu_body (r14 = r15 = 0xdeadbeef before; the oracle: both reach the
table and r2 unchanged, nothing else written). Every program runs in agx_run first. Usage: b24n.py sim|gpu"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import coverage as cov, coverage_catalog as CC, record_suite as RS, run_drm_compute as drm
cov.install()
N, WG = CC.N, CC.WG
mode = sys.argv[1]
rng = random.Random('b24-nop6')
pats = [bytes(4), b'\xff' * 4] + [bytes(rng.getrandbits(8) for _ in range(4)) for _ in range(6)]
if mode == 'gpu':
    import run_bench as B, gpu_safety
    R = B.Runner(Path('/scratch/agxsim-runs/b24n/run'))
res, bad = {}, 0
for op in CC.UNDECODED_NOP6:
    base = CC.undecoded_encodings(op)['base'].to_bytes(2, 'little')
    for k, p in enumerate(pats):
        instr = base + p
        tr = random.Random(f'b24n:{op}:{k}')
        table = [RS.operand(tr) for _ in range(8 * N)] + [0] * (2 * N)
        body = RS.alu_body(instr, N, False)
        code = drm.build_main(body)
        ok = lambda out, tab: out[8:8 + N] == [0xdeadbeef] * N and tab[8 * N:] == [0xdeadbeef] * (2 * N)
        so, st = cov.simulate(code, N, WG, 64, 0, table)
        assert ok(so, st), f'simulator: {instr.hex()} is not a no-op'
        if mode == 'gpu':
            gpu_safety.require_budget(1)
            out, tab, fw, _ = RS.run(R, code, N, WG, table, 64)
            good = ok(out, tab)
            bad += not good
            res[instr.hex()] = {'nop': good, 'fw_ns': fw}
            if not good:
                res[instr.hex()]['r14'] = [hex(x) for x in tab[8 * N:8 * N + 4]]
                print('NOT A NOP', instr.hex(), res[instr.hex()], flush=True)
        else:
            res[instr.hex()] = {'nop': True}
print(json.dumps({'mode': mode, 'forms': len(res), 'not_nop': bad}))
Path(f'{mode}.json').write_text(json.dumps(res, indent=0) + '\n')
