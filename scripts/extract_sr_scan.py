#!/usr/bin/env python3
"""Reduce direct-DRM SR scan records (run_drm_sr_scan.py) to compact retained evidence.

Raw records hold 256 selectors x every lane and reach ~1 GB. For each config
this keeps: env, lanes, oracle/no-execution flags, firmware times, per-selector
distinct-value summaries, and per-SIMD-group values (first lane of each group)
for the selectors used in claims, plus whether each is uniform within every
SIMD group. No GPU access.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

KEEP = (0, 7, 17, 19, 20, 21, 24, 32, 53, 57, 59, 113)
PAIRS = (250, 251, 252, 253)   # main-shader SR20/17/0/24 stored beside preshader copies


def summarize(rec):
    out = {k: rec.get(k) for k in ('env', 'lanes', 'returncode', 'buffer_ok', 'inactive_untouched', 'executed_nothing', 'unwritten',
                                    'written_selectors', 'preamble_runs_by_core', 'atomic_counter', 'atomic_neighbours_untouched')}
    out['fw_ns'] = [s['fw_ts'][1]-s['fw_ts'][0] for s in rec.get('samples', [])]
    out['usc_words_hex'] = next((e['usc_words_hex'] for e in rec.get('setup', []) if 'usc_words_hex' in e), None)
    if 'values' not in rec or rec.get('executed_nothing'):
        return out
    vals = {int(k): v for k, v in rec['values'].items()}
    out['selectors'] = {}
    for s, v in vals.items():
        c = collections.Counter(v)
        out['selectors'][s] = {'distinct': len(c), 'top': [[x, n] for x, n in c.most_common(4)]}
    groups = range(0, len(vals[0]), 32)
    keep = KEEP+tuple(x for x in PAIRS if x in (rec.get('written_selectors') or []))
    out['per_simd_group'] = {s: [vals[s][i] for i in groups] for s in keep}
    if 250 in keep:
        out['preshader_sr20_equals_main_sr20_all_lanes'] = vals[20] == vals[250]
    out['uniform_within_simd_group'] = {s: all(len(set(vals[s][i:i+32])) == 1 for i in groups) for s in KEEP}
    out['sr17_equals_sr53_all_lanes'] = vals[17] == vals[53]
    by_core = collections.defaultdict(set)
    for i in groups: by_core[vals[20][i]].add(vals[17][i])
    out['sr17_distinct_per_core'] = {'max': max(len(x) for x in by_core.values()), 'min': min(len(x) for x in by_core.values()),
                                     'cores': len(by_core), 'max_value': max(vals[17])}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('records', type=Path, nargs='+')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    for path in a.records:
        r = json.loads(path.read_text())
        summary = {'source': str(path), 'utc': r['utc'], 'passed': r['passed'], 'error': r.get('error'), 'diff_vs_base': r.get('diff'),
                   'configs': {n: summarize(c) for n, c in r['configs'].items()}}
        dest = a.output/f"scan-{r['utc']}.json"
        dest.write_text(json.dumps(summary)+'\n')
        print(dest, dest.stat().st_size)
    return 0


if __name__ == '__main__':
    sys.exit(main())
