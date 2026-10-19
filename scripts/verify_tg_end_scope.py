#!/usr/bin/env python3
"""Offline checks of the tg ending-opcode scope evidence (results/2026-10-19-tg-end-visible). No GPU access."""
import gzip, json, sys
from pathlib import Path

D = Path(__file__).resolve().parents[1]/'results/2026-10-19-tg-end-visible'
checks = []
SENT = 0xcdcdcdcd
ALIVE = 0xcafe0001
REMARK = 0xbeef0001


def check(name, cond):
    checks.append(bool(cond)); print('PASS' if cond else 'FAIL', name)


def load(n):
    return json.load(gzip.open(D/f'{n}.json.gz'))


for name, n, nw in (('tg-op11-cross-group-r0', 128, 3), ('tg-op11-cross-group2-r0', 1024, 4)):
    d = load(name)
    check(f'{name}: control-before, variant and control-after all ran (fence ok, fw valid)',
          all(d[p].get('ok') and d[p].get('fw_ns') for p in ('control_before', 'variant', 'control_after')))
    check(f'{name}: no kernel faults logged, hang budget untouched',
          d.get('kernel_log_delta') == '' and d['after']['budget_used'] == 0)
    check(f'{name}: recovery control exact after the variant', d.get('recovery_control_passed') is True)
    c = d['control_before']
    t = c['table_after']; w = n//64
    g0 = [i for i in range(n) if (i & 63) < 32]
    check(f'{name}: control reads all 0 then 1, ALIVE on group-0 lanes only',
          all(t[i] == 0 for i in range(n)) and all(t[n+i] == 1 for i in range(n)) and
          all(t[2*n+i] == ALIVE for i in g0) and all(t[2*n+i] == SENT for i in range(n) if i not in g0))
    v = d['variant']
    vt = v['table_after']
    vo = v.get('out') or []
    nlanes = d.get('n', n)
    check(f'{name}: variant outputs all sentinel (no lane stored anything)',
          all(x == SENT for x in vt) and all(x == SENT for x in vo[8:8+nlanes]))
    if nw == 4:
        mk = vt[3*n:4*n]
        check(f'{name}: explicit group-1 re-assertion markers absent (group 1 ended, not stuck)',
              all(m == SENT for m in mk))

sys.exit(0 if all(checks) else 1)
