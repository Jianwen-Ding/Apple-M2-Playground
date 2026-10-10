#!/usr/bin/env python3
"""Offline verifier for results/2026-10-10-sr-shape-core (no GPU access).

Independently recomputes per-lane coordinates and checks:
  * workgroup-geometry selectors across nine local/group shapes;
  * SR7 = ceil(threads per workgroup / 32);
  * shape-invariant constants SR15/19/24/25/97/114;
  * SR20 value set == {(cluster << 4) | core} from retained driver core masks,
    uniform per workgroup over 2048 workgroups;
  * the bit-15 get_sr form leaves its destination untouched for all 256
    selectors and does not change a following standard read (except SR21,
    whose value is per-device state).
--selftest also injects corruptions and requires each to be rejected.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO/'results/2026-10-10-sr-shape-core'
PARAMS = REPO/'results/2026-10-04-device-params/asahi/probe-00.stdout.txt'
PRELOAD = 0x5a5a1234
ALT_PRELOAD = 0xdeadbeef


def lanes(local, groups):
    """Yield (wg, lid, linear-local) in the shader's linear output order."""
    lx, ly, lz = local
    for wz in range(groups[2]):
        for wy in range(groups[1]):
            for wx in range(groups[0]):
                for z in range(lz):
                    for y in range(ly):
                        for x in range(lx):
                            yield (wx, wy, wz), (x, y, z), x + lx*(y + ly*z)


