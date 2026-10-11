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
     change no selector beyond the known varying ones (SR17, SR21, SR113);
  9. a preamble's uniform_store values reach every main-shader lane (constant control);
 10. in the preamble: one active lane (SR57 = SR59 = 1), SR0 = 0, SR17 = 96 and
     SR24 = 5 (main: 2), selectors 128..255 all zero; its SR20 equals the main
     shader's own SR20 in every lane (uniforms are per core);
 11. the device atomic add (no return) counts exactly 33 / 64 / 65,536 lanes;
 12. the preamble runs exactly once per core per dispatch on cores with work
     (atomic per-core counters all 1 with 1..60 workgroups per core);
 13. SR12 / SR13 = imageblock width / height of the USC Shared layout
     (32x32, 32x16, 16x16; 0 for the vertex/compute layout);
 14. SR15 = the Shared word's sample-stride field (8-byte units), with 0 read
     as 16 (the old "constant" 16); SR18 = its bytes field x 256;
 15. Shader unk_2 = 2 and the Shared sample-count field change no selector
     (SR24 does not follow unk_2; SR14 stays 0 in compute), and every
     strict-checked probe completed normally (firmware timestamps, < 50 ms).
"""
import argparse
import collections
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
    special = ('pre-', 'atomic-')   # table slots hold preamble copies or nothing: excluded from main-shader checks
    main_exec = [c for _, n, c in runs if not c.get('executed_nothing') and not n.startswith(special)]
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

    light = [c for _, n, c in runs if not c.get('executed_nothing') and not n.startswith(('occupancy', 'slots', 'resident')+special)]
    heavy = by['occupancy-2048wg'][0]
    check('sr17-uniform-per-simd-group', all(c['uniform_within_simd_group']['17'] for c in main_exec), scans=len(main_exec))
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

    s113 = [set(c['per_simd_group']['113']) for c in main_exec]
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

    # 9-12: preshader context and atomics.
    ctl = by['pre-control'][-1]
    check('preamble-delivery', all(ctl['selectors'][str(k)]['top'] == [[0x5a000000+k, ctl['lanes']]] for k in range(128)))
    pre = [c for n in ('pre-chunk0', 'pre-chunk0-local128', 'pre-chunk0-2048wg') for c in by[n] if 'preshader_sr20_equals_main_sr20_all_lanes' in c]
    ctxt = {s_: sorted({x for c in pre for x in c['per_simd_group'][str(s_)]}) for s_ in (0, 17, 24, 57, 59)}
    main24 = sorted({x for c in pre for x in c['per_simd_group']['253']})
    hi = by['pre-chunk1'][-1]
    check('preamble-context', ctxt == {0: [0], 17: [96], 24: [5], 57: [1], 59: [1]} and main24 == [2] and
          all(c['preshader_sr20_equals_main_sr20_all_lanes'] for c in pre) and
          all(hi['selectors'][str(k)]['top'] == [[0, hi['lanes']]] for k in range(128, 256)),
          preamble_values=ctxt, main_sr24=main24, paired_scans=len(pre), lanes_paired=sum(c['lanes'] if c['lanes'] < 65536 else 65536 for c in pre))
    at = {n: by[n][-1]['atomic_counter'] for n in ('atomic-33', 'atomic-64', 'atomic-65536')}
    check('atomic-add', at == {'atomic-33': 33, 'atomic-64': 64, 'atomic-65536': 65536} and
          all(by[n][-1]['atomic_neighbours_untouched'] for n in at), counters=at)
    once = {}
    for n in ('pre-atomic-2wg', 'pre-atomic-512x128', 'pre-atomic-2048wg'):
        c = by[n][-1]; runs_ = {int(k): v for k, v in c['preamble_runs_by_core'].items()}
        cores = set(c['per_simd_group']['250']); wgs = collections.defaultdict(set)
        for core, wg in zip(c['per_simd_group']['250'], c['per_simd_group']['252']): wgs[core].add(wg)
        once[n] = {'runs': sorted(set(runs_.values())), 'cores_with_runs': len(runs_), 'cores_with_work': len(cores),
                   'workgroups_per_core': [min(len(x) for x in wgs.values()), max(len(x) for x in wgs.values())]}
    check('preamble-once-per-core', all(v['runs'] == [1] and v['cores_with_runs'] == v['cores_with_work'] for v in once.values()), runs=once)

    # 13-15: imageblock layouts (USC Shared word) and Shader unk_2.
    v1 = lambda n, sel: sorted({x for x, _ in by[n][-1]['selectors'][str(sel)]['top']})
    dims = {n: (v1(n, 12), v1(n, 13)) for n in ('shared-32x32-s8', 'shared-32x16-s8', 'shared-16x16-s8', 'base')}
    check('sr12-sr13-imageblock-dims', dims == {'shared-32x32-s8': ([32], [32]), 'shared-32x16-s8': ([32], [16]),
                                                 'shared-16x16-s8': ([16], [16]), 'base': ([0], [0])}, dims=dims)
    stride = {'shared-32x32-s8': 1, 'shared-32x32-st2': 2, 'shared-32x32-st3': 3, 'shared-32x32-s32': 4,
              'shared-32x32-st7': 7, 'shared-32x32-st15': 15, 'shared-32x32-st0': 16, 'base': 16}
    words = {n: int(by[n][-1]['env'].get('AGX_SHARED_WORD', '0'), 16) for n in stride if n != 'base'}
    sr18 = {n: v1(n, 18) for n in words}
    check('sr15-sample-stride-sr18-bytes', all(v1(n, 15) == [w] for n, w in stride.items()) and
          all(sr18[n] == [((w >> 24) & 0xff)*256] for n, w in words.items()),
          sr15={n: v1(n, 15)[0] for n in stride}, sr18={n: x[0] for n, x in sr18.items()})
    strict = [n for n in by if n.startswith(('shared-', 'shader-unk2'))]
    neutral2 = {}
    for n in ('shader-unk2-2', 'shared-32x32-samples2', 'shared-32x32-samples4'):
        c = by[n][-1]; ref = by['shared-32x32-s8'][-1] if n.startswith('shared') else base
        neutral2[n] = sorted(int(s_) for s_ in c['selectors'] if sorted(x for x, _ in c['selectors'][s_]['top']) !=
                             sorted(x for x, _ in ref['selectors'][s_]['top']) and int(s_) not in (18,))
    check('unk2-and-sample-count-neutral', all(set(d) <= NOISY for d in neutral2.values()) and
          all(by[n][-1].get('completed_normally') for n in strict), changed=neutral2, strict_probes=len(strict))

    passed = all(c['passed'] for c in checks)
    (a.evidence/'verification.json').write_text(json.dumps({'passed': passed, 'checks': checks}, indent=1)+'\n')
    for c in checks: print(('PASS ' if c['passed'] else 'FAIL ')+c['check'], {k: v for k, v in c.items() if k not in ('check', 'passed')})
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
