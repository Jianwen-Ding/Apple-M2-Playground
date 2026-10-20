#!/usr/bin/env python3
"""Verify retained sparse-mask / paired-64-bit shuffle evidence without a GPU.

By default also replay each exact program in agx_run; --no-sim checks retained
hardware bytes, guards, coverage and independently reconstructed PTX results.
"""
import argparse
from collections import Counter
import copy
import gzip
import json
from pathlib import Path
import sys

import run_drm_shfl_mask as R
import sim_gate

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'results/2026-10-20-shfl-mask'


def verify_record(rec, replay=False):
    if not (rec['schema'] == 1 and rec['mode'] == 'hardware' and rec['complete']
            and rec['groups'] == len(R.masks()) and rec['budget_before'] == rec['budget_after'] == 0):
        raise ValueError('incomplete hardware run, wrong launch coverage or faults')
    for name, sha in rec['source_hashes'].items():
        if R.digest((ROOT/name).read_bytes()) != sha:
            raise ValueError('source hash mismatch: '+name)
    for name, sha in rec['assembler_sha256'].items():
        if R.digest((R.chains.APPLEGPU/name).read_bytes()) != sha:
            raise ValueError('assembler hash mismatch: '+name)
    cases = R.configs()
    if [r['case'] for r in rec['results']] != cases:
        raise ValueError('missing, duplicated, reordered or changed cases')
    totals = Counter()
    n = rec['groups']*32
    for r, case in zip(rec['results'], cases):
        table = R.inputs(rec['groups'], rec['seed'], case.get('b'))
        code = R.build(case, n)
        if r['code_hex'] != code.hex() or r['input_sha256'] != R.digest(R.pack(table)):
            raise ValueError('program or inputs changed: '+case['name'])
        if not r['simulator_gate'] or not r['output_guards_ok'] or not sim_gate.oracle_ok(r['output'], n, 0x12345678):
            raise ValueError('main readback or pre-GPU gate failed: '+case['name'])
        events = r['events']
        params = next(e['params'] for e in events if 'params' in e)
        sample = [e for e in events if 'rep' in e]
        if ((params['gen'], params['variant'], params['rev']) != (14, 'C', 17)
                or len(sample) != 1 or sample[0]['wait'] or sample[0]['errno']
                or not 0 < sample[0]['fw_ts'][0] < sample[0]['fw_ts'][1]
                or not any(e.get('completed') and e['count'] == n for e in events)):
            raise ValueError('wrong device or incomplete dispatch: '+case['name'])
        t = r['table']
        if len(t) != len(table) or t[:4*n] != table[:4*n] or t[7*n:] != table[7*n:]:
            raise ValueError('input/guard mutation: '+case['name'])
        # Use the earlier 2026-10-18 reference, independent of this runner's
        # source()/expected()/assess() code. Check both payload halves.
        mismatches = 0
        for group in range(rec['groups']):
            sl = slice(group*32, group*32+32)
            b = table[2*n+sl.start:2*n+sl.stop]
            values, pred = R.shfl.ptx_shfl(case['mode'], list(range(32)), b, case['c'])
            for lane, (src, pv) in enumerate(zip(values, pred)):
                i = sl.start+lane
                if not table[3*n+i]:
                    if any(t[plane*n+i] != R.SENT for plane in (4, 5, 6)):
                        raise ValueError('inactive lane written: '+case['name'])
                    totals['inactive_lanes'] += 1
                    continue
                if t[6*n+i] != pv:
                    raise ValueError('arithmetic predicate mismatch: '+case['name'])
                if not table[3*n+sl.start+src]:
                    totals['undefined_source_lanes_excluded'] += 1
                    continue
                totals['defined_lanes'] += 1
                for plane in (0, 1):
                    want = table[plane*n+sl.start+src]
                    got = t[(4+plane)*n+i]
                    if got != want:
                        mismatches += 1
                        # Group 1 has all lanes active: even poison controls
                        # must remain exact here.
                        if group == 1:
                            raise ValueError('full-mask control mismatch: '+case['name'])
        assessment = R.assess(case, table, t)
        if r['assessment'] != assessment:
            raise ValueError('summary disagrees with raw bytes: '+case['name'])
        if case['path'] != 'poisoned' or case.get('poison') == 0:
            if mismatches:
                raise ValueError('positive PTX data mismatch: '+case['name'])
            totals['positive_programs'] += 1
        else:
            if not mismatches:
                raise ValueError('negative control failed to expose index poison: '+case['name'])
            totals['negative_programs'] += 1
            totals['negative_mismatching_words'] += mismatches
        if case['path'] != 'poisoned' or case.get('poison') == 0:
            totals['positive_defined_lanes'] += assessment['counts'].get('defined', 0)
        raw, _, _ = R.expected(case, table, raw=True)
        # The observed raw effect (including initialized inactive-source reads)
        # must match the AGX unmasked-OR model, beyond PTX's defined subset.
        if t != raw:
            raise ValueError('raw AGX model mismatch: '+case['name'])
        if r['simulator_assessment'] != R.assess(case, table, raw):
            raise ValueError('simulator gate summary mismatch: '+case['name'])
        if replay:
            out, sim_table = R.simulate(code, n, table)
            if sim_table != raw or not sim_gate.oracle_ok(out, n, 0x12345678):
                raise ValueError('simulator replay mismatch: '+case['name'])
    # Before/after controls must repeat the exact same program and results.
    before, after = rec['results'][0], rec['results'][-1]
    if any(before[key] != after[key] for key in ('code_hex', 'input_sha256', 'table', 'output')):
        raise ValueError('bracketing control changed')
    return dict(totals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-sim', action='store_true')
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    args = parser.parse_args()
    paths = sorted(args.evidence.glob('run-*.json.gz'))
    if len(paths) != 2:
        raise ValueError('require two independent retained runs')
    records = [json.load(gzip.open(path)) for path in paths]
    if len({r['seed'] for r in records}) != 2:
        raise ValueError('runs must use distinct input seeds')
    for path, rec in zip(paths, records):
        counts = verify_record(rec, replay=not args.no_sim)
        print('PASS', path.name, json.dumps(counts, sort_keys=True))
    # Ensure the evidence checker detects lost controls and corrupted payloads,
    # guards, inactive writes and programs, rather than trusting summaries.
    original = records[0]
    for name in ('missing-case', 'payload', 'input', 'inactive-write', 'code'):
        bad = copy.deepcopy(original)
        r = bad['results'][0]
        n = bad['groups']*32
        if name == 'missing-case':
            bad['results'].pop()
        elif name == 'payload':
            r['table'][4*n+32] ^= 1   # first active lane in the all-on group
        elif name == 'input':
            r['table'][0] ^= 1
        elif name == 'inactive-write':
            r['table'][4*n] ^= 1     # group 0 has no active lanes
        else:
            r['code_hex'] = '8800'
        try:
            verify_record(bad)
        except ValueError:
            print('PASS rejects', name)
        else:
            raise ValueError('checker accepted corruption: '+name)
    print('PASS both runs: complete mask coverage, paired 64-bit payloads, bracketing controls and raw-AGX oracle')


if __name__ == '__main__':
    main()
