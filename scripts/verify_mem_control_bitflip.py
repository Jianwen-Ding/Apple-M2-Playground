#!/usr/bin/env python3
"""Offline checks of results/2026-10-11-mem-control-bitflip (no GPU access)."""
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_bitflip as A  # noqa: E402

D = Path(__file__).resolve().parents[1]/'results/2026-10-11-mem-control-bitflip'
checks = []


def check(name, ok):
    checks.append(bool(ok)); print(('PASS' if ok else 'FAIL'), name)


def load(n):
    return json.load(gzip.open(D/f'{n}.json.gz'))


def raws(n, layout='A'):
    return {r['flip']['raw']: r for r in load(n)['results'] if r['layout'] == layout and r['flip'] and 'raw' in r['flip']}


m = load('misc1'); by = {r['name']: r for r in m['results']}
def cls(key, bit):
    return A.classify(by[f'{key}-b{bit}-A'], by[f'{key}-b{bit}-B'], by[f'{key}-base-A'], by[f'{key}-base-B'])[0]
check('threadgroup_barrier bits 8-15: no effect with one SIMD group (scope untested)', all(cls('tgb', b) == 'same' for b in range(8, 16)))
check('get_sr bits 23-25, 30-31 inert; bit 22 changes the result', all(cls('gsr', b) == 'same' for b in (23, 24, 25, 30, 31)) and cls('gsr', 22) == 'dest')
check('device_load bit 31 (long form): result 0', by['dld-b31-A']['table'][6] == [0]*32 and by['dld-base-A']['table'][6] == [0xb0b0b0b0]*32)
r = raws('dld-b31cpu')
check('device_load bit 31 returns 0 also for CPU-written memory; bit 30 loads normally',
      r['b31']['table'][6] == [0]*32 and r['b30']['table'][6] == r['base']['table'][6] == [0xcdcdcdcd]*32)
r = raws('dld-sb2')
check('device_load bit 31 returns 0 after wait 0/1/2; bits 30+31 return 0 after wait 3 and leave r5 unwritten after wait 0',
      all(r[k]['table'][6] == [0]*32 for k in ('b31_w0', 'b31_w1', 'b31_w2', 'b3031_w3')) and
      r['b3031_w0']['table'][6][0] == 0x5a000505)
r = raws('dld-tg')
check('device_load bit 31 does not read threadgroup memory either', r['b31']['table'][6] == [0]*32 if 'b31' in r else
      [x for x in load('dld-tg')['results'] if x['name'] == 'dld-b31-A'][0]['table'][6] == [0]*32)
r = raws('dst-b31')
before = [0xb0b0b0b0]*32
check('device_store bit 31: store dropped (slot keeps its earlier value); bit 30: stored',
      r['b31']['table'][0] == before and r['b3031']['table'][0] == before and r['base']['table'][0] != before and r['b30']['table'][0] == r['base']['table'][0])
reps = []
for k in (1, 2, 3):
    reps.append({x['flip']['mask']: x['table'][6] for x in load(f'gsr-b22-rep{k}')['results'] if x['layout'] == 'A' and x['flip']})
check('get_sr bit 22: values differ between identical runs (undefined)', any(reps[0][k] != reps[1][k] or reps[1][k] != reps[2][k] for k in reps[0]))
r = raws('cf-gaps')
check('if_icmp/if_fcmp/while_icmp/else_icmp bits 46-47 and pop_exec bit 8: identical exec behaviour',
      all(r[f'{nm}_{b}']['table'][6] == r[f'{nm}_None']['table'][6] for nm, bits in (('if', (46, 47)), ('iff', (46, 47)), ('wh', (46, 47)), ('else', (46, 47)), ('pop', (8,))) for b in bits))
t = load('tg-gaps'); tb = {x['name']: x for x in t['results']}
ok = True
for b in (4, 7, 35, 40, 41, 42, 43, 44, 45, 46, 47, 62, 63):
    for kind in ('st', 'ld'):
        for L in 'AB':
            ok &= not A.diff_regs(tb[f'tg-rbase-{L}']['table'], tb[f'tg-r{kind}{b}-{L}']['table'])
check('threadgroup_load/store gap bits 4, 7, 35, 40-47, 62-63: round trip unchanged', ok)
vals = [[x for x in load(f'ustore-pre-{k}')['results'] if x['name'] == 'us-base-A'][0]['table'][6] for k in ('base', 'b30', 'b31', 'b48')]
check('uniform_store (preshader) bits 30, 31, 48 inert: u20 = 0x12345678 in all four', all(v == [0x12345678]*32 for v in vals))
t = {x['flip']['raw']: x for x in load('todo-fixed')['results'] if x['layout'] == 'A' and x['flip']}
check('fixed TODO encodings: after_sampling1/2 and unk0C00 time out (>3 s), unk40C0 fails fast; control passes after each',
      all(t[k]['fault'] and t[k]['host_ns'][0] > 3e9 for k in ('after_sampling1', 'after_sampling2', 'unk0C00')) and
      t['unk40C0']['fault'] and t['unk40C0']['host_ns'][0] < 5e6 and all(f['control_after_ok'] for f in load('todo-fixed')['faults']))
tb = {x['name']: x for x in load('todo-fixed')['results']}
check('fixed TODO encodings unk30C0, unkC0000000, unkE800, doorbell: no register/length effect',
      all(not A.diff_regs(tb[f'fx-base-{L}']['table'], tb[f'fx-r{k}-{L}']['table']) for k in ('unk30C0', 'unkC0000000', 'unkE800', 'doorbell') for L in 'AB'))
check('0x51 (applegpu no_var / TODO.unk51) ends the SIMD group in compute: earlier store kept, no later store',
      t['unk51']['table'][0] == [0xb0b0b0b0]*32 and t['unk51']['table'][25] == [0xcdcdcdcd]*32)
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
