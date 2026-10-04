#!/usr/bin/env python3
"""Read-only independent evidence audit; no runner imports or GPU access."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

def words(path):
    data = path.read_bytes()
    assert len(data) % 4 == 0, path
    return list(struct.unpack('<' + 'I' * (len(data)//4), data))

def advance(seed, n):
    # Compose affine maps by exponentiation, independent of runner's loop oracle.
    modulus = 1 << 32
    a, b, mul, add = 1664525, 1013904223, 1, 0
    while n:
        if n & 1:
            mul, add = a*mul % modulus, (a*add+b) % modulus
        a, b = a*a % modulus, (a*b+b) % modulus
        n >>= 1
    return (mul*seed+add) % modulus

def manifest(path):
    hashes = json.loads(path.read_text())
    checked, omitted = 0, []
    for name, expected in hashes.items():
        file = path.parent/name
        if not file.is_file():
            omitted.append(name)
            continue
        assert hashlib.sha256(file.read_bytes()).hexdigest() == expected, file
        checked += 1
    return {'checked': checked, 'omitted': omitted}

def audit(directory):
    results = []
    for path in sorted(directory.glob('*/timing.json')):
        case = path.parent
        t = json.loads(path.read_text(), parse_float=Decimal)
        mode, repeats = t['mode'], t['repeats']
        seeds = [0x12345678 ^ ((i*0x9e3779b9) % (1<<32)) for i in range(64)]
        expected = [0xcdcdcdcd]*80
        if mode in ('elapsed','pair'):
            expected[8:72] = [advance(seed, repeats) for seed in seeds]
        controls = [0xa5a50000+i for i in range(16)]
        for name, ref in {'input.bin':[0xcdcdcdcd]*80, 'output.bin':expected,
                          'expected.bin':expected, 'control-input.bin':controls,
                          'control-output.bin':controls, 'seeds.bin':seeds,
                          'seeds-output.bin':seeds}.items():
            assert words(case/name) == ref, case/name
        command = json.loads((case/'command.json').read_text())
        assert command['returncode'] == 0 and not command['timed_out'], case
        assert 'READBACK_COMPLETE' in (case/'stdout.txt').read_text(), case
        assert not (case/'stderr.txt').read_bytes(), case
        assert t['disjoint_before'] == t['disjoint_after'] == 0, case
        pair = mode in ('pair','empty-pair')
        if mode != 'control':
            assert t['available'][:2 if pair else 1] == [1]*(2 if pair else 1), case
        delta = t['raw_u64'][1]-t['raw_u64'][0] if pair else t['raw_u64'][0]
        bracket = (t['host_monotonic_s'][2]-t['host_monotonic_s'][0])*Decimal(10**9)
        results.append({'case':case.name,'mode':mode,'repeats':repeats,
                        'api_delta_ns':delta,'host_to_result_ns':str(bracket),
                        'exceeds_bracket_plus_1ms': delta > bracket+10**6})
    return results

if __name__ == '__main__':
    checks = {str(p.relative_to(REPO)):manifest(p) for p in
              (ROOT/'selected-manifest.json', ROOT/'final-run/manifest.json',
               ROOT/'negative-node/manifest.json',
               REPO/'results/2026-10-04-vulkan-capabilities/manifest.json')}
    cases = audit(ROOT/'final-run')
    elapsed = [c for c in cases if c['mode']=='elapsed']
    assert len(elapsed) == 10 and all(c['exceeds_bracket_plus_1ms'] for c in elapsed)
    assert len(cases)==24
    vk = REPO/'results/2026-10-04-vulkan-capabilities'
    setup = json.loads((vk/'final-setup/record.json').read_text())
    repeat = json.loads((vk/'final-repeat/record.json').read_text())
    assert setup['passed'] and repeat['passed']
    assert setup['capabilities'] == repeat['capabilities']
    assert setup['sha256'] == repeat['sha256']
    for name in ('final-setup','final-repeat'):
        record = json.loads((vk/name/'record.json').read_text())
        assert json.loads((vk/name/'stdout.json').read_text()) == record['capabilities']
        assert record['commands'][-1]['returncode'] == 0
    missing = json.loads((vk/'final-missing/record.json').read_text())
    assert not missing['passed'] and missing['capabilities']['vkCreateInstance']==-9
    print(json.dumps({'pass':True,'manifests':checks,'cases':cases,
                      'loaded_elapsed_invalid':len(elapsed),
                      'vulkan_repeat_capabilities_and_hashes_equal':True},indent=2))
