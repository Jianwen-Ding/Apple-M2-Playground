#!/usr/bin/env python3
"""Compact retained evidence from scratch runs of run_agx_sr_shape.py / run_agx_sr_scan.py.

Keeps every per-lane value; drops readback hex, API logs and scratch paths.
"""
import argparse
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scan(record, selectors=None):
    out = {k: record.get(k) for k in ('utc', 'count', 'repeats', 'preload', 'after_hex', 'reread', 'alt_bit15', 'complete', 'passed')}
    out['failures'] = record['failures']
    out['controls'] = [{'name': c['name'], 'passed': c['passed'], 'values_unique': sorted(set(c['values']))} for c in record['controls']]
    out['observations'] = {}
    for o in record['observations']:
        if selectors and o['selector'] not in selectors:
            continue
        patch = o['patch']
        out['observations'][str(o['selector'])] = {
            'body_hex': patch.get('body_hex', patch.get('new')), 'patched_sha256': patch['patched_sha256'],
            'samples': [s['values'] for s in o['samples']],
            'readback_sha256': [s['readback_sha256'] for s in o['samples']]}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--shape', type=Path, required=True)
    p.add_argument('--big', type=Path, required=True)
    p.add_argument('--alt', type=Path, required=True)
    p.add_argument('--alt-reread', type=Path, required=True)
    p.add_argument('--std-preload', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    shape = load(a.shape)
    compact = {k: shape[k] for k in ('utc', 'selectors', 'repeats', 'passed', 'failures', 'source_hashes')}
    compact['child_runs'] = len(shape['commands'])
    compact['all_children_succeeded'] = all(c['returncode'] == 0 for c in shape['commands'])
    compact['shapes'] = [{k: s[k] for k in ('tag', 'local', 'groups', 'count', 'export_sha256', 'patch_site')} |
                         {'observations': {sel: {'patch': o['patch'], 'samples': o['samples']} for sel, o in s['observations'].items()}}
                         for s in shape['shapes']]
    (a.output/'shape.json').write_text(json.dumps(compact)+'\n')
    big = load(a.big)
    # SR20 and SR0 keep one value per workgroup after checking per-workgroup uniformity in the verifier
    # input; other selectors keep value histograms (all were single-valued).
    core = scan(big)
    for sel, o in core['observations'].items():
        if sel in ('20', '0'):
            o['per_workgroup'] = [[s[i] for i in range(0, len(s), 32)] for s in o['samples']]
            o['workgroup_uniform'] = [all(len(set(s[i:i+32])) == 1 for i in range(0, len(s), 32)) for s in o['samples']]
        o['histograms'] = [{str(v): s.count(v) for v in sorted(set(s))} if len(set(s)) <= 64 else
                           {'distinct': len(set(s)), 'min': min(s), 'max': max(s), 'identity': s == list(range(len(s)))}
                           for s in o['samples']]
        del o['samples']
    (a.output/'core-id.json').write_text(json.dumps(core)+'\n')
    for name, path in (('alt-preload', a.alt), ('alt-reread', a.alt_reread), ('std-preload', a.std_preload)):
        (a.output/(name+'.json')).write_text(json.dumps(scan(load(path)))+'\n')
    manifest = {f.name: sha(f) for f in sorted(a.output.glob('*.json')) if f.name != 'manifest.json'}
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=1)+'\n')


if __name__ == '__main__':
    main()
