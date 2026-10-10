#!/usr/bin/env python3
"""Offline verifier for results/2026-10-10-sr-resources (no GPU access).

Checks, against independent oracles:
  * SR18 = threadgroup-memory bytes rounded up to 256 (0 when none), from
    both SPIR-V shared arrays and direct local_size metadata edits;
  * SR19 = max(8, nr_gprs rounded up to 8), independent of nr_preamble_gprs;
  * no other selector changes with shared memory or any single metadata edit
    (SR21 per-device state and intermittent SR113 excluded);
  * get_sr with a 64-bit destination writes no high register, and a 16-bit
    destination returns the low half of the standard 32-bit value.
--selftest injects corruptions and requires each to be rejected.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO/'results/2026-10-10-sr-resources'
STD = REPO/'results/2026-10-10-sr-shape-core/std-preload.json'
NOISY = {'21', '113'}
PRELOAD = 0x5a5a1234


def sr18(nbytes):
    return -(-nbytes//256)*256


def sr19(gprs):
    return max(8, -(-gprs//8)*8)


def digest(samples):
    return hashlib.sha256(json.dumps(samples).encode()).hexdigest()


def check(ev, std):
    errors = []
    req = lambda cond, msg: cond or errors.append(msg)
    for name in ('shared_full', 'shared_gran'):
        run = ev[name]
        req(run['passed'] and not run['failures'] and run['all_children_succeeded'], name+' not clean')
        base = next((s for s in run['shapes'] if s['shared_words'] == 0), None)
        for s in run['shapes']:
            n = s['count']
            req(s['digests']['18'] == digest(s['samples']['18']) and s['digests']['19'] == digest(s['samples']['19']), s['tag']+' digest')
            for v in s['samples']['18']:
                req(v == [sr18(4*s['shared_words'])]*n, f"{s['tag']} SR18")
            for v in s['samples']['19']:
                req(v == [8 if s['shared_words'] == 0 else 16]*n, f"{s['tag']} SR19")
            if base is not None and s is not base:
                for sel, d in base['digests'].items():
                    if sel not in NOISY | {'18', '19'}:
                        req(s['digests'].get(sel) == d, f"{s['tag']} SR{sel} changed with shared memory")
        if name == 'shared_full':
            req(base is not None and len(base['samples']) == 256, 'shared_full baseline must hold all 256 selectors')
            req(sorted(s['shared_words'] for s in run['shapes']) == [0, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192], 'shared sizes')
            for sel, samples in base['samples'].items():
                req(digest(samples) == base['digests'][sel], f'baseline SR{sel} digest')
    meta = ev['meta']
    req(meta['passed'] and meta['export_fields']['nr_gprs'] == 6 and meta['export_fields']['local_size'] == 0, 'meta run not clean')
    n = meta['count']
    sweeps = {(s['selector'], s['field']): s for s in meta['sweeps']}
    s = sweeps[(18, 'local_size')]
    req(s['results']['original'] == [0]*n, 'SR18 original')
    for k, v in s['results'].items():
        if k != 'original': req(v == [sr18(int(k))]*n, f'SR18 local_size={k}')
    s = sweeps[(19, 'nr_gprs')]
    req(s['results']['original'] == [sr19(6)]*n, 'SR19 original')
    req(len(s['results']) >= 12, 'SR19 sweep too small')
    for k, v in s['results'].items():
        if k != 'original': req(v == [sr19(int(k))]*n, f'SR19 nr_gprs={k}')
    for k, v in sweeps[(19, 'nr_preamble_gprs')]['results'].items():
        req(v == [8]*n, f'SR19 nr_preamble_gprs={k}')
    base = meta['scans']['baseline']
    req(len(base) == 256 and all(v is not None for v in base.values()), 'meta baseline incomplete')
    expect = {'nr_gprs=64': {'19': [sr19(64)]*n}, 'local_size=4096': {'18': [4096]*n}}
    for name, scan in meta['scans'].items():
        if name == 'baseline': continue
        for sel, v in scan.items():
            if sel in NOISY: continue
            req(v == expect.get(name, {}).get(sel, base[sel]), f'{name} changed SR{sel}')
    w64, w16 = ev['width64'], ev['width16']
    for name, run in (('width64', w64), ('width16', w16)):
        req(run['complete'] and run['passed'] and not run['failures'] and run['preload'] == PRELOAD, name+' not clean')
        req(sorted(map(int, run['observations'])) == list(range(256)), name+' coverage')
    req(any(c['name'] == 'high-control' and c['values_unique'] == [PRELOAD ^ 0xffffffff] for c in w64['controls']), 'r3 copy control')
    for sel in range(256):
        o = w64['observations'][str(sel)]
        raw = int.from_bytes(bytes.fromhex(o['body_hex'])[12:16], 'little')
        req(raw & 0x7f == 0x72 and raw >> 7 & 3 == 2 and raw >> 9 & 63 == 5, f'width64 SR{sel} encoding')
        req(all(v == [PRELOAD ^ 0xffffffff]*w64['count'] for v in o['samples']), f'width64 SR{sel} wrote r3')
        o = w16['observations'][str(sel)]
        raw = int.from_bytes(bytes.fromhex(o['body_hex'])[6:10], 'little')
        req(raw & 0x7f == 0x72 and raw >> 7 & 3 == 0 and raw >> 9 & 63 == 4, f'width16 SR{sel} encoding')
        if str(sel) == '21': continue
        for v, w in zip(o['samples'], std['observations'][str(sel)]['samples']):
            req(v == [(PRELOAD & 0xffff0000) | (x & 0xffff) for x in w], f'width16 SR{sel} != low half of standard read')
    return errors


def load():
    files = {'shared_full': 'shared-full.json', 'shared_gran': 'shared-granularity.json', 'meta': 'meta.json',
             'width64': 'width64.json', 'width16': 'width16.json'}
    manifest = json.loads((EVIDENCE/'manifest.json').read_text())
    for f in files.values():
        if hashlib.sha256((EVIDENCE/f).read_bytes()).hexdigest() != manifest[f]:
            raise SystemExit('manifest hash mismatch: '+f)
    return {k: json.loads((EVIDENCE/f).read_text()) for k, f in files.items()}, json.loads(STD.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selftest', action='store_true')
    a = p.parse_args()
    ev, std = load()
    errors = check(ev, std)
    print(json.dumps({'passed': not errors, 'errors': errors[:20]}))
    if errors:
        return 1
    if a.selftest:
        def rejected(fn):
            e = copy.deepcopy(ev); fn(e)
            try:
                return bool(check(e, std))
            except (KeyError, IndexError, TypeError, ValueError, StopIteration):
                return True
        cases = {
            'SR18 off by granule': lambda e: e['shared_gran']['shapes'][2]['samples']['18'][0].__setitem__(0, 256),
            'SR18 sweep value': lambda e: e['meta']['sweeps'][0]['results']['512'].__setitem__(3, 768),
            'SR19 not rounded': lambda e: e['meta']['sweeps'][1]['results']['20'].__setitem__(0, 20),
            'SR19 follows preamble': lambda e: e['meta']['sweeps'][2]['results']['32'].__setitem__(0, 32),
            'shared changed other SR': lambda e: e['shared_full']['shapes'][3]['digests'].__setitem__('7', '0'*64),
            'scan side effect': lambda e: e['meta']['scans']['push_count=60']['4'].__setitem__(0, 33),
            'r3 written': lambda e: e['width64']['observations']['32']['samples'][0].__setitem__(1, 0),
            '16-bit high half lost': lambda e: e['width16']['observations']['80']['samples'][1].__setitem__(2, 2),
            'missing selector': lambda e: e['width16']['observations'].pop('200'),
        }
        results = {name: rejected(fn) for name, fn in cases.items()}
        print(json.dumps({'selftest_rejections': results}))
        if not all(results.values()):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
