#!/usr/bin/env python3
"""Replay retained SR values through synthetic cost-tracer address probes, not original GPU shaders."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess

from verify_sr_resources import load as load_resources, check as check_resources

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {'uniform': 64, 'depth1': 32, 'depth2': 16, 'depth3': 8, 'quad': 16, 'quad-depth2': 8}
HIGH = 0xa5a5edcb


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def words(values, count):
    require(len(values) == count and all(type(v) is int and 0 <= v <= 0xffffffff for v in values), 'incomplete/invalid lane values')


def fixtures(hw, ev):
    rows = []

    def emit(selector, width, active, values, count, regs=8, context=47, pipeline=32768, tg_bytes=0, high_only=False):
        words(values, len(active))
        table = dict(zip(active, values))
        for wg in range((count + 31)//32):
            expected = [table.get(32*wg+t) for t in range(32)]
            mask = sum(1 << t for t, v in enumerate(expected) if v is not None)
            rows.append(dict(selector=selector, width=width, mask=mask, expected=expected, workgroup=wg,
                regs=regs, context=context, pipeline=pipeline, tg_bytes=tg_bytes, high_only=high_only))

    patterns = hw['patterns']
    require(set(patterns) == set(PATTERNS), 'missing retained divergence pattern')
    for name, p in patterns.items():
        active = p['active_lanes']
        require(len(active) == PATTERNS[name] and len(set(active)) == len(active) and
            all(type(i) is int and 0 <= i < 64 for i in active), 'invalid active lanes')
        require(set(p['values']) == {str(s) for s in range(256)}, 'missing SR selector')
        for values in p['values'].values():
            words(values, len(active))
        for s in range(256):
            if s not in (17, 20, 113):
                emit(s, 'word', active, p['values'][str(s)], 64, regs=32, context=p['values']['21'][0], pipeline=4096)
    divergence = len(rows)
    require(divergence == 3036, 'incomplete divergence replay')

    for name, width in [('width16', 'half'), ('width64', 'odd')]:
        run = ev[name]
        require(run['count'] == 65 and run['repeats'] == 2 and run['preload'] == 0x5a5a1234 and
            run['complete'] and run['passed'] and not run['failures'], 'incomplete width run')
        require(set(run['observations']) == {str(s) for s in range(256)}, 'missing width selector')
        for s in range(256):
            samples = run['observations'][str(s)]['samples']
            require(len(samples) == 2, 'missing width repetition')
            for values in samples:
                words(values, 65)
                if width == 'half' and s in (17, 20, 21, 113) or width == 'odd' and s == 113:
                    continue
                if width == 'odd':
                    require(all(v == HIGH for v in values), 'odd-width adjacent register changed')
                # Odd-width recordings observed only the adjacent register. The
                # first probe's low-word values are intentionally not compared.
                emit(s, width, list(range(65)), values, 65, regs=16 if width == 'odd' else 8, high_only=width == 'odd')
    widths = len(rows) - divergence
    require(widths == 3042, 'incomplete width replay')

    meta = ev['meta']
    require(meta['count'] == 96 and len(meta['sweeps']) == 3, 'incomplete metadata sweeps')
    require({(s['selector'], s['field']) for s in meta['sweeps']} ==
        {(18, 'local_size'), (19, 'nr_gprs'), (19, 'nr_preamble_gprs')}, 'missing metadata sweep')
    for sweep in meta['sweeps']:
        for key, values in sweep['results'].items():
            words(values, 96)
            n = 6 if key == 'original' and sweep['field'] == 'nr_gprs' else 0 if key == 'original' else int(key)
            emit(sweep['selector'], 'word', list(range(96)), values, 96,
                regs=n if sweep['field'] == 'nr_gprs' else 6, tg_bytes=n if sweep['field'] == 'local_size' else 0)
    require(len(rows) == 6171, 'incomplete replay case count')
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--simrepo', type=Path, default=ROOT.parent/'AGX-Performance-Simulator')
    ap.add_argument('--run', type=Path)
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    ev, std = load_resources()  # verifies all resource evidence manifest hashes
    require(not check_resources(ev, std), 'independent resource evidence verification failed')
    hw = json.loads(gzip.decompress((args.simrepo/'results/2026-10-16-special-registers/hardware.json.gz').read_bytes()))
    rows = fixtures(hw, ev)
    run = (args.run or args.simrepo/'rust/target/release/examples/cost_special_registers').resolve()
    result = subprocess.run([str(run), '--replay'], input=''.join(json.dumps(r)+'\n' for r in rows), capture_output=True, text=True, timeout=180)
    require(result.returncode == 0, (result.stdout + result.stderr)[-3000:])
    require(json.loads(result.stdout) == dict(cases=len(rows), passed=True), 'missing/incomplete simulator result')
    if args.selftest:
        for mutate in [lambda h, e: h['patterns'].pop('depth1'),
                lambda h, e: e['width16']['observations'].pop('200'),
                lambda h, e: e['width64']['observations']['7']['samples'][0].pop()]:
            h, e = copy.deepcopy(hw), copy.deepcopy(ev)
            mutate(h, e)
            try:
                fixtures(h, e)
            except (AssertionError, KeyError, ValueError):
                continue
            raise AssertionError('corrupt evidence was accepted')
        bad = copy.deepcopy(rows[0]); bad['expected'][0] ^= 1
        failure = subprocess.run([str(run), '--replay'], input=json.dumps(bad)+'\n', capture_output=True, text=True, timeout=10)
        require(failure.returncode != 0, 'wrong lane value was accepted')
    print('6171 SR group probes pass: 3036 divergence, 3042 retained width, 93 resource metadata; no new GPU execution')
    if args.selftest:
        print('4 failure injections rejected (schema, width coverage/length, wrong lane value)')


if __name__ == '__main__':
    main()
