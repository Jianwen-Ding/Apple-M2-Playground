#!/usr/bin/env python3
"""Bounded GLES timer API calibration; independent modulo-2^32 readback oracle."""
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


def verify(directory, mode, repeats):
    seeds = [0x12345678 ^ ((i*0x9e3779b9) & 0xffffffff) for i in range(64)]
    expected = [SENTINEL]*80
    if mode in ('elapsed', 'pair'):
        for i, x in enumerate(seeds):
            for _ in range(repeats):
                x = (x*1664525 + 1013904223) & 0xffffffff
            expected[8+i] = x
    references = {'input.bin': pack([SENTINEL]*80), 'output.bin': pack(expected),
                  'control-input.bin': pack([0xa5a50000+i for i in range(16)]),
                  'control-output.bin': pack([0xa5a50000+i for i in range(16)]),
                  'seeds.bin': pack(seeds), 'seeds-output.bin': pack(seeds)}
    (directory/'expected.bin').write_bytes(pack(expected))
    checks = {name: mismatch((directory/name).read_bytes(), ref)
              for name, ref in references.items()}
    result = {'pass': all(v is None for v in checks.values()), 'checks': checks,
              'output_words': 64, 'prefix_guard_words': 8, 'suffix_guard_words': 8,
              'untouched_control_words': 16, 'unchanged_seed_words': 64}
    write_json(directory/'verification.json', result)
    return result


