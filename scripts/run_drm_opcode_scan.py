#!/usr/bin/env python3
"""Classify AGX opcodes the applegpu model cannot decode, on the direct DRM path.

For each candidate the main shader is the pinned control with its `mov_imm r2, P`
replaced by `mov_imm r2, P ; <candidate> ; wait 0 x4`; the unchanged suffix then
stores r2. One candidate per submission. Outcome per candidate:

  * noop      - r2 == P in every active lane, guards intact, completed normally
  * writes-r2 - completed normally, guards intact, but r2 != P (the op wrote r2)
  * ends      - completed normally, guards intact, but the store did not run
                (r2 slot still the sentinel): the op ended the thread/group
  * fault     - no firmware timestamps, or host time >= 50 ms, or non-zero exit,
                or guard words clobbered: a GPU fault/hang recovered by firmware

A fault is never retried. After any fault the unchanged control is submitted and
must pass before the scan continues, and the scan pauses between candidates.
This DELIBERATELY EXECUTES FAULTING INSTRUCTIONS and is gated by
CONFIRM_GPU_FAULTS=1. The owner may see desktop flashes/stutter during a fault.
The 0x6e stale-on-chip-data forms (LeftoverLocals class) are excluded.
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
import time

import patch_agx_sr as patcher
import run_drm_compute as drm
import agx_loop

REPO = Path(__file__).resolve().parents[1]
WAIT = bytes.fromhex('3800')
SENTINEL = 0xcdcdcdcd
PRELOAD = 0x5a5a1234
# Excluded: 0x6e returns stale on-chip register-file data (LeftoverLocals class, CVE-2023-4969).
EXCLUDE = {0x6e}


def undecoded(gpu):
    return [op for op in range(128) if op not in EXCLUDE
            and not any(gpu.get_instruction_descriptor(op | ext << 7) for ext in range(512))]


def candidate_bytes(op):
    # op | Dt=2 (32-bit dest) | D=r2; 2 bytes, then padding waits so trailing bytes are harmless.
    return (op | 2 << 7 | 4 << 9).to_bytes(2, 'little')+WAIT*3


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--opcodes', default='undecoded', help="'undecoded' or comma list of 0..127")
    p.add_argument('--count', type=int, default=32)
    p.add_argument('--gprs', type=int, default=32)
    p.add_argument('--timeout', type=int, default=20)
    p.add_argument('--pause', type=float, default=1.0, help='seconds between candidates after a fault')
    p.add_argument('--max-faults', type=int, default=64)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1':
        sys.exit('refusing to run: this executes GPU-faulting instructions. Re-run with CONFIRM_GPU_FAULTS=1 on an idle machine.')
    if not (1 <= a.count <= 1024 and 8 <= a.gprs <= 256):
        sys.exit('bounded count/gprs required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/opcode-scan')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    gpu, _ = patcher.load_model(agx_loop.APPLEGPU)
    ops = undecoded(gpu) if a.opcodes == 'undecoded' else [int(o, 0) for o in a.opcodes.split(',')]
    rounded = (a.count+31)//32*32
    state = {'utc': stamp, 'path': 'direct-drm', 'kind': 'opcode-scan', 'count': a.count, 'gprs': a.gprs,
             'preload': PRELOAD, 'opcodes': ops, 'excluded': sorted(EXCLUDE), 'results': [], 'faults': 0, 'complete': False}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')

    def run_body(body, name):
        code = drm.build_main(body)
        path = out/(name+'.bin'); path.write_bytes(code+bytes(16)); rb = out/(name+'.readback')
        rec = {'name': name, 'code_bytes': len(code)}
        try:
            res = subprocess.run([str(exe), a.device, str(path), str(a.count), str(rb), '1', str(a.gprs)],
                                 capture_output=True, timeout=a.timeout)
            rec['returncode'] = res.returncode
            events = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
            samples = [e for e in events if 'rep' in e]
            rec['fw_ns'] = [e['fw_ts'][1]-e['fw_ts'][0] for e in samples]
            rec['host_ns'] = [e['host_ns'] for e in samples]
            rec['completed_normally'] = bool(samples) and all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in samples)
            if res.returncode == 0:
                w = list(struct.unpack(f'<{rounded+32}I', rb.read_bytes()))
                guards = [SENTINEL]*8+[SENTINEL]*(rounded-a.count)+[SENTINEL]*8+[0xa5a50000+j for j in range(16)]
                gi = list(range(8))+list(range(8+a.count, rounded+16))+list(range(rounded+16, rounded+32))
                rec['guards_ok'] = all(w[i] == ([SENTINEL]*(rounded+16)+[0xa5a50000+j for j in range(16)])[i] for i in gi)
                rec['payload'] = w[8:8+a.count]
            else:
                rec['stdout_tail'] = res.stdout.decode(errors='replace')[-300:]
                rec['guards_ok'] = False
        except subprocess.TimeoutExpired as e:
            rec['returncode'] = None; rec['timed_out'] = True; rec['completed_normally'] = False; rec['guards_ok'] = False
            rec['stdout_tail'] = (e.stdout or b'').decode(errors='replace')[-300:]
        for f in (path, rb):
            try: f.unlink()
            except FileNotFoundError: pass
        return rec

    def classify(rec):
        if not rec.get('completed_normally') or not rec.get('guards_ok'):
            return 'fault'
        payload = rec.get('payload', [])
        if all(v == PRELOAD for v in payload):
            return 'noop'
        if all(v == SENTINEL for v in payload):
            return 'ends'
        if all(v == 0x12345678 for v in payload):  # suffix wrote the control value: op left r2 untouched but store ran
            return 'noop'
        return 'writes-r2'

    try:
        # mov_imm r2, PRELOAD so a no-op is distinguishable from the control value.
        preload_mov = bytes.fromhex('6209')+PRELOAD.to_bytes(4, 'little')
        ctrl = run_body(preload_mov+WAIT*4, 'control-before')
        ctrl['class'] = classify(ctrl); state['control_before'] = ctrl
        if ctrl['class'] != 'noop':
            raise RuntimeError(f"preload control did not read back PRELOAD: {ctrl['class']}")
        for op in ops:
            body = preload_mov+candidate_bytes(op)+WAIT*4
            rec = run_body(body, f'op-{op:02x}')
            rec['opcode'] = op; rec['class'] = classify(rec)
            state['results'].append(rec); save()
            print(json.dumps({'opcode': hex(op), 'class': rec['class'], 'payload0': rec.get('payload', [None])[0],
                              'fw_ns': rec.get('fw_ns'), 'host_ms': [round(x/1e6, 1) for x in rec.get('host_ns', [])]}), flush=True)
            if rec['class'] == 'fault':
                state['faults'] += 1
                time.sleep(a.pause)
                chk = run_body(preload_mov+WAIT*4, f'recovery-{op:02x}'); chk['class'] = classify(chk)
                state['results'].append({'name': chk['name'], 'recovery_after': hex(op), 'class': chk['class'],
                                         'completed_normally': chk.get('completed_normally'), 'guards_ok': chk.get('guards_ok')})
                save()
                if chk['class'] != 'noop':
                    raise RuntimeError(f'GPU did not recover after opcode {op:#x}: control now {chk["class"]}')
                if state['faults'] >= a.max_faults:
                    raise RuntimeError('fault budget reached')
        state['complete'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save()
        cls = {}
        for rec in state['results']:
            if 'opcode' in rec:
                cls.setdefault(rec['class'], []).append(hex(rec['opcode']))
        print(json.dumps({'complete': state['complete'], 'faults': state['faults'], 'classes': cls,
                          'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
