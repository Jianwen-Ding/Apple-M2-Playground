#!/usr/bin/env python3
"""Bisect the instruction-cache capacity edge: the largest loop body (bytes, multiple of the instruction size) that still
runs at the in-cache rate (within 3% of the 4 KB baseline), for one kind and loop-start pad. Uses probe_icache.py runs
(emulator + simulator gated, oracle-checked). Clock keeper must be running.
  probe_icache_edge.py --kind iadd8 --pad 0 [--lo 8192 --hi 16384] [--result FILE]
"""
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ns(kind, pad, size, out):
    r = subprocess.run([sys.executable, '-B', str(HERE/'probe_icache.py'), '--kind', kind, '--pad', str(pad), '--sizes', str(size),
                        '--repeats', '3', '--instr', '3000000', '--result', str(out)], capture_output=True, text=True, timeout=600)
    if r.returncode:
        sys.exit(r.stdout[-400:]+r.stderr[-400:])
    rows = json.loads(out.read_text())['rows']
    assert rows[0]['ok']
    fw = sorted(rows[0]['fw_ns'])[1]
    return fw/(rows[0]['body_instr']*rows[0]['trips'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', default='iadd8')
    p.add_argument('--pad', type=int, default=0)
    p.add_argument('--lo', type=int, default=8192)
    p.add_argument('--hi', type=int, default=16384)
    p.add_argument('--result', type=Path)
    a = p.parse_args()
    w = {'iadd8': 8, 'and6': 6, 'mov4': 4}[a.kind]
    tmp = Path('/scratch/apple-m2-playground/drm-compute/icache/edge-tmp.json')
    base = ns(a.kind, a.pad, 4096//w*w, tmp)
    lo, hi = a.lo//w*w, a.hi//w*w
    probes = {}
    assert ns(a.kind, a.pad, lo, tmp) <= base*1.03, 'lo already misses'
    while hi - lo > w:                              # invariant: lo fits, hi misses (checked lazily)
        mid = (lo+hi)//2//w*w
        t = ns(a.kind, a.pad, mid, tmp); probes[mid] = t
        if t <= base*1.03:
            lo = mid
        else:
            hi = mid
    rec = {'kind': a.kind, 'pad': a.pad, 'instr_bytes': w, 'baseline_ns': base, 'edge_fits': lo, 'edge_misses': hi, 'probes': probes}
    print(json.dumps(rec), flush=True)
    if a.result:
        a.result.write_text(json.dumps(rec)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
