"""Synthetic runner regression checks; no DRM access, temporary output in scratch."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'scripts'))
import run_time

root = Path(tempfile.mkdtemp(prefix='time-runner-review-', dir='/scratch'))
metadata = {'kind': 'metadata', 'driver': 'asahi', 'samples': 8, 'interval_ms': 0,
            'host_clock': 'CLOCK_MONOTONIC_RAW', 'uapi_units': 'nanoseconds', 'struct_size': 16}
rows = [metadata] + [{'kind': 'sample', 'index': i, 'host_before_ns': 100 + i*100,
                     'host_after_ns': 110 + i*100, 'flags': 0, 'gpu_timestamp_ns': 105+i*100,
                     'returncode': 0, 'errno': 0} for i in range(8)]
cases = {'empty': '', 'malformed-json': '{', 'non-object': 'null',
         'metadata-only': json.dumps(metadata),
         'truncated': '\n'.join(map(json.dumps, rows[:-1]))}
for name, field, value in [('failed-sample', 'returncode', -1), ('missing-field', 'errno', None),
                            ('string-timestamp', 'gpu_timestamp_ns', '105'),
                            ('boolean-timestamp', 'gpu_timestamp_ns', True),
                            ('oversized-timestamp', 'gpu_timestamp_ns', 2**64),
                            ('duplicate-index', 'index', 0), ('nonzero-flags', 'flags', 1),
                            ('reversed-host', 'host_after_ns', 1),
                            ('backward-gpu', 'gpu_timestamp_ns', 1)]:
    changed = copy.deepcopy(rows)
    changed[3][field] = value
    cases[name] = '\n'.join(map(json.dumps, changed))
changed = copy.deepcopy(rows); changed[0]['samples'] = 7
cases['metadata-count-mismatch'] = '\n'.join(map(json.dumps, changed))
changed = copy.deepcopy(rows); changed[0]['interval_ms'] = 1
cases['metadata-interval-mismatch'] = '\n'.join(map(json.dumps, changed))
changed = copy.deepcopy(rows)
for r in changed[1:]: r['gpu_timestamp_ns'] = 5
cases['stalled-time'] = '\n'.join(map(json.dumps, changed))
checks = []
for name, output in cases.items():
    def fake_command(argv, directory, label, timeout):
        (directory / f'{label}.stdout.txt').write_text(output if label != 'compile' else '')
        return {'returncode': 0, 'argv': argv}
    with patch.object(run_time, 'logged_command', fake_command), patch.object(run_time, 'collect', return_value={}), \
         patch.object(sys, 'argv', ['run_time.py', '--scratch-root', str(root / name)]), \
         contextlib.redirect_stdout(io.StringIO()):
        status = run_time.main()
    summary = json.loads(next((root / name / 'runs').glob('*/summary.json')).read_text())
    assert status == 1 and summary['passed'] is False, name
    checks.append({'case': name, 'runner_status': status, 'passed': summary['passed'],
                   'analysis': summary['analyses']})
assert run_time.analyze(rows, 8, 0)['gpu_ns_per_host_ns'] == 1
checks.append({'case': 'valid-unit-rate', 'passed': True})
print(json.dumps({'scope': 'Synthetic software validation; no hardware access',
                  'checks': checks}, indent=2))
