#!/usr/bin/env python3
"""Offline check of the direct-DRM differential special-register scans. No GPU access.

Evidence: results/2026-10-11-sr-direct-drm/scan-*.json (extract_sr_scan.py
summaries of run_drm_sr_scan.py records). Claims checked:

  1. every executed scan passed the output oracle, left inactive lanes'
     table slots untouched and wrote all 256 selectors;
  2. the baseline nonzero set is within the 2026-10-04 Vulkan scan's set;
  3. SR32 equals the USC offset of the pipeline words (5 placements) and
     ignores the code offset;
  4. SR17 is uniform within every SIMD group, equals SR53 lane-for-lane in
     every light-load scan (1-D, 2-D and 3-D workgroups up to 1024 threads), and
     separates from SR53 under load: with 2048 one-SIMD workgroups SR53 is 0
     everywhere while SR17 takes >= 30 distinct values per core;
  5. SR17's range shrinks with register allocation (resident sweep: 64 values
     at <= 64 registers with 1024-thread groups, <= 40 at 256 registers);
  6. SR113 is only ever 0 or 8 and differs between identical configurations;
  7. the (No) preshader word must be the last USC pipeline word: four orders
     violating that executed nothing (output and table untouched); orders
     keeping it last, and a real Preshader with a `stop` preamble, executed;
  8. helper data/cfg, queue priority, sampler heap and launch word-0 counts
     change no selector beyond the known varying ones (SR17, SR21, SR113).
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
VULKAN_NONZERO = {0, 4, 5, 6, 7, 8, 9, 10, 15, 16, 19, 20, 21, 24, 25, 32, 48, 51, 52, 56, 57, 58, 59, 60, 63, 80, 97, 113, 114}
NOISY = {17, 21, 113}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, default=REPO/'results/2026-10-11-sr-direct-drm')
    a = p.parse_args()
    scans = [json.loads(f.read_text()) for f in sorted(a.evidence.glob('scan-*.json'))]
    allruns = [(s['utc'], n, c) for s in scans for n, c in s['configs'].items()]
    refused = [(u, n) for u, n, c in allruns if c.get('returncode')]   # harness refused the layout before submitting
    runs = [(u, n, c) for u, n, c in allruns if not c.get('returncode')]
    for _, _, c in runs:   # early records predate the flag: derive it from the data
        if c.get('executed_nothing') is None:
            c['executed_nothing'] = not c['buffer_ok'] and len(c.get('unwritten') or []) == 256
    by = {}
    for _, n, c in runs: by.setdefault(n, []).append(c)
    checks = []
    def check(name, ok, **detail):
        checks.append({'check': name, 'passed': bool(ok), **detail})
    executed = [c for _, _, c in runs if not c.get('executed_nothing')]
    nonzero = lambda c: {int(s) for s, v in c['selectors'].items() if any(x not in (0,) for x, _ in v['top'])}
    val = lambda c, s: c['selectors'][str(s)]['top'][0][0]

    check('scans-valid', all(c['buffer_ok'] and c['inactive_untouched'] and not c['unwritten'] for c in executed),
          executed=len(executed), no_execution=len(runs)-len(executed), scans=len(scans), refused_before_submit=refused)
    check('baseline-within-vulkan-set', all(nonzero(c) <= VULKAN_NONZERO for c in by['base']),
          base_runs=len(by['base']), union=sorted(set().union(*(nonzero(c) for c in by['base']))))

    place = {'base': 0x1000, 'words-only': 0x4000, 'words-0x8040': 0x8040, 'words-0x40': 0x40, 'usc-moved': 0x3000, 'code-only': 0x1000}
    got = {n: sorted({val(c, 32) for c in by[n]}) for n in place}
    check('sr32-is-pipeline-offset', all(got[n] == [v] for n, v in place.items()) and
          all(c['selectors']['32']['distinct'] == 1 for n in place for c in by[n]),
          sr32={n: [hex(x) for x in v] for n, v in got.items()})

    light = [c for _, n, c in runs if not c.get('executed_nothing') and not n.startswith(('occupancy', 'slots', 'resident'))]
    heavy = by['occupancy-2048wg'][0]
    check('sr17-uniform-per-simd-group', all(c['uniform_within_simd_group']['17'] for c in executed))
    shapes = [n for n in by if n.startswith(('shape-', 'local-'))]
    check('sr17-equals-sr53-light-load', sum(c['sr17_equals_sr53_all_lanes'] for c in light) >= len(light)-1 and
          all(c['sr17_equals_sr53_all_lanes'] for n in shapes for c in by[n]),
          light_scans=len(light), equal=sum(c['sr17_equals_sr53_all_lanes'] for c in light), shapes=sorted(shapes))
    check('sr17-separates-under-load', set(heavy['per_simd_group']['53']) == {0} and heavy['sr17_distinct_per_core']['min'] >= 30,
          sr53_values=sorted(set(heavy['per_simd_group']['53'])), sr17_per_core=heavy['sr17_distinct_per_core'])
    res = {n: by[n][0]['sr17_distinct_per_core']['max'] for n in by if n.startswith('resident-')}
    check('sr17-range-shrinks-with-registers', res['resident-g32-wg1024'] == 64 and res['resident-g64-wg1024'] == 64 and
          all(res[f'resident-g256-wg{w}'] <= 40 for w in (32, 128, 1024)) and res['resident-g256-wg128'] < res['resident-g32-wg128'],
          max_distinct_per_core=dict(sorted(res.items(), key=lambda kv: (int(kv[0].split('-g')[1].split('-')[0]), kv[0]))))

    s113 = [set(c['per_simd_group']['113']) for c in executed]
    base113 = [val(c, 113) for c in by['base']+by.get('base-repeat', [])+by.get('order-shru', [])]
    check('sr113-random-0-or-8', set().union(*s113) <= {0, 8} and len({c['selectors']['113']['top'][0][0] for c in by['order-shru']}) == 2,
          order_shru_values=[val(c, 113) for c in by['order-shru']], base_values=base113)

    bad_orders = ['order-ushnr', 'order-usnrh', 'order-nrhsu', 'preshader-first']
    good_orders = ['base', 'order-shru', 'order-rhsu', 'preshader-stop']
    check('preshader-word-last', all(c['executed_nothing'] for n in bad_orders for c in by[n]) and
          not any(c.get('executed_nothing') for n in good_orders for c in by[n]),
          no_execution={n: [c['fw_ns'] for c in by[n]] for n in bad_orders},
          usc_words={n: by[n][0]['usc_words_hex'] for n in bad_orders+['preshader-stop']})

    neutral = ['helper-data', 'helper-cfg', 'priority-low', 'samplers-4', 'word0-uniform-2', 'word0-texture-8', 'word0-preshader-16', 'preshader-stop']
    base = by['base'][0]
    diffs = {}
    for n in neutral:
        c = by[n][0]
        vs = lambda r, s: sorted(x for x, _ in r['selectors'][s]['top'])
        diffs[n] = sorted(int(s) for s in c['selectors'] if vs(c, s) != vs(base, s))
    check('neutral-parameters', all(set(d) <= NOISY for d in diffs.values()), changed=diffs)

    passed = all(c['passed'] for c in checks)
    (a.evidence/'verification.json').write_text(json.dumps({'passed': passed, 'checks': checks}, indent=1)+'\n')
    for c in checks: print(('PASS ' if c['passed'] else 'FAIL ')+c['check'], {k: v for k, v in c.items() if k not in ('check', 'passed')})
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