def assess(timing):
    mode = timing['mode']
    raw = timing['raw_u64']
    host = timing['host_monotonic_s']
    result = {'host_fence_ns': (host[1]-host[0])*1e9,
              'host_readback_ns': (host[3]-host[0])*1e9, 'issues': []}
    if mode == 'control':
        return result
    if timing['disjoint_before'] or timing['disjoint_after']:
        result['issues'].append('disjoint flag set')
    pair = mode in ('pair', 'empty-pair')
    delta = raw[1]-raw[0] if pair else raw[0]
    result['api_delta_ns'] = delta
    if delta < 0:
        result['issues'].append('backward timestamp pair')
    if delta == 0:
        result['issues'].append('zero result; unusable for workload timing')
    # A loaded interval must fit inside its host start-to-result bracket.
    # No physical timer resolution is inferred from this plausibility check.
    if delta > (host[2]-host[0])*1e9 + 1_000_000:
        result['issues'].append('result exceeds enclosing host bracket by >1 ms')
    if pair and (raw[0] == 0 or raw[1] == 0):
        result['issues'].append('zero timestamp boundary')
    result['numerically_plausible'] = not result['issues']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-root', type=Path, default=Path('/scratch/apple-m2-playground/gles-timing'))
    parser.add_argument('--mesa-include', type=Path, default=Path('/save/workspace/AGX_Probe/mesa/include'))
    parser.add_argument('--device', default='/dev/dri/renderD128')
    args = parser.parse_args()
    compiler = shlex.split(os.environ.get('CC', 'cc'))
    if not compiler:
        parser.error('CC must name a compiler')
    if sys.byteorder != 'little':
        parser.error('requires little endian host')
    run = args.scratch_root.resolve()/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+str(os.getpid()))
    run.mkdir(parents=True)
    print(f'Timing evidence: {run}', flush=True)
    env = {k:v for k,v in os.environ.items() if not k.startswith(PREFIXES) and k not in ('LD_PRELOAD','LD_LIBRARY_PATH')}
    env.update(LIBGL_ALWAYS_SOFTWARE='false', MESA_SHADER_CACHE_DISABLE='true')
    write_json(run/'environment.json', {'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'uname':list(platform.uname()), 'device':args.device, 'repo':str(REPO),
        'removed_environment_keys':sorted(k for k in os.environ if k not in env),
        'overrides':{k:env[k] for k in ('LIBGL_ALWAYS_SOFTWARE','MESA_SHADER_CACHE_DISABLE')},
        'concurrency':'Other agents may be active; no isolated performance claims.',
        'clock_temperature':'Not measured; host CLOCK_MONOTONIC and API ns only.',
        'bounds':{'child_seconds':12,'fence_seconds':2,'availability_seconds':2,
                  'max_lanes':64,'max_recurrence_iterations':256,'timing_schedule_seconds':60,
                  'final_no_dispatch_control_seconds':12}})
    sources = run/'sources'; sources.mkdir()
    for p in (REPO/'tests/gles_time.c', Path(__file__).resolve()):
        shutil.copy2(p,sources/p.name)
    libs = [Path('/usr/lib64')/n for n in ('libEGL.so.1','libEGL_mesa.so.0','libgallium-25.1.9.so')]
    write_json(run/'runtime-hashes.json',{str(p):{'resolved':str(p.resolve()),'sha256':sha(p)} for p in libs if p.is_file()})
    inventory = run/'inventory'; inventory.mkdir()
    command(['rpm','-q','mesa-dri-drivers','mesa-libEGL','libdrm','gcc','glibc'], inventory,env,10)
    build = run/'build'; build.mkdir()
    binary = run/'gles_time'
    rec,_,_ = command(compiler+['-std=c11','-Wall','-Wextra','-Werror','-O2','-MD','-MF',str(build/'dependencies.d'),
         '-I'+str(args.mesa_include.resolve()),str(sources/'gles_time.c'),'-ldl','-o',str(binary)],build,env,30)
    summary = {'build':rec,'execution_verified':False,'timers_usable':False,'cases':[], 'failure':None,
               'calibration_failure':None, 'calibration_status':'NOT_COMPLETED',
               'interpretation':'API calibration only; no ISA latency or physical cycles.'}
    deadline = time.monotonic()+60
    def case(label, mode, repeats):
        directory=run/label; directory.mkdir()
        remaining=deadline-time.monotonic()
        if remaining <= 0:
            raise RuntimeError('suite deadline; no further timing dispatches')
        rec,stdout,_=command([str(binary),mode,str(repeats),'64',args.device],directory,env,min(12,remaining))
        result={'directory':label,'mode':mode,'repeats':repeats,'command':rec}
        summary['cases'].append(result)
        if rec['returncode'] != 0 or rec['timed_out'] or 'READBACK_COMPLETE' not in stdout:
            raise RuntimeError(label+': API/process failure; stopped scaling')
        result['verification']=verify(directory,mode,repeats)
        if not result['verification']['pass']:
            raise RuntimeError(label+': exact readback failure; stopped scaling')
        result['timing']=json.loads((directory/'timing.json').read_text())
        result['assessment']=assess(result['timing'])
        print(f'CHECKED {label}: {result["assessment"].get("issues",[])}',flush=True)
        return result
    try:
        if rec['returncode'] != 0 or rec['timed_out']:
            raise RuntimeError('build failed')
        deps=(build/'dependencies.d').read_text().replace('\\\n',' ')
        paths=[Path(p) for p in shlex.split(deps.split(':',1)[1])]
        write_json(run/'build-dependency-hashes.json',{str(p):sha(p) for p in paths})
        summary['binary_sha256']=sha(binary)
        case('00-initial-control','control',0)
        case('01-empty-elapsed','empty',0)
        case('02-empty-pair','empty-pair',0)
        # Fixed modest schedule, no adaptive escalation on unusable numerical results.
        # GL errors/timeouts/readback failures terminate this schedule immediately.
        case('03-warmup-elapsed','elapsed',0)
        case('04-warmup-pair','pair',0)
        number=5
        for repeats in (0,64,256):
            for sample in range(3):
                for mode in ('elapsed','pair'):
                    case(f'{number:02d}-{mode}-r{repeats}-s{sample}',mode,repeats)
                    number+=1
        summary['execution_verified']=True
        loaded=[c for c in summary['cases'] if c['mode'] in ('elapsed','pair')]
        summary['loaded_results_plausible']=all(c['assessment'].get('numerically_plausible',False) for c in loaded)
        # Plausibility alone does not establish command boundaries or calibration.
        invalid = [c['directory'] for c in summary['cases']
                   if c['mode'] != 'control' and c['assessment']['issues']]
        summary['invalid_timer_cases'] = invalid
        summary['calibration_status'] = 'FAIL_INVALID_TIMER' if invalid else 'FAIL_UNCALIBRATED'
        summary['calibration_failure'] = ('Invalid numerical timer results; see invalid_timer_cases. Timestamp pairs remain uncalibrated.'
            if invalid else 'Numerical plausibility only; independent command reference still required.')
        # Test the independent oracle on captured bytes without any further dispatch.
        actual=(run/loaded[-1]['directory']/'output.bin').read_bytes()
        expected=bytearray((run/loaded[-1]['directory']/'expected.bin').read_bytes())
        expected[32]^=1
        rejection=mismatch(actual,expected)
        summary['negative_oracle']=rejection
        if not rejection or rejection.get('mismatch_count') != 1:
            raise RuntimeError('negative oracle failed')
    except (RuntimeError,OSError,ValueError) as exc:
        summary['failure']=str(exc)
    finally:
        # Always attempt one bounded unchanged readback control after a runtime failure.
        # No compute dispatch occurs in this recovery control.
        if binary.exists() and rec['returncode']==0:
            try:
                deadline=max(deadline,time.monotonic()+12)
                summary['final_control']=case('final-control','control',0)
            except (RuntimeError,OSError,ValueError) as exc:
                summary['final_control_failure']=str(exc)
                summary['execution_verified']=False
                summary['failure']=summary['failure'] or ('final control: '+str(exc))
        write_json(run/'summary.json',summary)
        write_json(run/'manifest.json',{str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*'))
            if p.is_file() and p.name not in ('manifest.json','gles_time')})
    print(json.dumps({k:summary[k] for k in ('execution_verified','timers_usable','failure','calibration_status','calibration_failure')}),flush=True)
    # Unusable timer results are a retained calibration failure even if execution passes.
    return 0 if summary['execution_verified'] and summary['timers_usable'] and not summary['failure'] else 1


if __name__ == '__main__':
    sys.exit(main())
