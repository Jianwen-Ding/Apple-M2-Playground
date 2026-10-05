#!/usr/bin/env python3
"""Serial bounded AGX special-register scan, with known controls and guarded output."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import struct
import subprocess
import time

import patch_agx_sr as patcher
import run_vulkan_compute as baseline

REPO = Path(__file__).resolve().parents[1]
KNOWN = {80: lambda i: i, 0: lambda i: i//32, 4: lambda i: 32,
         5: lambda i: 1, 6: lambda i: 1, 48: lambda i: i%32,
         51: lambda i: i%32, 52: lambda i: i%32, 53: lambda i: 0}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_buffer(data, count, expected=None, pairs=False):
    rounded = (count+31)//32*32
    if len(data) != (rounded+32)*4:
        raise ValueError('wrong readback size')
    words = list(struct.unpack('<'+'I'*(rounded+32), data))
    active_words=count*(2 if pairs else 1)
    if active_words>rounded: raise ValueError('payload exceeds child allocation')
    untouched = list(range(8))+list(range(8+active_words, rounded+16))+list(range(rounded+16, rounded+32))
    initial = [0xcdcdcdcd]*(rounded+16)+[0xa5a50000+j for j in range(16)]
    if any(words[i] != initial[i] for i in untouched):
        raise ValueError('guard/inactive/tail corruption')
    values = words[8:8+active_words]
    expected_words=[expected(i) for i in range(count) for _ in range(2 if pairs else 1)] if expected is not None else None
    if expected is not None and values != expected_words:
        raise ValueError('known selector/control oracle mismatch')
    return values


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selectors', default='all', help='all or comma-separated numbers')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--count', type=int, default=257)
    p.add_argument('--spacing-ms', type=int, default=20)
    p.add_argument('--max-failures', type=int, default=8)
    p.add_argument('--pair-gap', type=int, help='two reads per lane with 0..256 intervening integer adds; count <=16')
    p.add_argument('--output', type=Path)
    p.add_argument('--runtime', type=Path, default=Path('/scratch/apple-m2-playground/vulkan-runtime/usr/lib64'))
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if not (1 <= a.count <= 257 and 2 <= a.repeats <= 5 and 0 <= a.spacing_ms <= 1000 and 1 <= a.max_failures <= 256):
        p.error('bounded count/repeats/spacing/failures required')
    if a.pair_gap is not None and not (0<=a.pair_gap<=256 and a.count<=16):
        p.error('pair-gap 0..256 requires count <=16')
    selectors = list(range(256)) if a.selectors == 'all' else [int(s) for s in a.selectors.split(',')]
    if len(set(selectors)) != len(selectors) or any(not 0 <= s <= 255 for s in selectors):
        p.error('unique selectors 0..255 required')
    # Known read controls first; FIFO-associated selectors last, still scanned.
    priority = [80,0,4,5,6,48,51,52,53,20,21]
    selectors = [s for s in priority if s in selectors]+[s for s in selectors if s not in priority and s not in (144,146,147)]+[s for s in (144,146,147) if s in selectors]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/sr-scan-runs')/stamp
    out.mkdir(parents=True, exist_ok=False)
    state = {'passed': False, 'complete': False, 'utc': stamp, 'requested': selectors,
             'count': a.count, 'repeats': a.repeats, 'spacing_ms': a.spacing_ms,
             'pair_gap': a.pair_gap,
             'commands': [], 'observations': [], 'controls': [], 'failures': []}
    def save():
        (out/'record.json').write_text(json.dumps(state, indent=2)+'\n')
    env = {k:v for k,v in os.environ.items() if not k.startswith(('VK_','MESA_','ASAHI_','AGX_','HK_','LIBGL_','GALLIUM_','DRI_','LD_'))}
    child = env | {'VK_DRIVER_FILES': str(baseline.ICD), 'VK_ICD_FILENAMES': str(baseline.ICD),
                   'VK_LOADER_LAYERS_DISABLE': '~implicit~', 'LD_LIBRARY_PATH': str(a.runtime.resolve()),
                   'MESA_SHADER_CACHE_DISABLE': 'true'}
    def run(argv, name, seconds=15, execute_env=child):
        folder = out/name; folder.mkdir()
        command = {'argv': list(map(str,argv)), 'timeout_seconds': seconds, 'host_before_ns': time.monotonic_ns()}
        try:
            result = subprocess.run(command['argv'], env=execute_env, capture_output=True, timeout=seconds)
            stdout, stderr = result.stdout, result.stderr
            command['returncode'] = result.returncode
        except subprocess.TimeoutExpired as e:
            stdout, stderr = e.stdout or b'', e.stderr or b''
            command.update(returncode=None, timed_out=True)
        command['host_after_ns'] = time.monotonic_ns()
        (folder/'stdout.txt').write_bytes(stdout); (folder/'stderr.txt').write_bytes(stderr)
        (folder/'command.json').write_text(json.dumps(command, indent=2)+'\n')
        state['commands'].append(command); save()
        if command['returncode'] != 0:
            raise RuntimeError('child failed: '+name)
        return stdout,command
    try:
        state['environment'] = {'kernel': platform.uname()._asdict(), 'child_environment_overrides': {k:v for k,v in child.items() if env.get(k)!=v}}
        sources = out/'sources'; sources.mkdir()
        paths = [Path(__file__), REPO/'scripts/patch_agx_sr.py', REPO/'scripts/patch_agx_imadd.py',
                 REPO/'scripts/patch_agx_shader.py', REPO/'scripts/run_vulkan_compute.py', REPO/'tests/vulkan_compute.c']
        for source in paths: shutil.copy2(source,sources/source.name)
        state['source_hashes'] = {str(f): sha(f) for f in paths}
        if sha(baseline.DRIVER) != baseline.DRIVER_HASH:
            raise ValueError('driver hash changed')
        state['driver_sha256'] = sha(baseline.DRIVER)
        dependencies,_ = run(['ldd', baseline.DRIVER], 'dependencies')
        if b'not found' in dependencies: raise ValueError('missing runtime library')
        runtime_files = [baseline.DRIVER, baseline.ICD, Path('/usr/lib64/libvulkan.so.1'), a.runtime/'libdisplay-info.so.2']
        for line in dependencies.decode().splitlines():
            fields=line.split(); filename=fields[2] if '=>' in fields and len(fields)>2 else fields[0] if fields else ''
            if filename.startswith('/') and Path(filename).is_file(): runtime_files.append(Path(filename))
        runtime_hashes = {str(f):sha(f) for f in runtime_files}; state['runtime_hashes']=runtime_hashes
        def verify_runtime():
            if {str(f):sha(f) for f in runtime_files} != runtime_hashes: raise ValueError('runtime changed')
        binary = out/'vulkan_compute'
        run(shlex.split(a.cc)+['-std=c11','-Wall','-Wextra','-Werror','-O2','-I/save/workspace/AGX_Probe/mesa/include',
                              REPO/'tests/vulkan_compute.c','-ldl','-o',binary], 'build',30,env)
        state['executable_sha256']=sha(binary)
        blob = bytes.fromhex(json.loads((REPO/'novel-results/2026-10-04-first-agx-instruction/patch.json').read_text())['input_hex'])
        control = out/'control.bin'; control.write_bytes(blob); state['control_hex']=blob.hex()
        def case(name, code, expected=None, pairs=a.pair_gap is not None):
            verify_runtime(); digest=sha(code); readback=out/(name+'.readback')
            stdout,cmd = run([binary,'import',code,a.count,'/dev/dri/renderD128',readback,out/'unused.bin'],name)
            events=[json.loads(line) for line in stdout.decode().splitlines()]
            if not events or events[-1] != {'completed':True,'dispatch':True,'count':a.count,'words':(a.count+31)//32*32+32}:
                raise ValueError('completion record mismatch')
            for api in ('vkCreateShadersEXT','vkQueueSubmit','vkWaitForFences'):
                matched=[e for e in events if e.get('api')==api]
                if len(matched)!=1 or matched[0].get('result')!=0: raise ValueError('API evidence missing: '+api)
            data=readback.read_bytes(); values=inspect_buffer(data,a.count,expected,pairs)
            verify_runtime()
            if sha(code)!=digest: raise ValueError('input changed')
            return {'name':name,'passed':True,'shader_sha256':digest,'readback_sha256':sha(readback),
                    'readback_hex':data.hex(),'values':values,'events':events,'pairs':pairs,
                    'host_before_ns':cmd['host_before_ns'],'host_after_ns':cmd['host_after_ns']}
        if a.pair_gap is not None:
            state['controls'].append(case('original-before',control,lambda i:0x12345678,pairs=False))
            pair_control,evidence=patcher.patch_pair(blob,80,a.pair_gap,constant=True)
            control=out/'paired-control.bin';control.write_bytes(pair_control)
            state['paired_control_patch']=evidence;state['paired_control_hex']=pair_control.hex()
        state['controls'].append(case('unchanged-before',control,lambda i:0x12345678)); save()
        for ordinal,selector in enumerate(selectors):
            patched,evidence=patcher.patch(blob,selector) if a.pair_gap is None else patcher.patch_pair(blob,selector,a.pair_gap)
            code=out/(f'sr{selector:03d}.bin');code.write_bytes(patched)
            observation={'selector':selector,'patch':evidence,'samples':[],'completed':False}
            state['observations'].append(observation)
            try:
                for repeat in range(a.repeats):
                    sample=case(f'sr{selector:03d}-r{repeat}',code,KNOWN.get(selector))
                    observation['samples'].append(sample);save()
                    if repeat+1<a.repeats: time.sleep(a.spacing_ms/1000)
                observation['completed']=True
            except Exception as e:
                observation['error']=str(e);state['failures'].append({'selector':selector,'error':str(e)})
                save()
                # A faulting unknown selector is recorded, never retried. Continue
                # only if the same guarded unchanged control proves recovery.
                state['controls'].append(case(f'recovery-after-sr{selector:03d}',control,lambda i:0x12345678));save()
                if len(state['failures'])>=a.max_failures: raise RuntimeError('failure budget reached')
            if (ordinal+1)%16==0:
                state['controls'].append(case(f'control-after-{ordinal+1}',control,lambda i:0x12345678));save()
                print(json.dumps({'scanned':ordinal+1,'failures':len(state['failures'])}),flush=True)
            save()
        state['controls'].append(case('unchanged-after',control,lambda i:0x12345678))
        state['complete']=True;state['passed']=not state['failures']
    except Exception as e:
        state['error']=str(e)
    finally:
        save();print(json.dumps({'complete':state['complete'],'passed':state['passed'],'output':str(out),'error':state.get('error')}),flush=True)
    return 0 if state['passed'] else 1


if __name__=='__main__':
    main()
