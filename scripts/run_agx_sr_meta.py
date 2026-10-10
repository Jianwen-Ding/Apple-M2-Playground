#!/usr/bin/env python3
"""Map special registers to driver-programmed shader resources by metadata edits.

Exports the 32x1x1 linear-index constant shader (run_agx_sr_shape.py), patches
its constant site with get_sr, then edits one field of the exported
agx_shader_info (offsets measured on this Mesa 25.3.6 export) and refreshes the
wrapper SHA1. Code bytes are unchanged by every edit.

  sweep:  SR18 vs local_size (0x82f), SR19 vs nr_gprs (0x861),
          SR19 vs nr_preamble_gprs (0x863)
  scan:   all 256 selectors under each single-field edit, diffed against an
          unedited baseline in the same run
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

import run_vulkan_compute as baseline
import run_agx_sr_shape as shape
from patch_agx_imadd import integrity, load_model

REPO = Path(__file__).resolve().parents[1]
FIELDS = {'push_count': (0x82d, '<H'), 'local_size': (0x82f, '<H'), 'scratch_size': (0x835, '<I'),
          'preamble_scratch_size': (0x839, '<I'), 'texture_state_count': (0x85f, '<B'),
          'sampler_state_count': (0x860, '<B'), 'nr_gprs': (0x861, '<H'), 'nr_preamble_gprs': (0x863, '<H')}
EXPECTED = {'push_count': 30, 'local_size': 0, 'scratch_size': 0, 'preamble_scratch_size': 0,
            'texture_state_count': 0, 'sampler_state_count': 0, 'nr_gprs': 6, 'nr_preamble_gprs': 8}
SWEEPS = [(18, 'local_size', [0, 256, 512, 1024, 4096, 16640, 32000, 65280]),
          (19, 'nr_gprs', [1, 2, 4, 6, 8, 9, 12, 16, 20, 24, 32, 48, 64, 100, 128, 255]),
          (19, 'nr_preamble_gprs', [0, 8, 16, 32])]
SCANS = [('push_count', 60), ('texture_state_count', 4), ('sampler_state_count', 2), ('scratch_size', 1024),
         ('preamble_scratch_size', 1024), ('nr_gprs', 64), ('local_size', 4096)]
LOCAL, GROUPS = (32, 1, 1), (3, 1, 1)
COUNT = 96


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--runtime', type=Path, default=Path('/scratch/apple-m2-playground/vulkan-runtime/usr/lib64'))
    p.add_argument('--grammar', type=Path, default=Path('/save/workspace/AGX_Probe/mesa/src/compiler/spirv/spirv.core.grammar.json'))
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    p.add_argument('--no-scan', action='store_true', help='sweeps only')
    a = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/sr-meta-runs')/stamp
    out.mkdir(parents=True, exist_ok=False)
    state = {'passed': False, 'utc': stamp, 'local': LOCAL, 'groups': GROUPS, 'count': COUNT,
             'fields': {k: [hex(o), f] for k, (o, f) in FIELDS.items()}, 'sweeps': [], 'scans': {}, 'runs': 0}
    env = {k: v for k, v in os.environ.items() if not k.startswith(('VK_', 'MESA_', 'ASAHI_', 'AGX_', 'HK_', 'LIBGL_', 'GALLIUM_', 'DRI_', 'LD_'))}
    child = env | {'VK_DRIVER_FILES': str(baseline.ICD), 'VK_ICD_FILENAMES': str(baseline.ICD),
                   'VK_LOADER_LAYERS_DISABLE': '~implicit~', 'LD_LIBRARY_PATH': str(a.runtime.resolve()),
                   'MESA_SHADER_CACHE_DISABLE': 'true'}
    exe = out/'vulkan_compute'
    def child_run(mode, code, readback):
        state['runs'] += 1
        r = subprocess.run([str(exe), mode, str(code), str(COUNT), '/dev/dri/renderD128', str(readback),
                            str(out/'export.bin'), *map(str, GROUPS)], env=child, capture_output=True, timeout=15)
        if r.returncode != 0:
            return None
        w = struct.unpack('<'+'I'*(COUNT+32), readback.read_bytes())
        if any(x != 0xcdcdcdcd for x in w[:8]+w[8+COUNT:COUNT+16]) or list(w[COUNT+16:]) != [0xa5a50000+j for j in range(16)]:
            raise ValueError('guard/tail corruption')
        return list(w[8:8+COUNT])
    def edit(blob, field, value):
        off, fmt = FIELDS[field]
        b = bytearray(blob); struct.pack_into(fmt, b, off, value); b[48:68] = integrity(b)
        return bytes(b)
    def run_blob(blob):
        path = out/'case.bin'; path.write_bytes(blob)
        return child_run('import', path, out/'case.readback')
    try:
        if shape.sha(baseline.DRIVER) != baseline.DRIVER_HASH: raise ValueError('driver hash changed')
        gpu, _ = load_model(shape.APPLEGPU)
        r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-I/save/workspace/AGX_Probe/mesa/include',
                           str(REPO/'tests/vulkan_compute.c'), '-ldl', '-o', str(exe)], env=env, capture_output=True, timeout=30)
        if r.returncode: raise RuntimeError('build failed: '+r.stderr.decode()[-500:])
        spv = shape.spirv(LOCAL, out/'base.spv', a.grammar)
        if child_run('export', spv, out/'export.readback') != [shape.CONSTANT]*COUNT: raise ValueError('export oracle')
        blob = (out/'export.bin').read_bytes()
        state['export_sha256'] = shape.sha(out/'export.bin')
        found = {k: struct.unpack_from(f, blob, o)[0] for k, (o, f) in FIELDS.items()}
        state['export_fields'] = found
        if found != EXPECTED: raise ValueError('metadata layout differs from measured export: '+json.dumps(found))
        if run_blob(blob) != [shape.CONSTANT]*COUNT: raise ValueError('import oracle')
        for sel, field, values in SWEEPS:
            patched = shape.patch(blob, sel, gpu)[0]
            sweep = {'selector': sel, 'field': field, 'original': found[field], 'results': {}}
            sweep['results']['original'] = run_blob(patched)
            for v in values:
                sweep['results'][str(v)] = run_blob(edit(patched, field, v))
            state['sweeps'].append(sweep)
            print(json.dumps({'sweep': field, 'selector': sel}), flush=True)
        if not a.no_scan:
            patched = {sel: shape.patch(blob, sel, gpu)[0] for sel in range(256)}
            state['scans']['baseline'] = {str(s): run_blob(b) for s, b in patched.items()}
            for field, value in SCANS:
                state['scans'][f'{field}={value}'] = {str(s): run_blob(edit(b, field, value)) for s, b in patched.items()}
                print(json.dumps({'scan': field}), flush=True)
        if run_blob(blob) != [shape.CONSTANT]*COUNT: raise ValueError('final import oracle')
        state['passed'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        (out/'record.json').write_text(json.dumps(state)+'\n')
        print(json.dumps({'passed': state['passed'], 'output': str(out), 'error': state.get('error')}))
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