def geometry_oracle(sel, local, groups):
    L = local[0]*local[1]*local[2]
    f = {0: lambda w, l, i: w[0], 1: lambda w, l, i: w[1], 2: lambda w, l, i: w[2],
         4: lambda w, l, i: local[0], 5: lambda w, l, i: local[1], 6: lambda w, l, i: local[2],
         7: lambda w, l, i: -(-L//32),
         8: lambda w, l, i: local[0], 9: lambda w, l, i: local[1], 10: lambda w, l, i: local[2],
         15: lambda w, l, i: 16, 19: lambda w, l, i: 8, 24: lambda w, l, i: 2, 25: lambda w, l, i: 2,
         48: lambda w, l, i: l[0], 49: lambda w, l, i: l[1], 50: lambda w, l, i: l[2],
         51: lambda w, l, i: i, 52: lambda w, l, i: i % 32, 53: lambda w, l, i: i//32,
         56: lambda w, l, i: i % 4, 57: lambda w, l, i: min(4, L - i//4*4),
         58: lambda w, l, i: i % 32, 59: lambda w, l, i: min(32, L - i//32*32),
         80: lambda w, l, i: w[0]*local[0]+l[0], 81: lambda w, l, i: w[1]*local[1]+l[1],
         82: lambda w, l, i: w[2]*local[2]+l[2],
         97: lambda w, l, i: 2048, 114: lambda w, l, i: 136}[sel]
    return [f(w, l, i) for w, l, i in lanes(local, groups)]


def core_ids():
    text = PARAMS.read_text()
    masks = {int(c): int(m, 16) for c, m in re.findall(r'core_masks\[(\d+)\]=0x([0-9a-f]+)', text)}
    return {(c << 4) | k for c, m in masks.items() for k in range(16) if m >> k & 1}


def check(ev):
    errors = []
    req = lambda cond, msg: cond or errors.append(msg)
    shape = ev['shape']
    req(shape['passed'] and not shape['failures'] and shape['all_children_succeeded'], 'shape run not clean')
    req(len(shape['shapes']) == 9, 'expected nine shapes')
    tags = set()
    for s in shape['shapes']:
        local, groups = tuple(s['local']), tuple(s['groups'])
        tags.add(tuple(local))
        req(s['count'] == len(list(lanes(local, groups))), s['tag']+' count')
        for sel, o in s['observations'].items():
            want = geometry_oracle(int(sel), local, groups)
            req(len(o['samples']) == shape['repeats'] >= 2, f"{s['tag']} SR{sel} sample count")
            for v in o['samples']:
                req(v == want, f"{s['tag']} SR{sel} mismatch")
            req(o['patch']['decoded'].startswith('get_sr') and f'sr{sel}' in o['patch']['decoded'], f"{s['tag']} SR{sel} decode")
    req(any(l[1] > 1 for l in tags) and any(l[2] > 1 for l in tags), 'Y and Z local sizes not exercised')

    core = ev['core']
    req(core['passed'] and not core['failures'] and core['count'] == 65536, 'core run not clean')
    obs = core['observations']
    ids = core_ids()
    req(len(ids) == 38, 'driver core masks do not give 38 cores')
    for k, wgs in enumerate(obs['20']['per_workgroup']):
        req(obs['20']['workgroup_uniform'][k], 'SR20 not uniform within a workgroup')
        req(len(wgs) == 2048 and set(wgs) == ids, f'SR20 sample {k} set != core-mask ids')
    for k, wgs in enumerate(obs['0']['per_workgroup']):
        req(wgs == list(range(2048)) and obs['0']['workgroup_uniform'][k], 'SR0 workgroup control')
    for h in obs['80']['histograms']:
        req(h.get('identity') is True and h['distinct'] == 65536, 'SR80 global-id control')
    for sel, const in (('7', 1), ('15', 16), ('19', 8), ('24', 2), ('25', 2), ('97', 2048), ('114', 136),
                       ('8', 32), ('9', 1), ('10', 1)):
        for h in obs[sel]['histograms']:
            req(h == {str(const): 65536}, f'SR{sel} not constant {const} over 2048 workgroups')

    alt, reread, std = ev['alt'], ev['alt_reread'], ev['std']
    for name, r, pre in (('alt', alt, ALT_PRELOAD), ('alt-reread', reread, PRELOAD), ('std', std, PRELOAD)):
        req(r['complete'] and r['passed'] and not r['failures'] and r['preload'] == pre, name+' run not clean')
        req(sorted(map(int, r['observations'])) == list(range(256)), name+' must cover 0..255')
        req(any(c['name'] == 'preload-control' and c['values_unique'] == [pre] for c in r['controls']), name+' preload control')
    req(alt['alt_bit15'] and reread['alt_bit15'] and reread['reread'] and not std['alt_bit15'], 'run modes')
    for sel in range(256):
        a = alt['observations'][str(sel)]
        raw = int.from_bytes(bytes.fromhex(a['body_hex'])[6:10], 'little')
        req(raw & 0x7f == 0x72 and raw >> 15 & 1 and (raw >> 16 & 63) | (raw >> 26 & 3) << 6 == sel, f'alt SR{sel} encoding')
        req(all(v == [ALT_PRELOAD]*alt['count'] for v in a['samples']), f'alt SR{sel} wrote its destination')
        b, c = reread['observations'][str(sel)], std['observations'][str(sel)]
        if sel == 21:
            req(all(len(set(v)) == 1 for v in b['samples'] + c['samples']), 'SR21 not dispatch-uniform')
        else:
            req(b['samples'] == c['samples'], f'alt write changed standard SR{sel} read')
        req(all(PRELOAD not in v for v in b['samples']), f'SR{sel} took the bit-15 source value')
    return errors


def load():
    files = {'shape': 'shape.json', 'core': 'core-id.json', 'alt': 'alt-preload.json',
             'alt_reread': 'alt-reread.json', 'std': 'std-preload.json'}
    manifest = json.loads((EVIDENCE/'manifest.json').read_text())
    for f in files.values():
        if hashlib.sha256((EVIDENCE/f).read_bytes()).hexdigest() != manifest[f]:
            raise SystemExit('manifest hash mismatch: '+f)
    return {k: json.loads((EVIDENCE/f).read_text()) for k, f in files.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selftest', action='store_true')
    a = p.parse_args()
    ev = load()
    errors = check(ev)
    print(json.dumps({'passed': not errors, 'errors': errors[:20]}))
    if errors:
        return 1
    if a.selftest:
        def mutate(fn):
            e = copy.deepcopy(ev); fn(e)
            try:
                return bool(check(e))
            except (KeyError, IndexError, TypeError, ValueError):
                return True  # Malformed evidence is a rejection.
        cases = {
            'shape SR7 off by one': lambda e: e['shape']['shapes'][6]['observations']['7']['samples'][0].__setitem__(0, 3),
            'shape SR50 lane swap': lambda e: e['shape']['shapes'][2]['observations']['50']['samples'][1].reverse(),
            'shape constant SR114': lambda e: e['shape']['shapes'][0]['observations']['114']['samples'][0].__setitem__(5, 137),
            'SR20 extra core': lambda e: e['core']['observations']['20']['per_workgroup'][0].__setitem__(9, 0x19),
            'SR20 nonuniform': lambda e: e['core']['observations']['20']['workgroup_uniform'].__setitem__(1, False),
            'SR97 changed': lambda e: e['core']['observations']['97']['histograms'][0].update({'2048': 65535, '0': 1}),
            'alt wrote r2': lambda e: e['alt']['observations']['33']['samples'][1].__setitem__(4, 0),
            'alt changed SR': lambda e: e['alt_reread']['observations']['200']['samples'][0].__setitem__(0, PRELOAD),
            'missing selector': lambda e: e['std']['observations'].pop('255'),
        }
        results = {name: mutate(fn) for name, fn in cases.items()}
        print(json.dumps({'selftest_rejections': results}))
        if not all(results.values()):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
