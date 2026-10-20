#!/usr/bin/env python3
"""Check empty/partial-mask stop evidence and its return-context counterexample.

Rebuilds exact programs and measured-model gates, then checks every hardware
word against separate per-lane checkpoint sets. Archived sources retain the
original contradicted simulator hypotheses.
"""
import gzip
import hashlib
import json
from pathlib import Path

import probe_empty_stop as E
import probe_ret_stop_context as R
from verify_probe_sources import require_source

PLAIN = {'all1':(range(32),range(32),range(32)),
         'all2':((),range(32),range(32)), 'all3':((),(),range(32)),
         'mix12':(range(1,32,2),range(32),range(32)),
         'mix13':(range(1,32,2),range(1,32,2),range(32)),
         'mix23':((),range(1,32,2),range(32)),
         'mix01':(range(0,32,2),range(0,32,2),range(0,32,2))}


def hardware_oracle(case=None, stops=None):
    if case is not None:
        visible = [set(s) for s in PLAIN[case]]
        checkpoint = set(range(1,32,2)) if case.startswith('mix') else set()
    else:
        visible = ([set(range(0,32,2)),set(range(32)),set(range(32))] if stops == 0
                   else [set(),set(range(1,32,2)),set(range(1,32,2))])
        checkpoint = set()   # fallback remains unwritten, unlike plain prefix checkpoint
    tab = [E.SENT]*(6*32+16)
    tab[:32] = [E.PRE]*32
    tab[32:64] = [E.CHECKPOINT if i in checkpoint else E.SENT for i in range(32)]
    for k, members in enumerate(visible):
        tab[(2+k)*32:(3+k)*32] = [E.MARKS[k] if i in members else E.SENT for i in range(32)]
    tab[160:192] = [0 if i in visible[-1] else E.SENT for i in range(32)]
    out = ([E.SENT]*8+[0x12345678 if i in visible[-1] else E.SENT for i in range(32)]
           +[E.SENT]*8+[0xa5a50000+i for i in range(16)])
    return out, tab


def main():
    expected_names = {f'empty-stop-{c}-r0.json.gz' for c in E.CASES}
    expected_names |= {f'empty-stop-{c}-r1.json.gz' for c in ('mix12','mix13','mix01')}
    expected_names |= {f'ret-empty-stop-{n}-r0.json.gz' for n in (0,1,2,8,32)}
    expected_names |= {f'ret-empty-stop-{n}-r1.json.gz' for n in (0,1)}
    paths = sorted(E.DATA.glob('*.json.gz'))
    assert {p.name for p in paths} == expected_names, 'missing/extra records'
    mismatches = 0
    for path in paths:
        rec = json.load(gzip.open(path))
        g = rec['gate']
        if 'case' in g:
            p = E.build(g['case'])
            want = hardware_oracle(case=g['case'])
            builder = Path(E.__file__)
            sim_matches = True
        else:
            p = R.build(g['stops'])
            want = hardware_oracle(stops=g['stops'])
            builder = Path(R.__file__)
            sim_matches = True
        assert rec['phase'] == 'finished' and not rec.get('halted')
        assert rec['before']['budget_used'] == rec['after']['budget_used'] == 0
        assert rec['before']['boot_id'] == rec['after']['boot_id']
        assert rec['before']['ac_online'] == rec['after']['ac_online'] == '1'
        # Final GEM release is asynchronous: this harness snapshots immediately
        # after the child exits. The following probe starts with shmem back at 0.
        assert rec['before']['shmem'] == 0 and rec['after']['shmem'] <= 2*1024*1024
        assert rec['before']['memory_cgroup']['memory.events'] == rec['after']['memory_cgroup']['memory.events']
        assert rec['recovery_control_passed']
        assert rec['code'] == p['code'].hex() and rec['control_code'] == p['control'].hex()
        assert rec['table_in'] == E.TABLE
        require_source(builder,g['builder_sha256'])
        assert rec['harness_sha256'] == hashlib.sha256((E.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
        for phase in ('control_before','variant','control_after'):
            v = rec[phase]
            assert v['ok'] and v['returncode'] == 0
            assert not v.get('host_timeout') and not v.get('host_process_stuck')
            s = v['samples']
            assert len(s) == 1 and s[0]['wait'] == s[0]['errno'] == 0
            assert 0 < s[0]['fw_ts'][0] < s[0]['fw_ts'][1]
            expected = want if phase == 'variant' else p['expected']
            assert (v['out'],v['table_after']) == expected, (path.name, phase)
        with E.measured_model():
            pred = E.P.cov.simulate(p['code'],32,32,64,0,E.TABLE)
        assert (pred == want) == sim_matches, 'simulator mismatch scope changed'
        mismatches += not sim_matches
        print('PASS',path.name,'exact hardware oracle;', 'simulator exact' if sim_matches else 'known simulator counterexample')
    assert mismatches == 0
    print(f'PASS {len(paths)} variants / {len(paths)*3} total dispatches, exact controls and guards, zero faults; all simulator replays exact')


if __name__ == '__main__':
    main()
