#!/usr/bin/env python3
"""Offline checks of the Mesa-compiled stack / spill shaders (results/2026-10-18-stack-mesa). Simulator replay unless --no-sim."""
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_gles_stack2 as G  # noqa: E402
D = ROOT/'results/2026-10-18-stack-mesa'
ASM = ROOT.parent/'AGX-Performance-Simulator/rust/target/release/agx_asm'
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def walk(path):
    h = path.read_bytes().hex()
    out = subprocess.run([str(ASM)], input='!'+h+'\n', capture_output=True, text=True).stdout.strip()
    if out.startswith('ERROR'):
        return None, len(h)//2
    ins = [p.split(' ', 2) for p in out.split(' | ')]
    return ins, len(h)//2


names = ['spill', 'priv_u', 'priv_v4', 'priv_f', 'priv_h']
meta = {n: json.load((D/n/'meta.json').open()) for n in names}
for n in names:
    got = list(struct.unpack('<%dI' % (8+64+8), (D/n/'output.bin').read_bytes()))
    want = [G.SHADERS[n][1](i) for i in range(64)]
    check(f'{n}: Mesa GLES hardware output equals the host model on all 64 lanes, guard words intact',
          got[8:72] == want and all(x == 0xcdcdcdcd for x in got[:8]) and all(x == 0xcdcdcdcd for x in got[72:]))
census = {}
for n in names:
    ins, size = walk(D/n/'main.bin')
    pre, psize = walk(D/n/'preamble.bin')
    total = sum(int(i[1]) for i in ins) if ins else -1
    check(f'{n}: main shader ({size} B) and preamble ({psize} B) decode on exact instruction boundaries to their last byte, no undecodable byte',
          ins is not None and pre is not None and total == size and sum(int(i[1]) for i in pre) == psize)
    census[n] = [(i[0], i[2]) for i in ins if i[0].startswith('stack')]
sp = census['spill']
adj = [t for m, t in sp if t.startswith('stack_store i8')]
st = [t for m, t in sp if m == 'stack_store' and ' i32,' in t and 'i8' not in t]
ld = [t for m, t in sp if m == 'stack_load']
check('spill (192 live values, 255 registers): %d spill stores and %d fills, all i32 x with an immediate byte offset' % (len(st), len(ld)),
      len(st) == 70 and len(ld) == 70 and len(adj) == 1)
offs = sorted(int(re.search(r', r\d+, (\d+), \d$', t).group(1)) for t in st)
check('spill offsets are 4-byte multiples from 0 to 276 (70 distinct slots), loads use the same offsets',
      offs == list(range(0, 280, 4)) and sorted(int(re.search(r', (\d+), \d$', t).group(1)) for t in ld) == offs)
forms = {n: {re.sub(r'r\d+(l|h)?(_r\d+(l|h)?)*', 'rN', t) for m, t in census[n]} for n in names[1:]}
check('private arrays use a byte-offset register (not an immediate): priv_u / priv_f i32 x, priv_v4 i32 xyzw (128-bit r4_r5_r6_r7), priv_h i16 x (mediump -> 16-bit)',
      any('i32, 1, 0, x, 4, rN, rN, 0' in t for t in forms['priv_u']) and any('xyzw' in t for t in forms['priv_v4'])
      and any('stack_store i16, 1, 0, x, 4, rN, rN, 0' in t for t in forms['priv_h']) and any('i32, 1, 0, x' in t for t in forms['priv_f']))
align4 = lambda x: (x+3)//4*4
adj_words = {n: int(re.search(r'i8, 1, 2, 0, (\d+), 0', next(t for m, t in census[n] if 'i8' in t)).group(1)) for n in names}
check('stack_adjust words = align(ceil(scratch_bytes / 4) + 10, 4) for all 5 shaders (80, 1036, 268, 524, 524)',
      all(adj_words[n] == align4(-(-meta[n]['stats']['scratch']//4)+10) for n in names) and [adj_words[n] for n in names] == [80, 1036, 268, 524, 524])
if '--no-sim' not in sys.argv:
    import replay_mesa_stack as R
    for n in names:
        got, info = R.replay(D/n, 64)
        hw = list(struct.unpack('<%dI' % len(got), (D/n/'output.bin').read_bytes()))
        check(f'{n}: Rust simulator replay (preamble + main, stack memory per lane) equals the hardware output word for word', got == hw)
sys.exit(0 if all(ok) else 1)
