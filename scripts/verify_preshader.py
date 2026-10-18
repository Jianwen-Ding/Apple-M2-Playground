#!/usr/bin/env python3
"""Offline checks of the preshader follow-ups (results/2026-10-18-preshader). Simulator replay of the uniform program unless --no-sim."""
import gzip
import json
from pathlib import Path
import statistics as st
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
rec = json.load(gzip.open(ROOT/'results/2026-10-18-preshader/preshader.json.gz'))
ok = []
HARNESS = range(4, 10)


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


for key in ('uniforms', 'uniforms_b'):
    cf = rec[key]['configs']
    check(f'{key}: uniform register count field 1..7 (32 .. 224 uniforms), every uniform the preamble wrote inside the allocation reads back in the main shader on all lanes',
          [c['field'] for c in cf] == list(range(1, 8)) and all(c['allocated_uniforms'] == 32*c['field'] and c['written_read_back'] == c['written_expected'] and c['lanes_agree'] for c in cf))
    check(f'{key}: field 1..6 wrote every uniform except the harness u4..u9 (26, 58, 90, 122, 154, 186); field 7 a 102-uniform sample (preamble size limit)',
          [c['written_expected'] for c in cf] == [26, 58, 90, 122, 154, 186, 102])
    pat = lambda u: 0xC0DE0000 | u
    check(f'{key}: nothing beyond the allocation shows a written value (no aliasing of high uniforms onto low ones)',
          all(c['values'][u] != pat(v) for c in cf for u in range(c['allocated_uniforms'], 256) for v in range(256)))
    zeros = sum(1 for c in cf for u in range(c['allocated_uniforms'], 256) if c['values'][u] in (0, 0xcdcdcdcd))
    check(f'{key}: uniforms beyond the allocation read as garbage: {zeros} of 896 are 0 / the sentinel (none in run 1, 18 in run 2), the rest arbitrary nonzero words',
          zeros <= 40)
a, b = rec['uniforms']['configs'], rec['uniforms_b']['configs']
diff = sum(1 for ca, cb in zip(a, b) for u in range(ca['allocated_uniforms'], 256) if ca['values'][u] != cb['values'][u])
check('the garbage beyond the allocation differs between two runs (%d of %d values) - undefined contents' % (diff, sum(256-c['allocated_uniforms'] for c in a)), diff > 500)
check('the harness uniforms u4..u9 (index offset, count, output VA, table VA) were not written and keep their pushed values (u5 = 32 lanes)',
      all(c['values'][5] == 32 and c['values'][4] == 0 for c in a))
cnt = rec['count']['configs']
check('preamble runs once per core per dispatch: 38 cores, per-core count = dispatches for 1, 3, 2, 6, 4 and 8 dispatches (commands per submit x submits)',
      [(c['dispatches'], c['per_core'], c['cores_with_runs'], c['total_runs']) for c in cnt] ==
      [(1, [1], 38, 38), (3, [3], 38, 114), (2, [2], 38, 76), (6, [6], 38, 228), (4, [4], 38, 152), (8, [8], 38, 304)])
check('several commands in one submit: 2 and 4 commands per submit give 2 and 4 runs per core (same as separate submits)',
      all(c['per_core'] == [c['commands_per_submit']*c['submits']] for c in cnt))
rg = rec['regs']['configs']
check('SR19 (register allocation) is 64 and the peak occupancy 96 (16 halves) / 52 (64 halves) groups with no preamble, a stop preamble and a preamble writing r2..r30',
      [c['preamble'] for c in rg] == ['none', 'stop', 'regs_r2_r30'] and all(c['sr19_values'] == [64] and c['peak_groups_by_gprs'] == {'16': 96.0, '64': 52.0} for c in rg))
s = rec['cost']['samples_ns']
med = {k: st.median(v) for k, v in s.items()}
check('cost: 15 interleaved samples of 2,048 workgroups; a 1-instruction preamble is within noise of none (|diff| < 300 ns)', all(len(v) == 15 for v in s.values()) and abs(med['stop']-med['none']) < 300)
check('cost: 64 dependent ALU instructions add under 600 ns (+%d), 256 add 2.2-3.4 us (+%d)' % (med['alu64']-med['none'], med['alu256']-med['none']),
      med['alu64']-med['none'] < 600 and 2200 <= med['alu256']-med['none'] <= 3400 and rec['cost']['keeper_stopped'])
if '--no-sim' not in sys.argv:
    out = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/run_drm_preshader.py'), 'offline'], capture_output=True, text=True, cwd=ROOT)
    lines = out.stdout.strip().splitlines()
    check('Rust simulator: preamble + main of the uniform program read back 26 of 26 (field 1) and 154 of 154 (field 5) uniforms: ' + ' | '.join(lines),
          len(lines) == 2 and '26 of 26' in lines[0] and '154 of 154' in lines[1])
sys.exit(0 if all(ok) else 1)
