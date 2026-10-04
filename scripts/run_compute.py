#!/usr/bin/env python3
"""Independent bounded P2 runner. No imports from shared runner internals."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import signal
import struct
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
PREFIXES = ('MESA_', 'ASAHI_', 'AGX_', 'HK_', 'EGL_', 'LIBGL_', 'GALLIUM_',
            'DRI_', 'VK_', 'MALI_', 'ZINK_')
SENTINEL = 0xcdcdcdcd


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, cwd, env, timeout):
    """Retain partial output and kill the entire child group on timeout."""
    start = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        record = {'argv': list(map(str, argv)), 'cwd': str(cwd),
                  'timeout_seconds': timeout, 'timed_out': False, 'returncode': None,
                  'elapsed_seconds': time.monotonic()-start, 'launch_error': str(exc)}
        (cwd / 'stdout.txt').write_bytes(b'')
        (cwd / 'stderr.txt').write_text(str(exc) + '\n')
        write_json(cwd / 'command.json', record)
        return record, '', str(exc)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # The process group may have exited at the timeout boundary.
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            # A stuck kernel call can survive SIGKILL; never wait indefinitely.
            stdout, stderr = exc.output or b'', exc.stderr or b''
    record = {'argv': list(map(str, argv)), 'cwd': str(cwd),
              'timeout_seconds': timeout, 'timed_out': timed_out,
              'returncode': proc.returncode, 'elapsed_seconds': time.monotonic()-start}
    (cwd / 'stdout.txt').write_bytes(stdout)
    (cwd / 'stderr.txt').write_bytes(stderr)
    write_json(cwd / 'command.json', record)
    return record, stdout.decode(errors='replace'), stderr.decode(errors='replace')


def pack(words):
    return struct.pack('<' + 'I' * len(words), *words)


def mismatch(actual, expected):
    if len(actual) != len(expected):
        return {'byte_length_actual': len(actual), 'byte_length_expected': len(expected)}
    bad = []
    for i, (a, e) in enumerate(zip(struct.iter_unpack('<I', actual),
                                  struct.iter_unpack('<I', expected))):
        if a != e:
            bad.append({'word': i, 'actual': a[0], 'expected': e[0]})
    return {'mismatch_count': len(bad), 'first_mismatches': bad[:16]} if bad else None


def verify(directory, mode, n):
    # This oracle is independent of GPU output and the C input generator.
    total = 16 + ((n + 31) // 32) * 32
    initial = [SENTINEL] * total
    expected = initial.copy()
    if mode != 'control':
        for i in range(n):
            expected[8+i] = (0x12345678 if mode == 'constant' else
                             ((i * 0x9e3779b9) & 0xffffffff) ^ 0x12345678)
    controls = pack([0xa5a50000+i for i in range(16)])
    expected_bytes = pack(expected)
    (directory / 'expected.bin').write_bytes(expected_bytes)
    (directory / 'control-expected.bin').write_bytes(controls)
    checks = {}
    for name, reference in [('input.bin', pack(initial)), ('output.bin', expected_bytes),
                            ('control-input.bin', controls), ('control-output.bin', controls)]:
        checks[name] = mismatch((directory / name).read_bytes(), reference)
    result = {'pass': all(value is None for value in checks.values()), 'checks': checks,
              'count': n, 'workgroups': (n+31)//32, 'local_size': 32,
              'verified_output_words': total, 'verified_control_words': 16,
              'prefix_guard_words': 8, 'suffix_guard_and_padding_words': total-8-n,
              'endian': 'little'}
    write_json(directory / 'verification.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-root', type=Path, default=Path('/scratch/apple-m2-playground/compute-runs'))
    parser.add_argument('--mesa-include', type=Path, default=Path(os.environ.get('PROBE_INCLUDE', '/save/workspace/AGX_Probe/mesa/include')))
    parser.add_argument('--device', default='/dev/dri/renderD128')
    parser.add_argument('--smoke', action='store_true',
                        help='two dispatches and two readback controls plus negative checks')
    args = parser.parse_args()
    args.scratch_root = args.scratch_root.expanduser().resolve()
    args.mesa_include = args.mesa_include.expanduser().resolve()
    if sys.byteorder != 'little':
        parser.error('this evidence format currently requires a little-endian host')
    run = args.scratch_root / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + str(os.getpid()))
    run.mkdir(parents=True, exist_ok=False)
    print(f'Compute evidence: {run}', flush=True)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(PREFIXES) and key not in ('LD_PRELOAD', 'LD_LIBRARY_PATH')}
    env['LIBGL_ALWAYS_SOFTWARE'] = 'false'
    env['MESA_SHADER_CACHE_DISABLE'] = 'true'
    removed = sorted(key for key in os.environ if key not in env)
    metadata = {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'uname': list(platform.uname()), 'python': sys.version, 'device': args.device,
                'repo': str(REPO), 'removed_environment_keys': removed,
                'environment_overrides': {'LIBGL_ALWAYS_SOFTWARE': 'false', 'MESA_SHADER_CACHE_DISABLE': 'true'},
                'concurrent_workloads': 'Other agents may be active; no isolation or timing claim.',
                'renderer_required': 'Apple M2 Max (G14C B1)', 'drm_driver_required': 'asahi'}
    try:
        st = Path(args.device).stat()
        metadata['device_stat'] = {'rdev_major': os.major(st.st_rdev), 'rdev_minor': os.minor(st.st_rdev), 'mode': oct(st.st_mode)}
    except OSError as exc:
        metadata['device_stat_error'] = str(exc)
    write_json(run / 'environment.json', metadata)
    sources = run / 'sources'; sources.mkdir()
    source_paths = [REPO / 'tests/gles_compute.c', Path(__file__).resolve()]
    for path in source_paths:
        shutil.copy2(path, sources / path.name)
    headers = [p for sub in ('EGL', 'GLES3', 'KHR') for p in (args.mesa_include / sub).glob('*.h')]
    headers += [Path('/usr/include/drm/drm.h'), Path('/usr/include/drm/drm_mode.h')]
    write_json(run / 'source-hashes.json', {str(p): sha(p) for p in source_paths + headers if p.is_file()})
    libs = [Path('/usr/lib64') / name for name in ('libEGL.so.1', 'libEGL_mesa.so.0', 'libgallium-25.1.9.so')]
    write_json(run / 'runtime-hashes.json', {str(p): {'resolved_path': str(p.resolve()), 'sha256': sha(p)} for p in libs if p.is_file()})
    inventory = run / 'inventory'; inventory.mkdir()
    inventory_record, _, _ = command(['rpm', '-q', 'mesa-dri-drivers', 'mesa-libEGL', 'libdrm', 'gcc', 'glibc'], inventory, env, 10)
    version_dir = run / 'compiler'; version_dir.mkdir()
    compiler = shlex.split(os.environ.get('CC', 'cc'))
    command(compiler + ['--version'], version_dir, env, 10)
    build = run / 'build'; build.mkdir()
    binary = run / 'gles_compute'
    build_record, _, _ = command(compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                                  '-MD', '-MF', str(build / 'dependencies.d'),
                                  '-I' + str(args.mesa_include), str(sources / 'gles_compute.c'), '-ldl', '-o', str(binary)], build, env, 30)
    summary = {'pass': False, 'build': build_record, 'package_inventory': inventory_record,
               'cases': [], 'negative_tests': {}, 'failure': None,
               'suite': 'smoke' if args.smoke else 'full'}
    try:
        if build_record['returncode'] != 0 or build_record['timed_out']:
            raise RuntimeError('compile failed or timed out')
        dependency_text = (build / 'dependencies.d').read_text().replace('\\\n', ' ')
        dependencies = [Path(value) for value in shlex.split(dependency_text.split(':', 1)[1])]
        write_json(run / 'build-dependency-hashes.json', {str(p): sha(p) for p in dependencies})
        summary['binary_sha256'] = sha(binary)
        if args.smoke:
            cases = [('control', 32), ('constant', 32), ('index', 33)]
        else:
            cases = [('control', 32), ('constant', 32), ('constant', 32), ('control', 32)]
            for repeat in range(2):
                for mode in ('constant', 'index'):
                    for n in (1, 32, 33, 65, 257):
                        cases.append((mode, n))
            cases.append(('control', 257))
        last_index = None
        for number, (mode, n) in enumerate(cases):
            directory = run / f'{number:02d}-{mode}-{n}'; directory.mkdir()
            rec, stdout, _ = command([str(binary), mode, str(n), args.device], directory, env, 15)
            result = {'directory': directory.name, 'command': rec, 'mode': mode, 'count': n}
            summary['cases'].append(result)
            if rec['returncode'] != 0 or rec['timed_out'] or 'READBACK_COMPLETE' not in stdout:
                raise RuntimeError(f'{directory.name}: API/timeout failure; no further dispatches')
            result['verification'] = verify(directory, mode, n)
            if not result['verification']['pass']:
                raise RuntimeError(f'{directory.name}: readback mismatch; no further dispatches')
            if mode == 'index':
                last_index = directory
            print(f'PASS {directory.name}', flush=True)
        # Deliberately wrong oracle on an already captured GPU output. No GPU/CPU buffer mutation.
        actual = (last_index / 'output.bin').read_bytes()
        wrong = bytearray((last_index / 'expected.bin').read_bytes()); wrong[8*4] ^= 1
        negative = run / 'negative-oracle'; negative.mkdir()
        (negative / 'expected-wrong.bin').write_bytes(wrong)
        rejection = mismatch(actual, wrong)
        accepted = bool(rejection and rejection.get('mismatch_count') == 1 and
                        rejection['first_mismatches'][0]['word'] == 8)
        summary['negative_tests']['oracle_mismatch'] = {'pass': accepted, 'actual_from': last_index.name + '/output.bin', 'rejection': rejection}
        write_json(negative / 'verification.json', summary['negative_tests']['oracle_mismatch'])
        if not accepted:
            raise RuntimeError('wrong oracle was not correctly rejected')
        directory = run / 'negative-invalid-shader'; directory.mkdir()
        rec, stdout, stderr = command([str(binary), 'invalid', '32', args.device], directory, env, 15)
        accepted = (rec['returncode'] == 3 and not rec['timed_out'] and 'compile_status=0' in stdout and
                    'stage=shader-compile' in stderr and 'dispatch_count=' not in stdout and
                    (directory / 'compile.log').is_file() and bool((directory / 'compile.log').read_bytes()) and
                    not (directory / 'output.bin').exists())
        summary['negative_tests']['invalid_shader'] = {'pass': accepted, 'command': rec}
        if not accepted:
            raise RuntimeError('invalid shader did not fail at compilation as expected')
        directory = run / 'negative-device'; directory.mkdir()
        # Refuse a mismatched EGL node before shader creation/submission.
        rec, stdout, stderr = command([str(binary), 'control', '32', '/dev/dri/intentionally-wrong-node'], directory, env, 15)
        accepted = rec['returncode'] == 1 and not rec['timed_out'] and 'stage=render-node-identity' in stderr and 'compile_status=' not in stdout
        summary['negative_tests']['device_identity'] = {'pass': accepted, 'command': rec}
        if not accepted:
            raise RuntimeError('mismatched device was not rejected')
        directory = run / 'final-control'; directory.mkdir()
        rec, stdout, _ = command([str(binary), 'control', '32', args.device], directory, env, 15)
        if rec['returncode'] != 0 or rec['timed_out'] or 'READBACK_COMPLETE' not in stdout:
            raise RuntimeError('final control API/timeout failure')
        final = verify(directory, 'control', 32)
        summary['final_control'] = {'command': rec, 'verification': final}
        if not final['pass']:
            raise RuntimeError('final control readback failed')
        summary['pass'] = True
    except (OSError, RuntimeError, ValueError) as exc:
        summary['failure'] = str(exc)
        print(f'FAIL: {exc}', file=sys.stderr)
    finally:
        write_json(run / 'summary.json', summary)
        write_json(run / 'manifest.json', {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file() and p.name not in ('gles_compute', 'manifest.json')})
    print('PASS: bounded hardware compute and negative controls' if summary['pass'] else 'FAIL: see retained evidence', flush=True)
    return 0 if summary['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
