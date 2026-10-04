#!/usr/bin/env python3
"""Bounded G14C B1 imadd addend-C 0->1 hardware probe on the pinned index blob.

Reuses the proven Vulkan delivery harness (tests/vulkan_compute.c), the
SPIR-V producer and the pinned-baseline infrastructure of
run_vulkan_compute.py without editing them, plus the standalone pinned
patcher patch_agx_imadd.py. Matrix: unchanged before/after controls at
count 33, patched imports at counts 33 and 257, a stale-digest import that
must be rejected before submission, a wrong-node identity control and a
no-dispatch control. Every readback is checked against a full-buffer
uint32 oracle including guards, rounded inactive lanes and the patterned
tail. Stops on any unexpected import, completion or oracle failure.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_vulkan_compute as baseline  # Reused unedited: SPIR-V producer, pins, helpers.

REPO = Path(__file__).resolve().parents[1]
PATCHER = REPO / 'scripts/patch_agx_imadd.py'
CONTROL_SHA256 = 'd0b99dace1de6eb2467c64ce872e8f5c02458d1edae0a3f74b9ed2c17cff0ba3'
PATCHED_SHA256 = 'b84264e4e41404eae35fc9f50c05c271e292bb6998c8e37a88e07aec53f07362'
STALE_SHA256 = '533c0387abb797e05f40f9d0a387acef66008179a4632df0acd7be55ac645d9b'
MULTIPLIER = 0x9e3779b9
XOR_LITERAL = 0x12345678
INCOMPATIBLE_SHADER_BINARY = 1000482000  # VK_ERROR_INCOMPATIBLE_SHADER_BINARY_EXT
MODEL_SHA256 = '986f6c6ec5547c5f61e357c7c0df614cb05b3382eed705d4ef7a79c4d3a2c46f'
DISASM_SHA256 = 'e7ef4908a0e35fb62c4c81b8f063f5235cec0221cd377fd3fdfe23981a0b86bd'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, value):
    p.write_text(json.dumps(value, indent=2) + '\n')


def oracle(data, count, addend, control=False):
    """Full-buffer uint32 expectation: payload, guards, inactive lanes, tail."""
    rounded = (count + 31) // 32 * 32
    expected = [0xcdcdcdcd] * (8 + rounded + 8) + [0xa5a50000 + j for j in range(16)]
    if not control:
        for i in range(count):
            expected[8 + i] = (((i * MULTIPLIER) + addend) & 0xffffffff) ^ XOR_LITERAL
    actual = list(struct.unpack('<' + 'I' * (len(data) // 4), data)) if len(data) % 4 == 0 else []
    return {'passed': actual == expected, 'expected': expected, 'actual': actual}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    p.add_argument('--include', type=Path, default=Path('/save/workspace/AGX_Probe/mesa/include'))
    p.add_argument('--grammar', type=Path, default=Path('/save/workspace/AGX_Probe/mesa/src/compiler/spirv/spirv.core.grammar.json'))
    p.add_argument('--runtime', type=Path, default=Path('/scratch/apple-m2-playground/vulkan-runtime/usr/lib64'))
    args = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = (args.output or Path('/scratch/apple-m2-playground/agx-imadd-addend-runs') / stamp).resolve()
    out.mkdir(parents=True, exist_ok=False)
    summary = {'passed': False, 'utc': stamp, 'commands': [], 'cases': [],
               'pinned': {'control_sha256': CONTROL_SHA256, 'patched_sha256': PATCHED_SHA256,
                          'stale_sha256': STALE_SHA256, 'driver_sha256': baseline.DRIVER_HASH,
                          'model_sha256': MODEL_SHA256, 'disassembler_sha256': DISASM_SHA256,
                          'addend_before': 0, 'addend_after': 1}}
    prefixes = ('VK_', 'MESA_', 'ASAHI_', 'AGX_', 'HK_', 'LIBGL_', 'GALLIUM_', 'DRI_', 'LD_')
    env = {k: v for k, v in os.environ.items() if not k.startswith(prefixes)}
    overrides = {'VK_DRIVER_FILES': str(baseline.ICD), 'VK_ICD_FILENAMES': str(baseline.ICD),
                 'VK_LOADER_LAYERS_DISABLE': '~implicit~', 'LD_LIBRARY_PATH': str(args.runtime.resolve()),
                 'MESA_SHADER_CACHE_DISABLE': 'true'}
    child = env | overrides
    summary['removed_environment_keys'] = sorted(set(os.environ) - set(env))
    summary['child_overrides'] = overrides

    def run(argv, name, timeout=15, child_env=env, success=True):
        directory = out / name
        directory.mkdir()
        record = {'argv': [str(x) for x in argv], 'timeout_seconds': timeout}
        summary['commands'].append(record)
        try:
            result = subprocess.run(record['argv'], env=child_env, capture_output=True, timeout=timeout)
            stdout, stderr = result.stdout, result.stderr
            record['returncode'] = result.returncode
        except subprocess.TimeoutExpired as e:
            stdout, stderr = e.stdout or b'', e.stderr or b''
            record['timed_out'] = True
            record['returncode'] = None
        (directory / 'stdout.txt').write_bytes(stdout)
        (directory / 'stderr.txt').write_bytes(stderr)
        dump(directory / 'command.json', record)
        if success and record['returncode'] != 0:
            raise RuntimeError('command failed: ' + name)
        return stdout, record

    try:
        sources = out / 'sources'
        sources.mkdir()
        for f in [REPO / 'tests/vulkan_compute.c', REPO / 'scripts/run_vulkan_compute.py', PATCHER, Path(__file__)]:
            shutil.copy2(f, sources / f.name)
        files = [baseline.DRIVER, baseline.ICD, Path('/usr/lib64/libvulkan.so.1'), args.runtime / 'libdisplay-info.so.2',
                 args.grammar, REPO / 'tests/vulkan_compute.c', REPO / 'scripts/run_vulkan_compute.py', PATCHER,
                 Path(__file__), Path('/usr/lib64/libSPIRV-Tools-shared.so')]
        files += sorted(args.include.glob('vulkan/*.h')) + sorted(args.include.glob('vk_video/*.h'))
        summary['sha256'] = {str(f.resolve()): sha(f) for f in files}
        if sha(baseline.DRIVER) != baseline.DRIVER_HASH:
            raise RuntimeError('actual driver hash changed')
        for name, pinned in [('applegpu.py', MODEL_SHA256), ('disassemble.py', DISASM_SHA256)]:
            if sha(Path('/save/workspace/AGX_Probe/applegpu') / name) != pinned:
                raise RuntimeError('model hash mismatch: ' + name)
        run(shlex.split(args.cc) + ['--version'], 'compiler')
        binary = out / 'vulkan_compute'
        run(shlex.split(args.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-MD', '-MF', out / 'dependencies.d',
            '-I' + str(args.include.resolve()), REPO / 'tests/vulkan_compute.c', '-ldl', '-o', binary], 'build', 30)
        summary['executable_sha256'] = sha(binary)
        deptext = (out / 'dependencies.d').read_text().replace('\\\n', ' ')
        summary['build_dependency_hashes'] = {str(Path(f).resolve()): sha(f) for f in shlex.split(deptext.split(':', 1)[1])}
        depout, _ = run(['ldd', baseline.DRIVER], 'dependencies', child_env=child)
        if b'not found' in depout:
            raise RuntimeError('unresolved runtime dependency')
        # Hash the resolved ICD dependency closure without extending capability inventory.
        deps = []
        for line in depout.decode().splitlines():
            fields = line.split()
            candidate = fields[2] if '=>' in fields and len(fields) > 2 else fields[0] if fields else ''
            if candidate.startswith('/') and Path(candidate).is_file():
                deps.append(Path(candidate))
        summary['runtime_dependency_hashes'] = {str(f.resolve()): sha(f) for f in deps}
        runtime_files = [baseline.DRIVER, Path('/usr/lib64/libvulkan.so.1'), args.runtime / 'libdisplay-info.so.2'] + deps
        runtime_expected = {str(f): sha(f) for f in runtime_files}
        summary['runtime_expected'] = runtime_expected

        def verify_runtime():
            if {str(f): sha(f) for f in runtime_files} != runtime_expected:
                raise RuntimeError('runtime changed during suite')

        module = baseline.spirv('index', args.grammar, out)
        stdout, _ = run([sys.executable, REPO / 'scripts/run_vulkan_compute.py', '--validate', module], 'validate-index')
        summary['index_validation'] = json.loads(stdout)

        def case(name, mode, code, n, addend, control=False):
            verify_runtime()
            input_hash = sha(code)
            readback = out / (name + '.readback')
            exported = out / 'index.bin'
            stdout, record = run([binary, mode, code, n, '/dev/dri/renderD128', readback, exported], name, child_env=child)
            verify_runtime()
            events = [json.loads(line) for line in stdout.decode().splitlines()]
            if not events or events[-1].get('completed') is not True:
                raise RuntimeError('missing completion')
            check = oracle(readback.read_bytes(), n, addend, control)
            check.update(name=name, mode=mode, count=n, addend=addend, input_sha256=input_hash,
                         readback_sha256=sha(readback), api_events=events)
            dump(out / (name + '-oracle.json'), check)
            summary['cases'].append(check)
            if not check['passed'] or sha(code) != input_hash:
                raise RuntimeError('oracle/input changed: ' + name)

        case('no-dispatch', 'control', module, 33, 0, control=True)
        case('index-source-33', 'export', module, 33, 0)
        if sha(out / 'index.bin') != CONTROL_SHA256:
            raise RuntimeError('exported index binary does not match the pinned baseline hash')
        summary['index_binary'] = {'bytes': (out / 'index.bin').stat().st_size, 'sha256': CONTROL_SHA256}
        patch_dir = out / 'imadd-patch'
        run([sys.executable, PATCHER, out / 'index.bin', '--output', patch_dir], 'patcher')
        if sha(patch_dir / 'patched.bin') != PATCHED_SHA256 or sha(patch_dir / 'stale-integrity.bin') != STALE_SHA256:
            raise RuntimeError('patcher output hash mismatch')
        case('imadd-before-33', 'import', out / 'index.bin', 33, 0)
        case('imadd-patched-33', 'import', patch_dir / 'patched.bin', 33, 1)
        case('imadd-patched-257', 'import', patch_dir / 'patched.bin', 257, 1)
        case('imadd-after-33', 'import', out / 'index.bin', 33, 0)
        # Stale-digest import must be rejected at shader creation, before any submission.
        stdout, record = run([binary, 'import', patch_dir / 'stale-integrity.bin', 33, '/dev/dri/renderD128',
                              out / 'stale.readback', out / 'unused.bin'], 'stale-integrity', child_env=child, success=False)
        events = [json.loads(line) for line in stdout.decode().splitlines()]
        create = [e for e in events if e.get('api') == 'vkCreateShadersEXT']
        if (record['returncode'] != 1 or len(create) != 1 or create[0]['result'] != INCOMPATIBLE_SHADER_BINARY or
                any(e.get('api') == 'vkQueueSubmit' for e in events) or (out / 'stale.readback').exists()):
            raise RuntimeError('stale integrity not rejected before submission')
        summary['stale_integrity_control'] = {'passed': True, 'api_events': events,
                                              'sha256': sha(patch_dir / 'stale-integrity.bin')}
        # Fail closed on an existing wrong character device, before logical-device creation.
        stdout, record = run([binary, 'import', out / 'index.bin', 33, '/dev/null', out / 'wrong.readback',
                              out / 'unused.bin'], 'wrong-node', child_env=child, success=False)
        if record['returncode'] != 1 or b'vkCreateDevice' in stdout or (out / 'wrong.readback').exists():
            raise RuntimeError('negative identity control did not fail before device creation')
        summary['wrong_node_control_passed'] = True
        # This software control checks that a no-dispatch sentinel cannot satisfy the payload oracle.
        summary['no_dispatch_rejected_as_dispatch'] = not oracle((out / 'no-dispatch.readback').read_bytes(), 33, 0)['passed']
        if not summary['no_dispatch_rejected_as_dispatch']:
            raise RuntimeError('oracle control failed')
        summary['instruction_patch'] = json.loads((patch_dir / 'patch.json').read_text())
        verify_runtime()
        summary['runtime_unchanged_before_after_each_case'] = True
        summary['passed'] = True
    except Exception as e:
        summary['error'] = f'{type(e).__name__}: {e}'
    finally:
        dump(out / 'record.json', summary)
        print(json.dumps({'passed': summary['passed'], 'output': str(out), 'error': summary.get('error')}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
