#!/usr/bin/env python3
"""Summarize a run_drm_opcode_describe.py record (offline; no GPU access).

Per length-suite job: completed?, slot-0 store survived?, which of r0..r23
differ from the reference body (`wait` candidate), markers missing (A/B) and
the implied instruction length, and whether the after-store ran.
Per granularity job: per lane, did the after-store run (1) or not (0).
"""
import json
from pathlib import Path
import sys

import run_drm_opcode_describe as m

LENGTH = {(0, 0): 2}
for L in range(4, 36, 2):
    LENGTH[(-(-(L-2)//4), -(-(L-4)//4))] = L


def expected(count, stride):
    """Reference oracle per slot (lists over lanes); None = do not check (r0 high half)."""
    gid = list(range(count))
    exp = [[m.BEFORE]*count]
    for r in m.DUMP:
        if r == 0: exp.append(None)
        elif r == 1: exp.append(gid)
        elif r in m.MARKERS: exp.append([(m.pre(r) & 0xffff0000) | 56]*count)
        else: exp.append([m.pre(r)]*count)
    exp.append([m.AFTER]*count)
    return exp


def summarize(rec, ref):
    t = rec.get('table')
    if not t:
        return {'name': rec['name'], 'fault': rec['fault']}
    if all(v == m.SENTINEL for v in t[25]):  # nothing after the candidate ran: register slots are all sentinel
        return {'name': rec['name'], 'fault': rec['fault'], 'fw_ns': rec['fw_ns'], 'before': all(v == m.BEFORE for v in t[0]),
                'after_lanes': 0, 'suffix_lanes': sum(v == 0x12345678 for v in rec['payload']), 'changed': None, 'missing_markers': None,
                'untouched': all(v == m.SENTINEL for s in t[1:] for v in s),
                'exact': all(v == m.BEFORE for v in t[0]) and all(v == m.SENTINEL for s in t[1:] for v in s)
                         and all(v == m.SENTINEL for v in rec['payload'])}
    regs = {}
    for k, r in enumerate(m.DUMP):
        a, b = t[1+k], ref['table'][1+k]
        if r == 0:  # r0h is uninitialized and varies per run; r0l is the exec counter
            a, b = [v & 0xffff for v in a], [v & 0xffff for v in b]
        if a != b:
            regs[f'r{r}'] = sorted({hex(v) for v in a})[:4]
    missing = [r for r in m.MARKERS if all(v == m.pre(r) for v in t[1+m.DUMP.index(r)])]
    ran_after = [int(v == m.AFTER) for v in t[25]]
    # exact-oracle check: every slot must equal the reference except swallowed markers and listed changes
    exact = t[0] == ref['table'][0] and t[25] == ref['table'][25] and all(
        t[1+k] == ref['table'][1+k] or (r in missing and all(v == m.pre(r) for v in t[1+k])) or r == 0
        for k, r in enumerate(m.DUMP))
    return {'name': rec['name'], 'fault': rec['fault'], 'fw_ns': rec['fw_ns'],
            'before': all(v == m.BEFORE for v in t[0]),
            'after_lanes': sum(ran_after), 'after_mask': ''.join(map(str, ran_after)),
            'suffix_lanes': sum(v == 0x12345678 for v in rec['payload']),
            'changed': {k: v for k, v in regs.items() if int(k[1:]) not in missing},
            'missing_markers': len(missing) if sum(ran_after) else None, 'exact': exact}


def jobs(rec):
    """Per submission (repeats kept): name, firmware ns, and slots that differ from the exact oracle.

    The oracle is the reference body's; for length-suite jobs the one swallowed marker
    of a 6-byte candidate (slot of r16) is expected, so it is reported separately."""
    out = []
    for r in rec['results']:
        t = r.get('table')
        row = {'name': r['name'], 'fault': r['fault'], 'fw_ns': r.get('fw_ns')}
        if t and r['variant'] in ('all', 'control'):
            exp = expected(r['count'], 32)
            row['bad_slots'] = [s for s, e in enumerate(exp) if e is not None and t[s] != e]
        out.append(row)
    return out


def main():
    rec = json.loads(Path(sys.argv[1]).read_text())
    if len(sys.argv) > 2 and sys.argv[2] == '--jobs':
        print(json.dumps(jobs(rec), indent=0)); return
    res = {r['name']: r for r in rec['results']}
    out = {'control_before': rec.get('control_before'), 'complete': rec['complete'], 'error': rec.get('error')}
    # validate references against the exact oracle
    for lay in 'AB':
        ref = res.get(f'ref-wait-{lay}')
        if ref:
            exp = expected(ref['count'], 32)
            bad = [s for s, e in enumerate(exp) if e is not None and ref['table'][s] != e]
            out[f'ref-{lay}-ok'] = not bad and all(v == 0x12345678 for v in ref['payload'])
            if bad: out[f'ref-{lay}-bad-slots'] = bad
    rows = {}
    for name, r in res.items():
        if not name.startswith('op-'): continue
        _, op, en, lay = name.split('-')
        s = summarize(r, res[f'ref-wait-{lay}'])
        rows.setdefault((op, en), {})[lay] = s
    table = []
    for (op, en), d in sorted(rows.items()):
        A, B = d.get('A', {}), d.get('B', {})
        mm = (A.get('missing_markers'), B.get('missing_markers'))
        table.append({'op': '0x'+op, 'enc': en,
                      'class': 'fault' if A.get('fault') or B.get('fault') else ('ends' if not A.get('after_lanes') and not B.get('after_lanes') else
                               ('mixed' if not A.get('after_lanes') or not B.get('after_lanes') else 'continues')),
                      'length': LENGTH.get(mm) if None not in mm else None, 'missing': mm,
                      'before_ok': (A.get('before'), B.get('before')),
                      'changed_A': A.get('changed'), 'changed_B': B.get('changed'),
                      'after_A': A.get('after_lanes'), 'after_B': B.get('after_lanes'),
                      'suffix': (A.get('suffix_lanes'), B.get('suffix_lanes')),
                      'exact': (A.get('exact'), B.get('exact')), 'fw_ns': (A.get('fw_ns'), B.get('fw_ns'))})
    out['length_suite'] = table
    gran = {}
    for name, r in res.items():
        if not name.startswith('gran-'): continue
        t = r.get('table')
        gran[name] = {'fault': r['fault'], 'fw_ns': r.get('fw_ns'),
                      'before': ''.join(str(int(v == m.BEFORE)) for v in t[0]) if t else None,
                      'after': ''.join(str(int(v == m.AFTER)) for v in t[25]) if t else None,
                      'suffix': ''.join(str(int(v == 0x12345678)) for v in r['payload']) if r.get('payload') else None}
    out['granularity'] = gran
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
