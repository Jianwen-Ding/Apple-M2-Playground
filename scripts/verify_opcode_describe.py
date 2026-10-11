#!/usr/bin/env python3
"""Check the retained opcode-description evidence offline (no GPU access).

Evidence: results/2026-10-11-opcode-describe/ (summaries written by
analyze_opcode_describe.py from run_drm_opcode_describe.py records).
"""
import json
from pathlib import Path
import statistics
import sys

REPO = Path(__file__).resolve().parents[1]
EV = REPO/'results/2026-10-11-opcode-describe'
LOW11 = [op for op in range(3, 128, 4) if op != 0x6f]
CTRL = (0x18, 0x78)
ENDS = [0x01, 0x0d, 0x1d, 0x2c, 0x2d, 0x3c, 0x3d, 0x4d, 0x50, 0x5d, 0x60, 0x6c, 0x6d, 0x70, 0x7c, 0x7d]
ENCS = ['base', 'zero', 'd6', 'dt0', 'dt1', 'dt3', 'b15', 'hi']
BIT7 = {'dt1', 'dt3', 'hi'}   # encodings with bit 7 set
ALL, NONE = '1'*32, '0'*32
HALF_LOW_OFF = '0'*16+'1'*16
G0_OFF = '0'*32+'1'*32
checks = []


def check(name, ok, detail=''):
    checks.append((name, bool(ok), detail))


def rows(path):
    d = json.loads((EV/path).read_text())
    return d, {(r['op'], r['enc']): r for r in d['length_suite']}


