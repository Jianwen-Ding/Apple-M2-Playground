#!/usr/bin/env python3
"""Replay the Mesa-compiled stack / spill shaders (scripts/run_gles_stack2.py) in the Rust simulator, without a GPU.

Per shader the retained files are: main.bin, preamble.bin, the rodata words, the shader source, and the hardware output (from Mesa's
GLES driver). Uniform convention reconstructed from the captured code: u0_u1 = pointer to a root table whose first word is `count` (the
preamble loads it into u4), u2_u3 = output buffer address, rodata words at u<base_uniform/2> ... (Mesa maps `rodata` to a uniform base
in 16-bit halves). The output buffer is 8 sentinel words + count results + 8 sentinel words. A replay must equal the hardware output.
  replay_mesa_stack.py [--dir results/2026-10-18-stack-mesa]
"""
import argparse, json, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT.parent/'AGX-Performance-Simulator/rust/target/release/agx_run'
VA_OUT, VA_ROOT = 0x1100008000, 0x1100000000


def replay(d, count):
    meta = json.load((d/'meta.json').open())
    words = 8+((count+31)//32*32)+8
    with tempfile.TemporaryDirectory(prefix='agx-stack-replay-') as t:
        t = Path(t)
        (t/'out.bin').write_bytes(struct.pack(f'<{words}I', *([0xcdcdcdcd]*words)))
        (t/'root.bin').write_bytes(struct.pack('<4I', count, 0, 0, 0))
        argv = [str(RUN), str(d/'main.bin'), '--grid', f'{(count+31)//32*32},1,1', '--wg', '32,1,1', '--regs', str(meta['nr_gprs']*2 if meta['nr_gprs'] < 128 else 256),
                '--preamble', str(d/'preamble.bin'), '--uniform', '0=%d' % (VA_ROOT & 0xffffffff), '--uniform', '1=%d' % (VA_ROOT >> 32),
                '--uniform', '2=%d' % (VA_OUT & 0xffffffff), '--uniform', '3=%d' % (VA_OUT >> 32),
                '--map', f'{VA_OUT:#x}={t/"out.bin"}', '--map', f'{VA_ROOT:#x}={t/"root.bin"}', '--dump', f'{VA_OUT:#x}={4*words}:{t/"res.bin"}',
                '--alloc-regs', '256', '--vm-slot', '0', '--pipeline', '4096']
        for i, w in enumerate(meta['rodata_words']):
            argv += ['--uniform', f'{meta["rodata_uniform"]+i}={w}']
        r = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        if r.returncode:
            raise RuntimeError((r.stdout+r.stderr).strip()[-300:])
        return list(struct.unpack(f'<{words}I', (t/'res.bin').read_bytes())), json.loads(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dir', type=Path, default=ROOT/'results/2026-10-18-stack-mesa')
    a = ap.parse_args()
    bad = 0
    for d in sorted(p for p in a.dir.iterdir() if p.is_dir()):
        meta = json.load((d/'meta.json').open())
        got, info = replay(d, meta['count'])
        hw = list(struct.unpack(f'<{len(got)}I', (d/'output.bin').read_bytes()))
        ok = got == hw
        bad += not ok
        print(f"{d.name}: simulator output {'equals' if ok else 'DIFFERS from'} the hardware output ({meta['count']} lanes, {info.get('instructions')} instructions executed)")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
