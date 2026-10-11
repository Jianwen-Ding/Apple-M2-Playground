#!/usr/bin/env python3
"""Summarize run_drm_sync_probe.py records (offline).

memwait: each candidate job is compared with the reference jobs right before and after it
(same memory op, candidate removed). A pair is kept only if both references agree within
2% (no clock-state change in between); the result is the extra time per loop iteration,
in ns and as a fraction of the reference iteration.
"""
import json
from pathlib import Path
import statistics
import sys


def memwait(results):
    med = [(r['name'], statistics.median(r['fw_ns']), r) for r in results]
    out = {}
    for i, (name, t, r) in enumerate(med):
        if name.endswith('-ref') or i == 0 or i+1 >= len(med): continue
        (pn, pt, _), (nn, nt, _) = med[i-1], med[i+1]
        if not (pn.endswith('-ref') and nn.endswith('-ref') and pn == nn): continue
        ref = (pt+nt)/2
        if abs(pt-nt)/ref > 0.02: continue
        trips = r.get('trips', 2000)
        out.setdefault(name, []).append({'extra_ns_per_iter': round((t-ref)/trips, 1), 'rel': round(t/ref, 3), 'ref_us': round(ref/1e3)})
    return out


def floor(results, trips):
    """Long dispatches settle at a hard floor and interference only adds time, so each job's
    cost is the minimum over all its submissions; candidates are compared with the
    same-group reference floor."""
    mins = {}
    for r in results:
        if r['fw_ns']: mins[r['name']] = min(mins.get(r['name'], 1 << 62), min(r['fw_ns']))
    out = {}
    for name, t in mins.items():
        if name.endswith('-ref'): continue
        ref = mins.get(name.rsplit('-', 1)[0]+'-ref')
        if name.startswith('memwait-'): ref = mins.get('-'.join(name.split('-')[:2])+'-ref')
        if ref: out[name] = {'floor_us': round(t/1e3, 1), 'ref_us': round(ref/1e3, 1), 'extra_ns_per_iter': round((t-ref)/trips, 2)}
    return out


def main():
    d = json.loads(Path(sys.argv[1]).read_text())
    if d['suite'] in ('memwait', 'scope'):
        print(json.dumps(floor(d['results'], d['trips']) if d['trips'] >= 20000 else memwait(d['results']), indent=1))


if __name__ == '__main__':
    main()