def main():
    d, L = rows('length-granularity-g64.json')
    check('g64 run complete, references exact', d['complete'] and d['ref-A-ok'] and d['ref-B-ok'])
    check('g64: 49 opcodes x 8 encodings', len(L) == 49*8, len(L))
    check('g64: every length-suite job matches its oracle exactly', all(r['exact'] == [True, True] for r in L.values()))
    check('g64: no job wrote any of r0l, r1..r15 or an unswallowed marker',
          all(not r['changed_A'] and not r['changed_B'] for r in L.values()))
    check('g64: store before the candidate always survives', all(r['before_ok'] == [True, True] for r in L.values()))
    check('31 low-0b11 opcodes: 6-byte, continue, in all 8 encodings',
          all(L[(f'0x{o:02x}', e)]['class'] == 'continues' and L[(f'0x{o:02x}', e)]['length'] == 6 for o in LOW11 for e in ENCS))
    check('0x18/0x78: 2-byte no-op when bit 7 is clear',
          all(L[(f'0x{o:02x}', e)]['class'] == 'continues' and L[(f'0x{o:02x}', e)]['length'] == 2 for o in CTRL for e in ENCS if e not in BIT7))
    check('0x18/0x78: end execution when bit 7 is set',
          all(L[(f'0x{o:02x}', e)]['class'] == 'ends' for o in CTRL for e in BIT7))
    check('16 ends opcodes end in all 8 encodings, nothing after runs',
          all(L[(f'0x{o:02x}', e)]['class'] == 'ends' and L[(f'0x{o:02x}', e)]['suffix'] == [0, 0] for o in ENDS for e in ENCS))

    G = d['granularity']
    pat = lambda n: (G[n]['before'], G[n]['after'], G[n]['suffix'])
    check('reference wait: every lane continues in every variant',
          all(G[n]['after'] == G[n]['suffix'] and set(G[n]['after']) == {'1'} for n in G if n.startswith('gran-wait-')))
    check('stop ends only active lanes; no-op with zero active lanes',
          pat('gran-stop-all') == (ALL, NONE, NONE) and pat('gran-stop-half') == (ALL, HALF_LOW_OFF, HALF_LOW_OFF)
          and pat('gran-stop-none') == (ALL, ALL, ALL) and G['gran-stop-group0-local64']['after'] == G0_OFF)
    for o in ENDS:
        n = f'gran-{o:02x}'
        check(f'{o:#04x} ends the whole SIMD group regardless of exec mask; other groups unaffected',
              all(pat(f'{n}-{v}') == (ALL, NONE, NONE) for v in ('all', 'half', 'none'))
              and pat(f'{n}-none-jump') == (ALL, ALL, ALL)
              and all(G[f'{n}-group0-local{l}']['after'] == G0_OFF == G[f'{n}-group0-local{l}']['suffix'] for l in (32, 64)))

    B = json.loads((EV/'granularity-bit7.json').read_text())['granularity']
    for n in ('98', 'f8'):
        check(f'0x{n} (bit-7 form) ends the whole SIMD group like the ends class, not like stop',
              all((B[f'gran-{n}-{v}']['before'], B[f'gran-{n}-{v}']['after']) == (ALL, NONE) for v in ('all', 'half', 'none'))
              and B[f'gran-{n}-none-jump']['after'] == ALL and B[f'gran-{n}-group0-local64']['after'] == G0_OFF)
    check('bit-7 run: stop reference reproduces', B['gran-stop-half']['after'] == HALF_LOW_OFF)

    # Register under-declaration: the same suite with 32 halves (r0..r15) declared
    d32, L32 = rows('length-granularity-g32.json')
    bad = sorted(f"{r['op']}-{r['enc']}" for r in L32.values() if r['exact'] != [True, True])
    gbad = sorted(n for n, g in d32['granularity'].items() if not (set(g['before'] or '') <= {'1'}))
    check('g32: exactly 3 length jobs and 1 granularity job are corrupted', bad == ['0x07-dt0', '0x0f-b15', '0x3b-d6'] and gbad == ['gran-3d-none-jump'], (bad, gbad))
    fw32 = [(fw, f"{r['op']}-{r['enc']}-{lay}") for r in L32.values() for lay, fw in zip('AB', r['fw_ns']) if fw]
    fw32 += [(g['fw_ns'], n) for n, g in d32['granularity'].items()]
    slow = sorted(n for fw, n in fw32 if fw[0] > 15000)
    check('g32: the corrupted dispatches are exactly the 4 with firmware time > 15 us',
          slow == sorted(['0x07-dt0-B', '0x0f-b15-A', '0x3b-d6-A', 'gran-3d-none-jump']), slow)
    fw64 = [fw[0] for r in L.values() for fw in r['fw_ns'] if fw]+[g['fw_ns'][0] for g in G.values()]
    check('g64: slow dispatches still occur (>15 us) but none is corrupted', sum(x > 15000 for x in fw64) >= 1)
    R = json.loads((EV/'rerun-g32-anomalies.json').read_text())
    check('g32 reruns (5x each): all exact, only the 6-byte op swallows marker r16 (slot 17)',
          all(r['bad_slots'] == [] for r in R if r['name'].startswith('ref-'))
          and all(r['bad_slots'] == [17] for r in R if r['name'].startswith('op-'))
          and not any(r['fault'] for r in R) and len(R) == 50)

    T = {j['name']: j for j in json.loads((EV/'timing.json').read_text())['jobs']}
    check('timing: 37 loops, no faults, r2 intact', len(T) == 37 and all(not j['fault'] and j['payload_ok'] for j in T.values()))
    # Loop bodies overlap the taken-branch overhead and absolute times depend on a GPU
    # state that changes between processes, so only same-run raw ratios are claimed.
    runs = [T]+[{j['name']: j for j in r['jobs']} for r in json.loads((EV/'timing-repeats.json').read_text())]
    check('timing repeats: 5 further runs, no faults', len(runs) == 6 and all(not j['fault'] for r in runs for j in r.values()))
    med = [{k[5:]: statistics.median(v['fw_ns']) for k, v in r.items()} for r in runs]
    check('absolute loop time varies between processes (mov_imm loop)', max(m['mov_imm'] for m in med) > 1.5*min(m['mov_imm'] for m in med),
          sorted(round(m['mov_imm']/1000) for m in med))
    check('low-0b11 no-ops: raw loop time equals a 6-byte mov_imm loop within 1% in every run',
          all(abs(m[k]/m['mov_imm']-1) < 0.01 for m in med for k in m if k in {f'{o:02x}' for o in LOW11}))
    check('0x18/0x78: raw loop time 3.5-5.5x the mov_imm loop in every run (variable: synchronizing)',
          all(3.5 < m[f'{o:02x}']/m['mov_imm'] < 5.5 for m in med for o in CTRL if f'{o:02x}' in m),
          [round(m['18']/m['mov_imm'], 2) for m in med])

    for name, ok, detail in checks:
        print(('PASS ' if ok else 'FAIL ')+name+(f'  [{detail}]' if detail != '' else ''))
    failed = sum(not ok for _, ok, _ in checks)
    print(f'{len(checks)-failed}/{len(checks)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
