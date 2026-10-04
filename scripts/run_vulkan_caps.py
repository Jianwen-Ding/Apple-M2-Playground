#!/usr/bin/env python3
"""Isolated signed Fedora runtime setup and bounded Asahi capability query."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
RUNTIME = Path('/scratch/apple-m2-playground/vulkan-runtime')
ICD = Path('/usr/share/vulkan/icd.d/asahi_icd.aarch64.json')
HEADERS = Path('/save/workspace/AGX_Probe/mesa/include')
RPM_NAME = 'libdisplay-info-0.2.0-3.fc42.aarch64.signed.rpm'
RPM_URL = ('https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/42/'
           'Everything/aarch64/os/Packages/l/libdisplay-info-0.2.0-3.fc42.aarch64.rpm')
RPM_SHA256 = '86fa707a83121deb20435b225615b76ff96a39b9b6fe9163f07218596e589ce3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean_env():
    prefixes = ('VK_', 'MESA_', 'ASAHI_', 'AGX_', 'HK_', 'LIBGL_', 'GALLIUM_', 'DRI_', 'LD_')
    return {k: v for k, v in os.environ.items() if not k.startswith(prefixes)}


def extract_cpio(data, root):
    """Extract this pinned RPM's newc payload without a host cpio dependency."""
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('oversized payload')
    pos = 0
    files = []
    while pos + 110 <= len(data):
        h = data[pos:pos + 110]
        if h[:6] != b'070701':
            raise ValueError('not newc')
        fields = [int(h[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        pos += 110
        name = data[pos:pos + namesize - 1].decode()
        pos = (pos + namesize + 3) & ~3
        if name == 'TRAILER!!!':
            return files
        rel = Path(name.removeprefix('./'))
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] != 'usr':
            raise ValueError(f'unsafe member: {name}')
        target = root / rel
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError('member escapes root')
        body = data[pos:pos + size]
        if len(body) != size:
            raise ValueError('truncated member')
        pos = (pos + size + 3) & ~3
        target.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISDIR(mode):
            target.mkdir(exist_ok=True)
        elif stat.S_ISREG(mode):
            target.write_bytes(body)
            target.chmod(mode & 0o777)
        elif stat.S_ISLNK(mode):
            link = body.decode()
            if Path(link).is_absolute() or not (target.parent / link).resolve().is_relative_to(root.resolve()):
                raise ValueError('unsafe symlink')
            if target.is_symlink():
                target.unlink()
            elif target.exists():
                raise ValueError('symlink destination occupied')
            target.symlink_to(link)
        else:
            raise ValueError('unexpected member type')
        files.append({'path': str(rel), 'mode': oct(mode), 'size': size,
                      'sha256': hashlib.sha256(body).hexdigest()})
    raise ValueError('missing cpio trailer')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', action='store_true', help='download/verify/extract pinned signed runtime RPM')
    parser.add_argument('--without-runtime', action='store_true', help='record original missing-dependency control')
    parser.add_argument('--output', type=Path, help='new evidence directory; must not exist')
    parser.add_argument('--mesa-include', type=Path, default=HEADERS, help='read-only Vulkan header include root')
    args = parser.parse_args()
    headers = args.mesa_include.resolve()
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler:
        parser.error("CC must name a compiler")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = args.output or RUNTIME / 'runs' / stamp
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    summary = {'passed': False, 'utc': stamp, 'platform': platform.platform(),
               'runtime_enabled': not args.without_runtime, 'commands': commands}
    env = clean_env()

    def run(argv, timeout=15, child_env=None, binary=False, required=True):
        record = {'argv': [str(x) for x in argv], 'timeout_seconds': timeout}
        started = time.monotonic()
        commands.append(record)
        try:
            p = subprocess.Popen(record['argv'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=child_env or env, start_new_session=True)
            try:
                stdout, stderr = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    stdout, stderr = p.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    stdout, stderr = exc.output or b'', exc.stderr or b''
                record.update(timed_out=True, returncode=p.returncode,
                              elapsed_seconds=time.monotonic()-started,
                              stdout='<binary payload>' if binary else stdout.decode(errors='replace'),
                              stderr=stderr.decode(errors='replace'))
                raise RuntimeError('command timeout')
            record.update(returncode=p.returncode, elapsed_seconds=time.monotonic() - started,
                          stdout='<binary payload>' if binary else stdout.decode(errors='replace'),
                          stderr=stderr.decode(errors='replace'))
            if required and p.returncode:
                raise RuntimeError(f'command failed: {record["argv"]}')
            return stdout if binary else record['stdout']
        except OSError as e:
            record.update(returncode=None, launch_error=str(e), elapsed_seconds=time.monotonic()-started)
            raise

    try:
        if platform.machine() != 'aarch64':
            raise RuntimeError('aarch64 required')
        if args.setup:
            rpm = RUNTIME / 'downloads' / RPM_NAME
            rpm.parent.mkdir(parents=True, exist_ok=True)
            if not rpm.exists():
                with urllib.request.urlopen(RPM_URL, timeout=30) as response:
                    body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise ValueError('oversized RPM')
                rpm.write_bytes(body)
            if sha(rpm) != RPM_SHA256:
                raise ValueError('RPM sha256 mismatch')
            sig = run(['rpmkeys', '--checksig', '--verbose', rpm])
            if 'Signature, key ID 105ef944: OK' not in sig or 'Payload SHA256 digest: OK' not in sig:
                raise ValueError('Fedora 42 signature/payload verification missing')
            summary['package'] = {'url': RPM_URL, 'sha256': sha(rpm),
                                  'identity': run(['rpm', '-qp', '--qf', '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n', rpm]),
                                  'requires': run(['rpm', '-qp', '--requires', rpm]),
                                  'provides': run(['rpm', '-qp', '--provides', rpm]),
                                  'signature': sig,
                                  'extracted_members': extract_cpio(run(['rpm2cpio', rpm], binary=True), RUNTIME)}
            (RUNTIME / 'setup.json').write_text(json.dumps(summary['package'], indent=2) + '\n')
        summary['packages'] = run(['rpm', '-q', 'mesa-vulkan-drivers', 'vulkan-loader', 'glibc', 'libdrm'])
        summary['rpm_verification'] = run(['rpm', '-V', 'mesa-vulkan-drivers'], required=False)
        summary['icd_elf_notes'] = run(['readelf', '-n', '/usr/lib64/libvulkan_asahi.so'])
        summary['mesa_header_source_revision'] = run(['git', '-C', '/save/workspace/AGX_Probe/mesa', 'rev-parse', 'HEAD']).strip()
        summary['system_dependency_control'] = run(['ldd', '/usr/lib64/libvulkan_asahi.so'], required=False)
        overrides = {'VK_DRIVER_FILES': str(ICD), 'VK_ICD_FILENAMES': str(ICD),
                     'VK_LOADER_LAYERS_DISABLE': '~implicit~', 'VK_LOADER_DEBUG': 'error,warn,driver'}
        if not args.without_runtime:
            library = RUNTIME / 'usr/lib64/libdisplay-info.so.2'
            if not library.exists():
                raise RuntimeError('runtime missing; run --setup first')
            overrides['LD_LIBRARY_PATH'] = str(RUNTIME / 'usr/lib64')
        child_env = env | overrides
        summary['child_environment_overrides'] = overrides
        summary['icd_manifest'] = json.loads(ICD.read_text())
        if summary['icd_manifest']['ICD']['library_path'] != '/usr/lib64/libvulkan_asahi.so':
            raise ValueError('unexpected Asahi ICD path')
        files = [REPO / 'tests/vulkan_caps.c', Path(__file__), ICD,
                 Path('/usr/lib64/libvulkan_asahi.so'), Path('/usr/lib64/libvulkan.so.1'),
                 Path('/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-42-primary')]
        files += sorted((headers / 'vulkan').glob('*.h'))
        files += sorted((headers / 'vk_video').glob('*.h'))
        if not args.without_runtime:
            files += [RUNTIME / 'usr/lib64/libdisplay-info.so.0.2.0']
            summary['runtime_dependency_check'] = run(['ldd', RUNTIME / 'usr/lib64/libdisplay-info.so.2'], child_env=child_env)
            summary['repaired_icd_dependency_check'] = run(['ldd', '/usr/lib64/libvulkan_asahi.so'], child_env=child_env)
            if 'not found' in summary['repaired_icd_dependency_check']:
                raise RuntimeError('unresolved ICD dependency')
        summary['sha256'] = {str(f): sha(f) for f in files}
        sources = out / 'sources'
        sources.mkdir()
        for source in (REPO / 'tests/vulkan_caps.c', Path(__file__).resolve()):
            shutil.copy2(source, sources / source.name)
        summary['header_include_root'] = str(headers)
        summary['compiler'] = run(compiler + ['--version'])
        binary = out / 'vulkan_caps'
        run(compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-I' + str(headers),
             sources / 'vulkan_caps.c', '-ldl', '-o', binary], timeout=30)
        summary['binary_sha256'] = sha(binary)
        output = run([binary], child_env=child_env, required=False)
        (out / 'stdout.json').write_text(output)
        (out / 'loader.stderr.txt').write_text(commands[-1]['stderr'])
        caps = json.loads(output)
        summary['capabilities'] = caps
        node = Path('/dev/dri/renderD128').stat()
        summary['expected_render_node'] = {'path': '/dev/dri/renderD128',
                                           'major': os.major(node.st_rdev), 'minor': os.minor(node.st_rdev)}
        device = caps.get('device', {})
        summary['passed'] = bool(commands[-1]['returncode'] == 0 and caps.get('accepted_asahi') and
                                 device.get('render_major') == os.major(node.st_rdev) and
                                 device.get('render_minor') == os.minor(node.st_rdev))
    except Exception as e:
        summary['error'] = f'{type(e).__name__}: {e}'
    finally:
        (out / 'record.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps({'passed': summary['passed'], 'output': str(out), 'error': summary.get('error')}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
