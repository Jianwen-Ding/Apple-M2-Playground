#!/usr/bin/env python3
"""Bounded execution scan of AGX opcode values the applegpu model cannot decode.

Each candidate replaces only the control's `mov_imm r2` with

    mov_imm r2, PRELOAD ; <candidate bytes> ; wait 0 x4

where a default candidate is `op | Dt=2 | D=r2` (2 bytes) followed by three
`wait 0` words. Whatever length the hardware assigns, the trailing bytes are
waits. r2 is then stored by the unchanged suffix. Register allocation is raised
(nr_gprs) so writes to nearby registers stay inside the allocation.

Recorded per sample: child exit/timeout, wall time, per-lane values (guards
and tail checked) or failure output. A failure is never retried; the scan
continues only after the unchanged control passes again, within a budget.
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
import run_vulkan_compute as baseline

REPO = Path(__file__).resolve().parents[1]
WAIT = bytes.fromhex('3800')


def undecoded_opcodes(gpu):
    """Low-7-bit opcodes for which no descriptor matches any bits 7..15 value."""
    return [op for op in range(128)
            if not any(gpu.get_instruction_descriptor(op | ext << 7) for ext in range(512))]


CLASS_C = (0x06, 0x24, 0x34, 0x44, 0x46, 0x54, 0x5c, 0x64, 0x74)
CLASS_A = (0x01, 0x70)
SEEN_6E = ('6e09be3a2b7c20c3 6e0979e227c59a05 6e094d2906ce1f40 6e09aa0a8aa2e1cb '
           '6e09049235cef180 6e09eec1f5160a80 6e09c167a9a99444 6e0981cabeb2ab85').split()


def candidate_set(name):
    """Named, deterministic candidate lists (label, bytes)."""
    import random
    import struct as st
    sys.path.insert(0, '/save/workspace/AGX_Probe/applegpu')
    import assemble
    op2 = lambda op: (op | 2 << 7 | 4 << 9).to_bytes(2, 'little')
    if name == 'wg0-skip':
        # Lane 0 only executes the instruction; SIMD groups with no active lane jump over it.
        cond = bytes(assemble.assemble_line('if_icmp r0l, ueq, r1, 0, 1')); pop = bytes.fromhex('520e00000000')
        out = []
        for label, ins in [('stop', bytes.fromhex('8800')+WAIT*3)]+[(hex(op), op2(op)+WAIT*3) for op in CLASS_C+CLASS_A+(0x18,)]:
            out.append((label, cond+bytes.fromhex('20c0')+st.pack('<i', 6+len(ins))+ins+pop))
        return out
    if name == '6e-fuzz':
        rng = random.Random(6)
        return [(f'6e-{k}', op2(0x6e)+rng.getrandbits(48).to_bytes(6, 'little')+WAIT*3) for k in range(64)]
    if name == '6e-init':
        init = b''.join((0x62 | 2 << 7 | (2*n) << 9).to_bytes(2, 'little')+(0xa0000000 | n << 16 | n).to_bytes(4, 'little') for n in range(3, 16))
        return [(v, init+bytes.fromhex(v)+WAIT*3) for v in SEEN_6E]
    raise ValueError('unknown set '+name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--opcodes', default='undecoded', help="'undecoded' or comma list of 0..127")
    p.add_argument('--set', choices=('wg0-skip', '6e-fuzz', '6e-init'), help='named deterministic candidate set')
    p.add_argument('--raw', help='comma list of explicit candidate hex byte strings (overrides --opcodes)')
    p.add_argument('--preload', type=lambda v: int(v, 0), default=0x5a5a1234)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--count', type=int, default=65)
    p.add_argument('--gprs', type=int, default=32)
    p.add_argument('--max-failures', type=int, default=16)
    p.add_argument('--timeout', type=int, default=15)
    p.add_argument('--bracket', action='store_true', help='store P before and ~P after the candidate (count forced to 16): distinguishes termination from skipped code')
    p.add_argument('--after-stop', action='store_true', help='place each candidate after stop (never executed)')
    p.add_argument('--follow', action='store_true', help='after each candidate, submit the unchanged control on the same VkDevice and check it')
    p.add_argument('--output', type=Path)
    p.add_argument('--runtime', type=Path, default=Path('/scratch/apple-m2-playground/vulkan-runtime/usr/lib64'))
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if not (1 <= a.repeats <= 5 and 1 <= a.count <= 257 and 8 <= a.gprs <= 256 and 1 <= a.max_failures <= 128):
        p.error('bounded repeats/count/gprs/failures required')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/opcode-scan-runs')/stamp
    out.mkdir(parents=True, exist_ok=False)
    state = {'passed': False, 'complete': False, 'utc': stamp, 'preload': a.preload, 'count': a.count,
             'repeats': a.repeats, 'gprs': a.gprs, 'controls': [], 'candidates': [], 'failures': []}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('VK_', 'MESA_', 'ASAHI_', 'AGX_', 'HK_', 'LIBGL_', 'GALLIUM_', 'DRI_', 'LD_'))}
    child = env | {'VK_DRIVER_FILES': str(baseline.ICD), 'VK_ICD_FILENAMES': str(baseline.ICD),
                   'VK_LOADER_LAYERS_DISABLE': '~implicit~', 'LD_LIBRARY_PATH': str(a.runtime.resolve()),
                   'MESA_SHADER_CACHE_DISABLE': 'true'}
    exe = out/'vulkan_compute'
    if a.bracket: a.count = 16
    rounded = (a.count+31)//32*32
    active = 2*a.count if a.bracket else a.count
    def execute(blob, name, expected=None):
        path = out/(name+'.bin'); path.write_bytes(blob); rb = out/(name+'.readback')
        rec = {'name': name, 'host_before_ns': time.monotonic_ns()}
        try:
            follow = a.follow and expected is None
            argv = [str(exe), 'follow' if follow else 'import', str(path), str(a.count), '/dev/dri/renderD128', str(rb),
                    str(out/'control.bin') if follow else str(out/'unused.bin')]
            r = subprocess.run(argv,
                               env=child, capture_output=True, timeout=a.timeout)
            rec['returncode'] = r.returncode; stdout = r.stdout.decode(errors='replace')
        except subprocess.TimeoutExpired as e:
            rec['returncode'] = None; rec['timed_out'] = True; stdout = (e.stdout or b'').decode(errors='replace')
        rec['host_after_ns'] = time.monotonic_ns()
        if rec['returncode'] != 0:
            rec['stdout_tail'] = stdout[-600:]; return rec
        w = list(struct.unpack('<'+'I'*(rounded+32), rb.read_bytes()))
        initial = [0xcdcdcdcd]*(rounded+16)+[0xa5a50000+j for j in range(16)]
        rec['guards_ok'] = all(w[i] == initial[i] for i in list(range(8))+list(range(8+active, rounded+32)))
        rec['values'] = w[8:8+active]
        if a.follow and expected is None:
            events = [json.loads(l) for l in stdout.splitlines() if l.startswith('{')]
            rec['follow_events'] = [e for e in events if str(e.get('api', '')).startswith('follow:')]
            second = Path(str(rb)+'.2'); w2 = list(struct.unpack('<'+'I'*(rounded+32), second.read_bytes())); second.unlink()
            rec['follow_control_ok'] = (all(e['result'] == 0 for e in rec['follow_events']) and len(rec['follow_events']) == 3 and
                                        w2[8:8+a.count] == [0x12345678]*a.count and w2[8+a.count:] == initial[8+a.count:])
        want = None if expected is None else ([expected[0]]*a.count+[expected[1]]*a.count if isinstance(expected, tuple) else [expected]*active)
        rec['passed'] = rec['guards_ok'] and (want is None or rec['values'] == want)
        rb.unlink(); path.unlink()
        return rec
    try:
        if baseline.sha(baseline.DRIVER) != baseline.DRIVER_HASH: raise ValueError('driver hash changed')
        r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-I/save/workspace/AGX_Probe/mesa/include',
                           str(REPO/'tests/vulkan_compute.c'), '-ldl', '-o', str(exe)], env=env, capture_output=True, timeout=30)
        if r.returncode: raise RuntimeError('build failed')
        blob = bytes.fromhex(json.loads((REPO/'novel-results/2026-10-04-first-agx-instruction/patch.json').read_text())['input_hex'])
        mov = bytes.fromhex('6209')+a.preload.to_bytes(4, 'little')
        after = b''
        if a.bracket:
            # r1 = i on entry. First store at slot 8+i, then r1 += 8 twice more so the
            # unchanged suffix (r1 += 8; store) writes ~P at slot 8+16+i.
            code = blob[patcher.CODE_START:]
            add8, store, wait0 = code[0x9c:0xa4], code[0xa4:0xac], code[0xac:0xae]
            mov = mov+add8+store+wait0
            after = bytes.fromhex('6209')+(a.preload ^ 0xffffffff).to_bytes(4, 'little')+add8
        control = blob
        (out/'control.bin').write_bytes(blob)
        state['follow'] = a.follow
        preload_control, _ = patcher.patch_body(blob, mov+WAIT*4+after, gprs=a.gprs)
        state['bracket'] = a.bracket; state['after_stop'] = a.after_stop
        def controls(tag):
            want = (a.preload, a.preload ^ 0xffffffff) if a.bracket else a.preload
            for name, b, want in (('unchanged', control, (0x12345678, 0xcdcdcdcd) if a.bracket else 0x12345678), ('preload', preload_control, want)):
                rec = execute(b, f'{tag}-{name}', want); state['controls'].append(rec)
                if not rec.get('passed'): raise RuntimeError('control failed: '+rec['name'])
        controls('before')
        gpu, _ = patcher.load_model(Path('/save/workspace/AGX_Probe/applegpu'))
        if a.set:
            cands = candidate_set(a.set); state['set'] = a.set
        elif a.raw:
            cands = [('raw', bytes.fromhex(h)) for h in a.raw.split(',')]
        else:
            ops = undecoded_opcodes(gpu) if a.opcodes == 'undecoded' else [int(o, 0) for o in a.opcodes.split(',')]
            state['opcodes'] = ops
            cands = [(hex(op), (op | 2 << 7 | 4 << 9).to_bytes(2, 'little')+WAIT*3) for op in ops]
        for k, (label, cand) in enumerate(cands):
            body = mov+cand+WAIT*4+after
            if a.after_stop:
                body = mov+WAIT*4+after
                patched, ev = patcher.patch_body(blob, body, gprs=a.gprs, strict=False, trailer=cand+WAIT*4)
            else:
                patched, ev = patcher.patch_body(blob, body, gprs=a.gprs, strict=False)
            entry = {'label': label, 'candidate_hex': cand.hex(), 'body_hex': body.hex(),
                     'patched_sha256': ev['patched_sha256'], 'samples': []}
            state['candidates'].append(entry)
            for rep in range(a.repeats):
                rec = execute(patched, f'c{k:03d}-r{rep}')
                entry['samples'].append(rec); save()
                if rec['returncode'] != 0 or not rec.get('guards_ok'):
                    state['failures'].append({'label': label, 'sample': rep, 'returncode': rec['returncode'],
                                              'timed_out': rec.get('timed_out', False), 'guards_ok': rec.get('guards_ok')})
                    controls(f'recovery-{k:03d}')
                    if len(state['failures']) >= a.max_failures: raise RuntimeError('failure budget reached')
                    break  # never retry a failing candidate
            if (k+1) % 16 == 0: controls(f'after-{k+1}')
            vals = {v for s in entry['samples'] if 'values' in s for v in s['values']}
            print(json.dumps({'candidate': label, 'unique': len(vals), 'changed': vals != {a.preload},
                              'failed': any(s['returncode'] != 0 for s in entry['samples'])}), flush=True)
        controls('after')
        state['complete'] = True; state['passed'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save(); print(json.dumps({'complete': state['complete'], 'failures': len(state['failures']),
                                  'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
