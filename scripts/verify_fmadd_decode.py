#!/usr/bin/env python3
"""Offline: the simulator decoder walks every retained fmadd candidate program on exact instruction boundaries.

No GPU access. Each `cand` of results/2026-10-11-alu-bitflip/fma*.json.gz is disassembled with the simulator's
`agx_asm` (`!HEX`). The walk must end exactly at the program end with no undecodable byte, and an fmadd32/fmadd16
decodes as the 10-byte `*_lane` form exactly when bit 53 of its first 8 bytes is set (8 bytes without).
"""
import glob
import gzip
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ASM = ROOT.parent/'AGX-Performance-Simulator/rust/target/release/agx_asm'
fails = []
n_prog = n_lane = n_plain = n_ext = 0

progs = []
for f in sorted(glob.glob(str(ROOT/'results/2026-10-11-alu-bitflip/fma*.json.gz'))):
    for r in json.load(gzip.open(f))['results']:
        progs.append((Path(f).name[:-8], r['name'], r['cand']))
uniq = sorted({p[2] for p in progs})
out = subprocess.run([str(ASM)], input=''.join('!%s\n' % h for h in uniq), capture_output=True, text=True, check=True).stdout.splitlines()
assert len(out) == len(uniq)
dis = dict(zip(uniq, out))

for src, name, hx in progs:
    n_prog += 1
    d = dis[hx]
    if d.startswith('ERROR'):
        # A bare fragment whose last instruction is a lane form needs 2 bytes the wrapper code supplies on hardware.
        at = int(d.split()[2][:-1]) if d.startswith('ERROR at') else -1
        if d.endswith('_lane truncated') and len(hx)//2 - at < 10 and (int.from_bytes(bytes.fromhex(hx)[at:at+8], 'little') >> 53) & 1:
            n_ext += 1
        else:
            fails.append((src, name, d))
        continue
    pos = 0
    for part in d.split(' | '):
        nm, size = part.split(' ')[:2]
        size = int(size)
        if nm.startswith(('fmadd32', 'fmadd16')):
            b53 = (int.from_bytes(bytes.fromhex(hx)[pos:pos+8], 'little') >> 53) & 1
            lane = nm.endswith('_lane')
            if lane != bool(b53) or size != (10 if lane else size) or (not lane and size not in (6, 8)):
                fails.append((src, name, 'fmadd at %d decoded %s/%d with bit53=%d' % (pos, nm, size, b53)))
            n_lane += lane
            n_plain += not lane
        pos += size
    if pos != len(hx)//2:
        fails.append((src, name, 'walk ends at %d of %d' % (pos, len(hx)//2)))

print('programs %d, lane-form fmadds %d, plain fmadds %d, fragments extending into wrapper %d' % (n_prog, n_lane, n_plain, n_ext))
for x in fails[:20]:
    print('FAIL', *x)
print('PASS' if not fails and n_lane else 'FAIL', 'fmadd decode boundaries')
sys.exit(1 if fails or not n_lane else 0)
