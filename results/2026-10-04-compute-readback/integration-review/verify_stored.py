"""Read-only independent P2 evidence verification; no runner imports or GPU access."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
checks = []
manifest = json.loads((ROOT / 'retained-manifest.json').read_text())
for name, digest in manifest.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
checks.append({'check': 'retained manifest', 'files': len(manifest), 'passed': True})
primary = ROOT / 'primary'
manifest = json.loads((primary / 'manifest.json').read_text())
for name, digest in manifest.items():
    assert hashlib.sha256((primary / name).read_bytes()).hexdigest() == digest, name
checks.append({'check': 'primary manifest', 'files': len(manifest), 'passed': True})
summary = json.loads((primary / 'summary.json').read_text())
assert summary['pass'] and len(summary['cases']) == 25
cases = [(c['directory'], c['mode'], c['count']) for c in summary['cases']]
cases.append(('final-control', 'control', 32))
output_words = dispatches = controls = 0
for name, mode, count in cases:
    case = primary / name
    slots = 16 + ((count + 31) // 32) * 32
    expected = [0xcdcdcdcd] * slots
    if mode != 'control':
        dispatches += 1
        for i in range(count):
            expected[8+i] = 0x12345678 if mode == 'constant' else ((i * 2654435769) % 4294967296) ^ 0x12345678
    else:
        controls += 1
    untouched = list(range(0xa5a50000, 0xa5a50010))
    references = {'input.bin': [0xcdcdcdcd]*slots, 'output.bin': expected,
                  'expected.bin': expected, 'control-input.bin': untouched,
                  'control-output.bin': untouched, 'control-expected.bin': untouched}
    for filename, words in references.items():
        actual = (case / filename).read_bytes()
        assert actual == struct.pack('<' + str(len(words)) + 'I', *words), (name, filename)
    command = json.loads((case / 'command.json').read_text())
    stdout = (case / 'stdout.txt').read_text()
    assert command['returncode'] == 0 and not command['timed_out']
    assert 'drm_driver=asahi' in stdout and 'gl_renderer=Apple M2 Max (G14C B1)' in stdout
    assert f'dispatch_count={int(mode != "control")}' in stdout
    assert 'status=0x911a' in stdout or 'status=0x911c' in stdout
    assert 'READBACK_COMPLETE' in stdout
    output_words += slots + 16
assert (dispatches, controls, output_words) == (22, 4, 3328)
actual = (primary / '23-index-257/output.bin').read_bytes()
wrong = (primary / 'negative-oracle/expected-wrong.bin').read_bytes()
assert len(actual) == len(wrong)
assert [i//4 for i in range(0, len(actual), 4) if actual[i:i+4] != wrong[i:i+4]] == [8]
invalid = primary / 'negative-invalid-shader'
assert json.loads((invalid / 'command.json').read_text())['returncode'] == 3
assert 'dispatch_count=' not in (invalid / 'stdout.txt').read_text() and not (invalid / 'output.bin').exists()
assert 'INTENTIONAL_UNDECLARED_IDENTIFIER' in (invalid / 'compile.log').read_text()
assert 'stage=render-node-identity' in (primary / 'negative-device/stderr.txt').read_text()
checks.append({'check': 'independent complete-buffer oracle and API completion gates',
               'readback_cases': len(cases), 'dispatches': dispatches, 'controls': controls,
               'output_words': output_words, 'passed': True})
checks.append({'check': 'wrong oracle, invalid shader and device rejection', 'passed': True})
print(json.dumps({'scope': 'Read-only software review of stored hardware evidence; no dispatch',
                  'checks': checks}, indent=2))
