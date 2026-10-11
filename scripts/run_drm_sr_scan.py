#!/usr/bin/env python3
"""Differential special-register scan on the direct DRM path.

One dispatch reads all 256 `get_sr` selectors per lane (32-bit form, the
encoding validated in earlier scans) and stores selector s for lane i to
table[s*S + i] (S = rounded lane count) over a 0xcdcdcdcd sentinel table.
The control's r2 store still writes 0x12345678, so the whole-buffer oracle
proves the dispatch ran. Lanes >= count must leave their table slots intact.

Each configuration changes one launch parameter through drm_compute's AGX_*
environment overrides. The report lists, per selector, the per-lane values in
each configuration and which selectors differ from the baseline.
Straight-line code only (no loops); get_sr reads were already scanned on
hardware without faults.
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
import agx_loop
import run_drm_compute as drm

REPO = Path(__file__).resolve().parents[1]
SENTINEL = 0xcdcdcdcd

CONFIGS = {
    # name: (environment overrides, lanes)
    'base': ({}, 64),
    'base-repeat': ({}, 64),
    'lanes-96': ({}, 96),
    'local-64': ({'AGX_LOCAL_X': '64'}, 128),
    'helper-data': ({'AGX_HELPER_DATA': '0x1122334455667788'}, 64),
    'helper-cfg': ({'AGX_HELPER_CFG': '0x10000'}, 64),
    'priority-low': ({'AGX_PRIORITY': '0'}, 64),
    'usc-moved': ({'AGX_USC_WORDS_OFF': '0x3000', 'AGX_CODE_OFF': '0x5000'}, 64),
    'cdm-moved': ({'AGX_CDM_OFF': '0x2400'}, 64),
    'words-only': ({'AGX_USC_WORDS_OFF': '0x4000'}, 64),
    'code-only': ({'AGX_CODE_OFF': '0x5000'}, 64),
    'words-0x8040': ({'AGX_USC_WORDS_OFF': '0x8040'}, 64),
    'words-0x40': ({'AGX_USC_WORDS_OFF': '0x40'}, 64),
    'local-96': ({'AGX_LOCAL_X': '96'}, 192),
    'local-128': ({'AGX_LOCAL_X': '128'}, 256),
    'local-256': ({'AGX_LOCAL_X': '256'}, 512),
    'local-1024': ({'AGX_LOCAL_X': '1024'}, 2048),
    'cdm-moved-2': ({'AGX_CDM_OFF': '0x2400'}, 64),
    'cdm-moved-3': ({'AGX_CDM_OFF': '0x2400'}, 64),
    'order-ushnr': ({'AGX_USC_ORDER': 'ushnr'}, 64),     # Registers last
    'order-usnrh': ({'AGX_USC_ORDER': 'usnrh'}, 64),     # Shader last
    'order-nrhsu': ({'AGX_USC_ORDER': 'nrhsu'}, 64),     # fully reversed
    'preshader-stop': ({'AGX_PRESHADER': '1'}, 64),
    'preshader-first': ({'AGX_PRESHADER': '1', 'AGX_USC_ORDER': 'nushr'}, 64),
    'shape-16x4': ({'AGX_LOCAL_X': '16', 'AGX_LOCAL_Y': '4', 'AGX_GLOBAL_Y': '8'}, 64),
    'shape-8x8': ({'AGX_LOCAL_X': '8', 'AGX_LOCAL_Y': '8', 'AGX_GLOBAL_Y': '16'}, 32),
    'shape-32x2x2': ({'AGX_LOCAL_X': '32', 'AGX_LOCAL_Y': '2', 'AGX_LOCAL_Z': '2', 'AGX_GLOBAL_Y': '4', 'AGX_GLOBAL_Z': '4'}, 64),
    'shape-4x8x4': ({'AGX_LOCAL_X': '4', 'AGX_LOCAL_Y': '8', 'AGX_LOCAL_Z': '4', 'AGX_GLOBAL_Y': '16', 'AGX_GLOBAL_Z': '8'}, 32),
    'order-shru': ({'AGX_USC_ORDER': 'shrun'}, 64),
    'order-rhsu': ({'AGX_USC_ORDER': 'rhsun'}, 64),
    'occupancy-2048wg': ({}, 65536),                            # 2048 one-SIMD workgroups, ~54 per core
    'occupancy-512x128': ({'AGX_LOCAL_X': '128'}, 65536),       # 512 four-SIMD workgroups
    'slots-g32-wg32': ({'GPRS': '32'}, 65536),
    'slots-g32-wg128': ({'GPRS': '32', 'AGX_LOCAL_X': '128'}, 65536),
    'slots-g48-wg32': ({'GPRS': '48'}, 65536),
    'slots-g48-wg128': ({'GPRS': '48', 'AGX_LOCAL_X': '128'}, 65536),
    'slots-g64-wg32': ({'GPRS': '64'}, 65536),
    'slots-g64-wg128': ({'GPRS': '64', 'AGX_LOCAL_X': '128'}, 65536),
    'slots-g96-wg32': ({'GPRS': '96'}, 65536),
    'slots-g96-wg128': ({'GPRS': '96', 'AGX_LOCAL_X': '128'}, 65536),
    'slots-g128-wg32': ({'GPRS': '128'}, 65536),
    'slots-g128-wg128': ({'GPRS': '128', 'AGX_LOCAL_X': '128'}, 65536),
    'slots-g192-wg32': ({'GPRS': '192'}, 65536),
    'slots-g192-wg128': ({'GPRS': '192', 'AGX_LOCAL_X': '128'}, 65536),
    'slots-g256-wg32': ({'GPRS': '256'}, 65536),
    'slots-g256-wg128': ({'GPRS': '256', 'AGX_LOCAL_X': '128'}, 65536),
    'resident-g32-wg32': ({'GPRS': '32', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g32-wg128': ({'GPRS': '32', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g32-wg1024': ({'GPRS': '32', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g64-wg32': ({'GPRS': '64', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g64-wg128': ({'GPRS': '64', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g64-wg1024': ({'GPRS': '64', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g96-wg32': ({'GPRS': '96', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g96-wg128': ({'GPRS': '96', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g96-wg1024': ({'GPRS': '96', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g128-wg32': ({'GPRS': '128', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g128-wg128': ({'GPRS': '128', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g128-wg1024': ({'GPRS': '128', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g160-wg32': ({'GPRS': '160', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g160-wg128': ({'GPRS': '160', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g160-wg1024': ({'GPRS': '160', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g192-wg32': ({'GPRS': '192', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g192-wg128': ({'GPRS': '192', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g192-wg1024': ({'GPRS': '192', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g224-wg32': ({'GPRS': '224', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g224-wg128': ({'GPRS': '224', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g224-wg1024': ({'GPRS': '224', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'resident-g256-wg32': ({'GPRS': '256', 'AGX_LOCAL_X': '32', 'DELAY': '4000'}, 65536),
    'resident-g256-wg128': ({'GPRS': '256', 'AGX_LOCAL_X': '128', 'DELAY': '4000'}, 65536),
    'resident-g256-wg1024': ({'GPRS': '256', 'AGX_LOCAL_X': '1024', 'DELAY': '4000'}, 65536),
    'pre-control': ({'PRE_CHUNK': '0', 'PRE_CONST': '0x5a000000'}, 64),
    'pre-chunk0': ({'PRE_CHUNK': '0'}, 64),
    'pre-chunk1': ({'PRE_CHUNK': '1'}, 64),
    'pre-chunk0-local128': ({'PRE_CHUNK': '0', 'AGX_LOCAL_X': '128'}, 512),
    'pre-chunk0-2048wg': ({'PRE_CHUNK': '0'}, 65536),
    'atomic-64': ({'ATOMIC_TEST': '1'}, 64),
    'atomic-33': ({'ATOMIC_TEST': '1'}, 33),
    'atomic-65536': ({'ATOMIC_TEST': '1'}, 65536),
    'pre-atomic-2wg': ({'PRE_CHUNK': '0', 'PRE_COUNT': 'atomic'}, 64),
    'pre-atomic-512x128': ({'PRE_CHUNK': '0', 'PRE_COUNT': 'atomic', 'AGX_LOCAL_X': '128'}, 65536),
    'pre-atomic-2048wg': ({'PRE_CHUNK': '0', 'PRE_COUNT': 'atomic'}, 65536),
    'pre-count-2wg': ({'PRE_CHUNK': '0', 'PRE_COUNT': '1'}, 64),
    'pre-count-512x128': ({'PRE_CHUNK': '0', 'PRE_COUNT': '1', 'AGX_LOCAL_X': '128'}, 65536),
    'pre-count-2048wg': ({'PRE_CHUNK': '0', 'PRE_COUNT': '1'}, 65536),
    'shader-unk2-2': ({'AGX_SHADER_UNK2': '2'}, 64),
    'shared-32x32-s8': ({'AGX_SHARED_WORD': '0x2010bd4d'}, 64),
    'shared-32x16-s8': ({'AGX_SHARED_WORD': '0x2010fd4d'}, 64),
    'shared-16x16-s8': ({'AGX_SHARED_WORD': '0x2010d94d'}, 64),
    'shared-32x32-s32': ({'AGX_SHARED_WORD': '0x8040bd4d'}, 64),
    'shared-32x32-st2': ({'AGX_SHARED_WORD': '0x4020bd4d'}, 64),
    'shared-32x32-st3': ({'AGX_SHARED_WORD': '0x6030bd4d'}, 64),
    'shared-32x32-st7': ({'AGX_SHARED_WORD': '0xe070bd4d'}, 64),
    'shared-32x32-st15': ({'AGX_SHARED_WORD': '0xe0f0bd4d'}, 64),
    'shared-32x32-st0': ({'AGX_SHARED_WORD': '0x8000bd4d'}, 64),
    'shared-32x32-samples2': ({'AGX_SHARED_WORD': '0x4011bd4d'}, 64),
    'shared-32x32-samples4': ({'AGX_SHARED_WORD': '0x8012bd4d'}, 64),
    'shared-16x16-samples4': ({'AGX_SHARED_WORD': '0x22d94d'}, 64),
    'samplers-4': ({'AGX_SAMPLER_COUNT': '4'}, 64),
    'word0-uniform-2': ({'AGX_WORD0_OR': str(2 << 1)}, 64),      # uniform register count field 1 -> 3 groups
    'word0-texture-8': ({'AGX_WORD0_OR': str(1 << 4)}, 64),      # texture state register count 1 group
    'word0-preshader-16': ({'AGX_WORD0_OR': str(1 << 12)}, 64),  # preshader register count 1 group
}


def get_sr(selector, reg):
    raw = 0x72 | (2 << 7) | ((2*reg) << 9) | ((selector & 63) << 16) | ((selector >> 6) << 26)
    return raw.to_bytes(4, 'little')


def delay_loop(trips):
    """Emulator-checked counted loop (r2..r4 clobbered) that keeps the SIMD group resident."""
    body, _ = agx_loop.loop_body(trips, 4, 'fadd4')
    ok, sbody, _, _ = agx_loop.check(min(trips, 16), 4, 'fadd4', active=32)
    if not ok or len(sbody) != len(body) or any(not 8 <= i < 12 for i, (x, y) in enumerate(zip(body, sbody)) if x != y):
        raise RuntimeError('delay loop failed the emulator gate')
    return body


def scan_body(selectors, stride_words, gx=None, gy=1, delay=0):
    """stride_words = total threads; for 2-D/3-D grids the slot is the linear global id
    r1 + SR81*gx + SR82*gx*gy (r1 = SR80 from the control prefix)."""
    gpu, _ = patcher.load_model(agx_loop.APPLEGPU)
    out = agx_loop.chains.mov_imm(14, stride_words)+agx_loop.encode('iadd r5, r1, 0')
    if gx is not None and stride_words != gx:
        out += get_sr(81, 6)+agx_loop.chains.mov_imm(7, gx)+agx_loop.encode('imadd r5, r6, r7, r5')
        out += get_sr(82, 6)+agx_loop.chains.mov_imm(7, gx*gy)+agx_loop.encode('imadd r5, r6, r7, r5')
    step = agx_loop.encode('iadd r5, r5, r14')
    for k, s in enumerate(selectors):
        reg = 6+k % 8
        b = get_sr(s, reg)
        n = int.from_bytes(b, 'little'); d = gpu.get_instruction_descriptor(n)
        if type(d).__name__ != 'MovFromSrInstructionDesc' or dict(d.decode_fields(n)) != {'Dt': 2, 'D': 2*reg, 'SR': s}:
            raise ValueError(f'get_sr encoding mismatch for SR{s}')
        out += b+agx_loop.store(reg, 8, 5)+step
        if k % 8 == 7: out += agx_loop.encode('wait 0')
    out += agx_loop.encode('wait 0')
    if delay: out += delay_loop(delay)
    out += bytes.fromhex('620978563412')  # r2 = control value for the suffix store
    return out


MAIN_EXTRA = {250: 20, 251: 17, 252: 0, 253: 24}   # table slot: main-shader selector, for pairing with preshader copies


COUNTER_SLOT = 255   # table[255*S + SR20] counts preamble executions per core (non-atomic load/add/store)


def preshader_scan(selectors, stride_words, constant=None, count_runs=False):
    """Preamble: get_sr each selector into r1..r4 and uniform_store it at halfs 32+2k
    (constant: write `constant` instead, as a delivery control). Main: copy u(16+k)
    to table[s*S + lane]. Returns (preamble bytes, main body bytes)."""
    pre = b''
    if count_runs:
        pre += get_sr(20, 1)+agx_loop.chains.mov_imm(3, COUNTER_SLOT*stride_words)+agx_loop.encode('iadd r1, r1, r3')
        if count_runs == 'atomic':
            pre += agx_loop.chains.mov_imm(2, 1)+agx_loop.atomic_add(8, 1, 2)+agx_loop.encode('wait 0')
        else:
            pre += agx_loop.encode('device_load 0, i32, x, r2, u8_u9, r1, unsigned')+agx_loop.encode('wait 0')
            pre += agx_loop.encode('iadd r2, 1, r2.sx')+agx_loop.store(2, 8, 1)+agx_loop.encode('wait 0')
    for k, s in enumerate(selectors):
        reg = 1+k % 4
        pre += (agx_loop.chains.mov_imm(reg, constant+k) if constant is not None else get_sr(s, reg))
        pre += agx_loop.uniform_store(reg, 32+2*k)
    pre += bytes.fromhex('8800')  # stop
    body = agx_loop.chains.mov_imm(14, stride_words)
    for k, s in enumerate(selectors):
        reg = 6+k % 8
        body += agx_loop.chains.mov_imm(5, 0)+agx_loop.encode('iadd r5, r1, 0')
        body += agx_loop.chains.mov_imm(15, s*stride_words)+agx_loop.encode('iadd r5, r5, r15')
        body += agx_loop.encode(f'iadd r{reg}, u{16+k}, 0')+agx_loop.store(reg, 8, 5)
        if k % 8 == 7: body += agx_loop.encode('wait 0')
    for k, (slot, sel) in enumerate(MAIN_EXTRA.items()):
        if slot in selectors: continue
        reg = 6+k
        body += agx_loop.encode('iadd r5, r1, 0')+agx_loop.chains.mov_imm(15, slot*stride_words)+agx_loop.encode('iadd r5, r5, r15')
        body += get_sr(sel, reg)+agx_loop.store(reg, 8, 5)
    body += agx_loop.encode('wait 0')+bytes.fromhex('620978563412')
    return pre, body


ATOMIC_SLOT = 254


def atomic_test_body(stride_words):
    """Every active lane atomically adds 1 to table[254*S]; the result must equal the lane count."""
    body = agx_loop.chains.mov_imm(5, ATOMIC_SLOT*stride_words)+agx_loop.chains.mov_imm(6, 1)
    body += agx_loop.atomic_add(8, 5, 6)+agx_loop.encode('wait 0')+bytes.fromhex('620978563412')
    return body


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--configs', default=','.join(CONFIGS))
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/sr-scan')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode: sys.exit('build failed: '+r.stderr.decode()[-400:])
    state = {'utc': stamp, 'path': 'direct-drm', 'kind': 'sr-scan', 'configs': {}, 'passed': False}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')
    try:
        for name in a.configs.split(','):
            envs, lanes = CONFIGS[name]
            gy, gz = int(envs.get('AGX_GLOBAL_Y', 1)), int(envs.get('AGX_GLOBAL_Z', 1))
            rounded = (lanes+31)//32*32*gy*gz        # total threads (lanes = global X)
            if gy*gz > 1 and lanes % 32: raise ValueError('multi-dimensional configs need lanes multiple of 32')
            written = list(range(256))
            extra_env = {}
            if 'ATOMIC_TEST' in envs:
                written = []
                body = atomic_test_body(rounded)
            elif 'PRE_CHUNK' in envs:
                c = int(envs['PRE_CHUNK']); scanned = list(range(128*c, 128*c+128))
                const = int(envs['PRE_CONST'], 0) if 'PRE_CONST' in envs else None
                pre, body = preshader_scan(scanned, rounded, const, envs.get('PRE_COUNT', False))
                written = scanned+[slot for slot in MAIN_EXTRA if slot not in scanned]
                (out/'preamble.bin').write_bytes(pre)
                extra_env = {'AGX_PRESHADER': '1', 'AGX_PRESHADER_CODE': str(out/'preamble.bin'),
                             'AGX_WORD0_OR': str((5 << 1) | (1 << 12))}   # 5 x 64 uniform halfs, 16 preshader halfs
            else:
                body = scan_body(range(256), rounded, lanes, gy, int(envs.get('DELAY', 0)))
            code = drm.build_main(body)
            (out/'scan.bin').write_bytes(code+bytes(16))
            table = out/'table.bin'; table.write_bytes(struct.pack('<I', SENTINEL)*(256*rounded))
            dump = out/f'{name}.table'; rb = out/'readback'
            gprs = envs.get('GPRS', '32')
            env = dict(os.environ, **{k: v for k, v in envs.items() if k not in ('GPRS', 'DELAY', 'PRE_CHUNK', 'PRE_CONST', 'PRE_COUNT', 'ATOMIC_TEST')},
                       **extra_env, AGX_TABLE_OUT=str(dump))
            res = subprocess.run([str(exe), a.device, str(out/'scan.bin'), str(lanes), str(rb), str(a.repeats), gprs, str(table)],
                                 env=env, capture_output=True, timeout=60)
            events = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
            rec = {'env': envs, 'lanes': lanes, 'returncode': res.returncode, 'code_bytes': len(code),
                   'setup': [e for e in events if 'params' in e or 'usc_words_hex' in e or 'cdm_hex' in e],
                   'samples': [e for e in events if 'rep' in e]}
            state['configs'][name] = rec
            if res.returncode: rec['stdout_tail'] = res.stdout.decode(errors='replace')[-600:]; save(); raise RuntimeError('submit failed: '+name)
            rec['completed_normally'] = bool(rec['samples']) and all(x['fw_ts'][0] and x['fw_ts'][1] and x['host_ns'] < 50_000_000 for x in rec['samples'])
            if not rec['completed_normally']:
                save(); raise RuntimeError('hang signature (no firmware timestamps or host time >= 50 ms): '+name)
            xr = (lanes+31)//32*32   # output buffer is sized by global X only
            w = list(struct.unpack(f'<{xr+32}I', rb.read_bytes()))
            expected = [SENTINEL]*(xr+16)+[0xa5a50000+j for j in range(16)]; expected[8:8+lanes] = [0x12345678]*lanes
            t = struct.unpack(f'<{256*rounded}I', dump.read_bytes())
            rec['buffer_ok'] = w == expected
            untouched = [SENTINEL]*(xr+16)+[0xa5a50000+j for j in range(16)]
            active = rounded if gy*gz > 1 else lanes
            rec['inactive_untouched'] = all(t[s*rounded+i] == SENTINEL for s in range(256) for i in range(active, rounded))
            rec['values'] = {s: list(t[s*rounded:s*rounded+active]) for s in range(256)}
            rec['unwritten'] = [s for s in range(256) if any(v == SENTINEL for v in rec['values'][s])]
            rec['written_selectors'] = written
            if 'ATOMIC_TEST' in envs:
                rec['atomic_counter'] = t[ATOMIC_SLOT*rounded]-SENTINEL
                rec['atomic_neighbours_untouched'] = all(t[ATOMIC_SLOT*rounded+i] == SENTINEL for i in range(1, rounded))
            if 'PRE_COUNT' in envs:
                rec['preamble_runs_by_core'] = {i: t[COUNTER_SLOT*rounded+i]-SENTINEL for i in range(rounded) if t[COUNTER_SLOT*rounded+i] != SENTINEL}
            rec['unwritten'] = [s for s in rec['unwritten'] if s in written]   # only the scanned selectors must be written
            # A configuration may legitimately execute nothing (e.g. pipeline words ignored). Accept that
            # only when output and table are completely untouched; any partial write is a failure.
            rec['executed_nothing'] = w == untouched and len(rec['unwritten']) == len(written)
            dump.unlink(); table.unlink(); rb.unlink(); save()
            print(json.dumps({'config': name, 'ok': rec['buffer_ok'] and rec['inactive_untouched'], 'executed_nothing': rec['executed_nothing'],
                              'nonzero': [s for s in range(256) if any(v not in (0, SENTINEL) for v in rec['values'][s])],
                              'fw_ns': [x['fw_ts'][1]-x['fw_ts'][0] for x in rec['samples']]}), flush=True)
            if rec['executed_nothing']: continue
            if not (rec['buffer_ok'] and rec['inactive_untouched']): raise RuntimeError('oracle failed: '+name)
        base = state['configs'].get('base')
        if base:
            state['diff'] = {}
            for name, rec in state['configs'].items():
                if rec.get('executed_nothing'): state['diff'][name] = 'executed nothing'; continue
                n = min(rec['lanes'], base['lanes'])
                state['diff'][name] = [s for s in range(256) if rec['values'][s][:n] != base['values'][s][:n]]
            print(json.dumps({'diff_vs_base': state['diff']}), flush=True)
        state['passed'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save(); print(json.dumps({'passed': state['passed'], 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
