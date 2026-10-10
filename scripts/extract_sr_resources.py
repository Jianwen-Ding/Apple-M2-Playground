#!/usr/bin/env python3
"""Compact retained evidence for the SR resource/width follow-up (see verify_sr_resources.py)."""
import argparse
import hashlib
import json
from pathlib import Path

from extract_sr_shape_core import scan


def digest(samples):
    return hashlib.sha256(json.dumps(samples).encode()).hexdigest()


def shared(record):
    shapes = []
    for s in record['shapes']:
        full = s['shared_words'] == 0
        shapes.append({k: s[k] for k in ('tag', 'local', 'groups', 'shared_words', 'count', 'export_sha256')} |
                      {'samples': {sel: o['samples'] for sel, o in s['observations'].items() if full or sel in ('18', '19')},
                       'digests': {sel: digest(o['samples']) for sel, o in s['observations'].items()}})
    return {k: record[k] for k in ('utc', 'repeats', 'passed', 'failures', 'source_hashes')} | {
        'child_runs': len(record['commands']), 'all_children_succeeded': all(c['returncode'] == 0 for c in record['commands']),
        'shapes': shapes}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('shared_full', 'shared_granularity', 'meta', 'width64', 'width16'):
        p.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    load = lambda path: json.loads(path.read_text())
    files = {'shared-full.json': shared(load(a.shared_full)), 'shared-granularity.json': shared(load(a.shared_granularity)),
             'meta.json': load(a.meta), 'width64.json': scan(load(a.width64)), 'width16.json': scan(load(a.width16))}
    for name, value in files.items():
        (a.output/name).write_text(json.dumps(value)+'\n')
    manifest = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(a.output.glob('*.json')) if f.name != 'manifest.json'}
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=1)+'\n')


if __name__ == '__main__':
    main()
