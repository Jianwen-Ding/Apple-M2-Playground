#!/usr/bin/env python3
"""Offline checks of results/2026-10-11-sync-and-end-opcodes (run_drm_sync_probe.py records)."""
import json
from pathlib import Path
import sys

import analyze_sync_probe as an

EV = Path(__file__).resolve().parents[1]/'results/2026-10-11-sync-and-end-opcodes'
ENDS = ['01', '0d', '1d', '2c', '2d', '3c', '3d', '4d', '50', '5d', '60', '6c', '6d', '70', '7c', '7d', '98', 'f8']
SENT = 0xcdcdcdcd
checks = []
check = lambda name, ok, detail='': checks.append((name, bool(ok), detail))
load = lambda f: json.loads((EV/f).read_text())


def group0_reads(path):
    out = {}
    for r in load(path)['results']:
        n = r['count']; res = r['table'][2*n:3*n]
        out[r['name']] = (set(res[:32]), set(res[32:]), r['fault'], r['suffix_lanes'] == n)
    return out


def main():
    for path, label in (('barrier-device.json', 'device memory'), ('barrier-tgmem.json', 'threadgroup memory')):
        B = group0_reads(path)
        check(f'{label} barrier runs: no fault, every lane reaches the suffix', all(not f and s for _, _, f, s in B.values()))
        for g in (2, 4):
            pre = 'barrier-tg-' if 'tg' in path else 'barrier-'
            check(f'{label}, {g} groups: wait does not synchronize (group 0 reads the sentinel)', B[f'{pre}g{g}-wait'][0] == {SENT})
            check(f'{label}, {g} groups: threadgroup_barrier 0x68 synchronizes (reads flag {g})', B[f'{pre}g{g}-tg_barrier'][0] == {g})
            check(f'{label}, {g} groups: 0x78 (7809 and 7800) synchronizes like 0x68',
                  B[f'{pre}g{g}-78'][0] == {g} and B[f'{pre}g{g}-78z'][0] == {g})
            check(f'{label}, {g} groups: 0x18 does not synchronize', B[f'{pre}g{g}-18'][0] == {SENT})
    D = group0_reads('barrier-device.json')
    check('device memory: memory_barrier alone does not synchronize; 0x18 zero form and mem+18 neither',
          all(D[f'barrier-g{g}-{k}'][0] == {SENT} for g in (2, 4) for k in ('mem_barrier', '18z', 'mem+18')))

    T = load('tgcheck.json')['results']
    check('threadgroup memory on direct DRM: lane i reads lane n-1-i exactly (1, 2, 4 groups)',
          all(r['table'][:r['count']] == [0x7e000000+(r['count']-1-i) for i in range(r['count'])] and not r['fault'] for r in T) and len(T) == 3)

    S = load('floor-stability.json')['results']
    floors = [min(r['fw_ns']) for r in S]
    check('50,000-trip dispatches: per-submission floor varies < 1.5% across 50 processes', max(floors) < 1.015*min(floors), (min(floors), max(floors)))
    F = load('clock-flip.json')['results']
    ref = [min(r['fw_ns']) for r in F if r['name'].endswith('none-none')]
    check('short dispatches: the same loop flips between two states (>2x) in one session', max(ref) > 2*min(ref), (min(ref), max(ref)))

    M = an.floor(load('memwait-floor.json')['results'], 50000)
    x = lambda k: M[k]['extra_ns_per_iter']
    check('wait 0 waits for a pending device load (+20 ns/iter vs +1.5 ns alone)', x('memwait-load-wait') > 15 and x('memwait-none-wait') < 3)
    check('0x18: same fixed cost with no memory op, a device load or a device store (4.3 ns, within 0.2)',
          all(abs(x(f'memwait-{m}-18')-4.3) < 0.2 for m in ('none', 'load', 'store')))
    check('0x78: same fixed cost in all three (2.9 ns, within 0.2)', all(abs(x(f'memwait-{m}-78')-2.9) < 0.2 for m in ('none', 'load', 'store')))
    check('threadgroup_barrier 9.3 ns; memory/device barriers 68-81 ns, all memory-independent',
          all(abs(x(f'memwait-{m}-tg_barrier')-9.35) < 0.2 for m in ('none', 'load', 'store'))
          and all(65 < x(f'memwait-{m}-{b}') < 82 for m in ('none', 'load', 'store') for b in ('mem_barrier', 'device_barrier_1', 'device_barrier_2')))
    G = an.floor(load('tgwait-floor.json')['results'], 50000)
    check('0x18 and 0x78 keep their fixed cost after threadgroup loads/stores',
          all(abs(G[f'memwait-{m}-18']['extra_ns_per_iter']-4.3) < 0.2 and abs(G[f'memwait-{m}-78']['extra_ns_per_iter']-2.9) < 0.2 for m in ('tgload', 'tgstore')))
    W = an.floor(load('scope-workgroups-floor.json')['results'], 50000)
    check('0x18 on 8 one-group workgroups (8 cores): same 4.3 ns as one group', abs(W['scope-w8-18']['extra_ns_per_iter']-4.3) < 0.2)

    E = load('endpend.json')['results']
    ok16 = lambda t: all(t[k*32+i] == (0xe0000000 | k << 16)+i for k in range(16) for i in range(32))
    check('all 16 stores issued just before stop / every ender reach memory', all(ok16(r['table']) and not r['fault'] for r in E) and len(E) == 20)
    check('endpend: enders and stop skip the suffix; the wait reference runs it',
          all(r['suffix_lanes'] == (32 if r['name'] == 'endpend-wait' else 0) for r in E))
    Fo = {r['name'][10:]: r for r in load('endfollow.json')['results']}
    after = lambda r: ''.join('1' if v == 0xafafafaf else '0' for v in r['table'][:32])
    check('endfollow: with 16 stop after it, the wait reference lets stop end only lanes 0-15', after(Fo['wait']) == '0'*16+'1'*16)
    check('endfollow: every ender ends all 32 lanes itself (does not skip ahead onto stop)', all(after(Fo[k]) == '0'*32 for k in ENDS))
    C = {}
    for r in load('endcost.json')['results']: C.setdefault(r['name'][8:], []).extend(r['fw_ns'])
    lo = {k: min(v) for k, v in C.items()}
    check('ending 2,048 one-group workgroups costs the same with every ender as with stop (min within 0.5 us)',
          all(abs(lo[k]-lo['stop']) < 500 for k in ENDS), {k: round(lo[k]/1e3, 1) for k in ('stop', '01', 'f8')})
    nf = sum(r['fault'] for f in EV.glob('*.json') for r in json.loads(f.read_text())['results'])
    check('no fault in any retained run', nf == 0)

    for name, ok, detail in checks:
        print(('PASS ' if ok else 'FAIL ')+name+(f'  [{detail}]' if detail != '' else ''))
    failed = sum(not ok for _, ok, _ in checks)
    print(f'{len(checks)-failed}/{len(checks)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
