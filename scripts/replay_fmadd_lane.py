#!/usr/bin/env python3
"""Replay retained fmadd bit-flip programs (results/2026-10-11-alu-bitflip/fma*.json.gz) in the Rust simulator.

No GPU access. Every record's candidate is rebuilt with run_drm_bitflip.build() (the exact harness program), run in
agx_run with the table layout the hardware run used, and compared word for word with the recorded table.
Outcomes: match, lane16-hazard (only lanes 16..16+k-1 differ: the measured cross-half write-distance/layout dependence),
mismatch (a model disagreement; fails), unsupported (the model refuses the form, by design).
Records known to be placement/hazard dependent on hardware (cross-half reads right after a write) are listed
separately; they are expected to mismatch because the model assumes the source was written long before the read.
"""
import argparse
import collections
import glob
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_drm_bitflip as B  # noqa: E402
import run_drm_compute as drm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SIMREPO = Path(os.environ.get('SIMREPO', ROOT.parent/'AGX-Performance-Simulator'))
RUN = SIMREPO/'rust/target/release/agx_run'
DATA_VA = 0x1100000000
COUNT, SLOTS = 32, B.D.SLOTS


def pack(words):
    return struct.pack(f'<{len(words)}I', *words)


def simulate(code, gprs):
    words = 8 + COUNT + 8 + 16
    out_va = DATA_VA+0x8000
    table_va = DATA_VA+max(1 << 20, (0x8000+words*4+16383)//16384*16384)
    table_in = [B.D.SENTINEL]*(SLOTS*COUNT)
    with tempfile.TemporaryDirectory(prefix='agx-fmadd-replay-') as t:
        t = Path(t)
        (t/'c.bin').write_bytes(code+bytes(16))
        (t/'o.bin').write_bytes(pack([0xcdcdcdcd]*(words-16)+[0xa5a50000+i for i in range(16)]))
        (t/'t.bin').write_bytes(pack(table_in))
        args = [str(RUN), str(t/'c.bin'), '--grid', f'{COUNT},1,1', '--wg', f'{COUNT},1,1', '--regs', str(gprs), '--shared', '0']
        for reg, value in [(4, 0), (5, COUNT), (6, out_va & 0xffffffff), (7, out_va >> 32), (8, table_va & 0xffffffff), (9, table_va >> 32)]:
            args += ['--uniform', f'{reg}={value}']
        args += ['--map', f'{out_va:#x}={t/"o.bin"}', '--map', f'{table_va:#x}={t/"t.bin"}',
                 '--dump', f'{table_va:#x}={4*len(table_in)}:{t/"ta.bin"}',
                 '--alloc-regs', str(max(8, (gprs+7)//8*8)), '--vm-slot', '0', '--pipeline', '4096']
        r = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise RuntimeError((r.stdout+r.stderr).strip()[-200:].replace('\n', ' '))
        data = (t/'ta.bin').read_bytes()
        w = struct.unpack(f'<{len(data)//4}I', data)
        return [list(w[s*COUNT:(s+1)*COUNT]) for s in range(SLOTS)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    res = collections.Counter()
    detail = collections.defaultdict(list)
    for f in sorted(glob.glob(str(ROOT/'results/2026-10-11-alu-bitflip/fma*.json.gz'))):
        rec = json.load(gzip.open(f))
        gprs = rec['gprs']
        for r in rec['results']:
            if r.get('fault') or 'table' not in r:
                continue
            body, _ = B.build(bytes.fromhex(r['cand']), r['layout'])
            tag = f"{Path(f).name[:-8]}/{r['name']}"
            try:
                got = simulate(drm.build_main(body), gprs)
            except RuntimeError as e:
                res['unsupported'] += 1
                detail['unsupported'].append((tag, str(e)))
                continue
            # slot 1 is r0 (mask-depth register): the hardware value is not modeled, so it is not compared
            if [g for i, g in enumerate(got) if i != 1] == [t for i, t in enumerate(r['table']) if i != 1]:
                res['match'] += 1
            else:
                diff = [(i, l) for i, (gs, rs) in enumerate(zip(got, r['table'])) if i != 1 for l, (x, y) in enumerate(zip(gs, rs)) if x != y]
                k = int.from_bytes(bytes.fromhex(r['cand'])[-2:], 'little') >> 11   # bits 75-79 of the lane form closing the candidate
                if diff and r['flip'] and all(16 <= l < 16+max(k, 1) for _, l in diff):
                    res['lane16-hazard'] += 1   # cross-half read: hardware value depends on write distance / following code
                    detail['hazard'].append((tag, len(diff)))
                else:
                    res['mismatch'] += 1
                    detail['mismatch'].append((tag, len(diff)))
    print(dict(res))
    reasons = collections.Counter(e.split(':', 2)[-1].strip()[:90] for _, e in detail['unsupported'])
    for k, v in reasons.most_common():
        print('  unsupported x%d: %s' % (v, k))
    for tag, n in (detail['mismatch'] if a.verbose else detail['mismatch'][:25]):
        print('  MISMATCH', tag, '%d words' % n)
    return 1 if res['mismatch'] else 0


if __name__ == '__main__':
    sys.exit(main())
