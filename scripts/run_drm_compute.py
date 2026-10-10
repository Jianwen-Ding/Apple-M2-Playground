#!/usr/bin/env python3
"""Run native AGX main code through the direct DRM harness (tests/drm_compute.c).

No Mesa/Vulkan in the execution path. The main is the pinned control's own
index/bounds prefix + <body> + address/store/pop_exec/stop suffix; the body
must leave the stored value in r2. Bodies reuse run_agx_timestamps' chain
generator (exact oracles). Firmware start/end timestamps of the compute
command, DRM GET_TIME around submit/wait, and host time are recorded.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys

import patch_agx_sr as patcher
import run_agx_timestamps as chains

REPO = Path(__file__).resolve().parents[1]


def control_main():
    blob = bytes.fromhex(json.loads((REPO/'novel-results/2026-10-04-first-agx-instruction/patch.json').read_text())['input_hex'])
    main = blob[patcher.CODE_START+0x80:patcher.CODE_START+0xb6]
    site = patcher.SITE-patcher.CODE_START-0x80
    if main[site:site+6] != bytes.fromhex('620978563412') or main[-2:] != bytes.fromhex('8800'):
        raise ValueError('control main layout mismatch')
    return main, site


def build_main(body):
    main, site = control_main()
    return main[:site]+bytes(body)+main[site+6:]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=sorted(chains.KINDS)+['control'], default='control')
    p.add_argument('--chains', type=int, choices=(1, 2, 4), default=1)
    p.add_argument('--lengths', default='0')
    p.add_argument('--count', type=int, default=33)
    p.add_argument('--repeats', type=int, default=4)
    p.add_argument('--gprs', type=int, default=16)
    p.add_argument('--preload', type=lambda v: int(v, 0), default=0x10000000)
    p.add_argument('--timeout', type=int, default=60)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    lengths = [None] if a.kind == 'control' else [int(x) for x in a.lengths.split(',')]
    if not (1 <= a.repeats <= 64 and 1 <= a.count <= 65536 and all(n is None or 0 <= n <= 100000 for n in lengths)):
        p.error('bounded repeats/count/lengths required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/runs')/stamp
    out.mkdir(parents=True, exist_ok=False)
    state = {'passed': False, 'utc': stamp, 'path': 'direct-drm', 'kind': a.kind, 'chains': a.chains,
             'count': a.count, 'repeats': a.repeats, 'gprs': a.gprs, 'preload': a.preload, 'variants': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state, indent=1)+'\n')
    exe = out/'drm_compute'
    rounded = (a.count+31)//32*32
    try:
        r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                           str(REPO/'tests/drm_compute.c'), '-o', str(exe)], capture_output=True, timeout=60)
        if r.returncode: raise RuntimeError('build failed: '+r.stderr.decode()[-400:])
        gpu, _ = patcher.load_model(chains.APPLEGPU)
        for n in lengths:
            if n is None:
                name, body, want = 'control', bytes.fromhex('620978563412'), 0x12345678
            else:
                name, body, want = f'{a.kind}-c{a.chains}-{n}', chains.body(n, a.kind, a.chains, a.preload, gpu), chains.oracle(n, a.kind, a.preload)
            code = build_main(body)
            path = out/(name+'.bin'); path.write_bytes(code+bytes(16)); rb = out/(name+'.readback')
            rec = {'name': name, 'n': n, 'code_bytes': len(code), 'oracle': want}
            state['variants'].append(rec)
            argv = [str(exe), a.device, str(path), str(a.count), str(rb), str(a.repeats), str(a.gprs)]
            try:
                res = subprocess.run(argv, capture_output=True, timeout=a.timeout)
                rec['returncode'] = res.returncode; stdout = res.stdout.decode(errors='replace')
            except subprocess.TimeoutExpired as e:
                rec['returncode'] = None; rec['timed_out'] = True; stdout = (e.stdout or b'').decode(errors='replace')
            events = [json.loads(l) for l in stdout.splitlines() if l.startswith('{')]
            rec['setup'] = [e for e in events if 'params' in e or 'usc_words_hex' in e or 'cdm_hex' in e]
            rec['samples'] = [e for e in events if 'rep' in e]
            if rec['returncode'] != 0:
                rec['stdout_tail'] = stdout[-800:]; save(); raise RuntimeError('submission failed: '+name)
            w = list(struct.unpack('<'+'I'*(rounded+32), rb.read_bytes()))
            expected = [0xcdcdcdcd]*(rounded+16)+[0xa5a50000+j for j in range(16)]
            expected[8:8+a.count] = [want]*a.count
            rec['buffer_ok'] = w == expected
            rec['mismatches'] = [[i, w[i]] for i in range(len(w)) if w[i] != expected[i]][:16]
            rb.unlink(); save()
            print(json.dumps({'variant': name, 'ok': rec['buffer_ok'],
                              'fw_ns': [s['fw_ts'][1]-s['fw_ts'][0] for s in rec['samples']],
                              'host_ns': [s['host_ns'] for s in rec['samples']]}), flush=True)
            if not rec['buffer_ok']: raise RuntimeError('oracle mismatch: '+name)
        state['passed'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save(); print(json.dumps({'passed': state['passed'], 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
