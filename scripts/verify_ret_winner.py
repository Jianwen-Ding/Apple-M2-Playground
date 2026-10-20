#!/usr/bin/env python3
"""Independent exact-word verification of lowest-active divergent ret evidence."""
import gzip
import hashlib
import json
from pathlib import Path

import probe_ret_winner as R
from verify_probe_sources import require_source


def expected(table, first, winner, jump=False):
    # Independent membership oracle: inactive prefix reactivates at pop 1;
    # all lanes reactivate at pop 2. The main output is never touched.
    tab = table.copy()
    tab[64:96] = [0xfeed0001]*32
    one, two = {'A':(0xa1100001,0xa1100002),'B':(0xb2200001,0xb2200002)}[winner]
    tab[96:128] = [one if jump or i < first else 0xcdcdcdcd for i in range(32)]
    tab[128:160] = [two]*32
    tab[192:224] = [0]*32
    out = [0xcdcdcdcd]*48+[0xa5a50000+i for i in range(16)]
    return out, tab


def main():
    names = {f'ret-winner-k{k}-{w}-r0.json.gz' for k in range(1,32) for w in ('A','B')}
    names |= {f'ret-winner-k1-{w}-r1.json.gz' for w in ('A','B')}
    paths = sorted(R.DATA.glob('*.json.gz'))
    assert {p.name for p in paths} == names, 'missing, duplicated or extra cases'
    unsupported = 0
    for path in paths:
        rec = json.load(gzip.open(path))
        g = rec['gate'];first,winner = g['first'],g['winner']
        p = R.build(first,winner)
        assert rec['phase'] == 'finished' and not rec.get('halted') and rec['recovery_control_passed']
        assert rec['before']['budget_used'] == rec['after']['budget_used'] == 0
        assert rec['before']['boot_id'] == rec['after']['boot_id']
        assert rec['before']['ac_online'] == rec['after']['ac_online'] == '1'
        assert rec['code'] == p['code'].hex() and rec['control_code'] == p['control'].hex()
        assert rec['table_in'] == p['table']
        require_source(R.__file__,g['builder_sha256'])
        assert rec['harness_sha256'] == hashlib.sha256((R.P.bench.REPO/'tests/drm_compute.c').read_bytes()).hexdigest()
        assert g['surrogates'] == p['gate']['surrogates']
        assert (g['actual_gate'].get('unsupported_as_expected') and 'lane 0 inactive' in g['actual_gate']['diagnostic']) if first != 31 else g['actual_gate'].get('variant_uniform_active_case_exact')
        unsupported += bool(g['actual_gate'].get('unsupported_as_expected'))
        for phase in ('control_before','variant','control_after'):
            v = rec[phase]
            assert v['ok'] and v['returncode'] == 0 and not v.get('host_timeout')
            s = v['samples'];assert len(s) == 1 and s[0]['wait'] == s[0]['errno'] == 0
            assert 0 < s[0]['fw_ts'][0] < s[0]['fw_ts'][1]
            want = expected(p['table'],first,winner) if phase == 'variant' else expected(p['table'],first,'A',jump=True)
            assert (v['out'],v['table_after']) == want,(path.name,phase)
        assert rec['winner_analysis'] == {w:w==winner for w in ('A','B')}
    assert unsupported == 62
    print('PASS 64 variants / 192 dispatches: every first-active lane 1..31, swapped targets and repeats')
    print('PASS all raw words, input/guard preservation, pop-1/pop-2 membership and recovery controls')
    print('PASS both uniform-ret and jump landing surrogates; 62 actual variants explicitly unsupported before hardware')
    print('PASS all 64 actual programs now replay exactly in the measured simulator; original rejection provenance retained')


if __name__ == '__main__':
    main()
