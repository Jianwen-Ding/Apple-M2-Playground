#!/usr/bin/env python3
"""Flip the bits applegpu does not account for in documented AGX instructions (direct DRM).

For each instruction in BASELINES the baseline is assembled, forced to its long
form, and run in the opcode-describe body (scripts/run_drm_opcode_describe.py):
r2..r15 preloaded with distinct values plus lane*16 (so lane-dependent ops show),
the candidate, 8 length markers, then r0..r23 stored per lane. Layouts A/B give
the length. Each gap bit (not a constant, field or length bit in applegpu) is
then flipped alone and the full per-lane register dump and length are compared
with the baseline's.

--subops instead sweeps every value of a named sub-op field (e.g. funop.op) to
find values applegpu cannot name.

Classes per flip: same (no observable change), dest (only the destination
register changed), regs (other registers changed), length (instruction length
changed), fault. The run stops at the first fault, then checks an unchanged
control. Gated by CONFIRM_GPU_FAULTS=1.
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

import agx_loop
import run_drm_compute as drm
import run_drm_opcode_describe as D

REPO = Path(__file__).resolve().parents[1]

# Register-only, compute-safe forms. Destination r5 (r5l for 16-bit forms); sources r6..r10.
BASELINES = {
    'mov_imm16': 'mov_imm r5l, 4660',
    'mov_imm32': 'mov_imm r5, 305419896, 0b0',
    'iadd': 'iadd r5, r6, r7',
    'imadd': 'imadd r5, r6, r7, r8',
    'convert': 'convert u32_to_f, r5, r6, rte',
    'bfi': 'bfi r5, r6, r7, r8',
    'bfeil': 'bfeil r5, r6, r7, r8',
    'extr': 'extr r5, r6, r7, r8',
    'shlhi': 'shlhi r5, r6, r7, r8',
    'shrhi': 'shrhi r5, r6, r7, r8',
    'asr': 'asr r5, r6, r7',
    'asrh': 'asrh r5, r6, r7',
    'bitop': 'and r5, r6, r7',
    'bitrev': 'bitrev r5, r6',
    'popcount': 'popcount r5, r6',
    'intl': 'intl r5, r6, r7',
    'ffs': 'ffs r5, r6',
    'fmadd32': 'fmadd32 r5, r6, r7, r8',
    'fmadd16': 'fmadd16 r5l, r6l, r7l, r8l',
    'fadd32': 'fadd32 r5, r6, r7',
    'fadd16': 'fadd16 r5l, r6l, r7l',
    'fmul32': 'fmul32 r5, r6, r7',
    'fmul16': 'fmul16 r5l, r6l, r7l',
    'floor': 'floor r5, r6',
    'ceil': 'ceil r5, r6',
    'trunc': 'trunc r5, r6',
    'rint': 'rint r5, r6',
    'rcp': 'rcp r5, r6',
    'rsqrt': 'rsqrt r5, r6',
    'rsqrt_special': 'rsqrt_special r5, r6',
    'sin_pt_1': 'sin_pt_1 r5, r6',
    'sin_pt_2': 'sin_pt_2 r5, r6',
    'log2': 'log2 r5, r6',
    'exp2': 'exp2 r5, r6',
    'icmpsel': 'icmpsel ult, r5, r6, r7, r8, r9',
    'fcmpsel': 'fcmpsel lt, r5, r6, r7, r8, r9',
    'icmp_ballot': 'icmp_ballot r5, ult, r6, r7',
    'fcmp_ballot': 'fcmp_ballot r5, lt, r6, r7',
    'icmp_quad_ballot': 'icmp_quad_ballot r5, ult, r6, r7',
    'fcmp_quad_ballot': 'fcmp_quad_ballot r5, lt, r6, r7',
    'simd_shuffle': 'simd_shuffle r5, r6, r7l',
    'simd_shuffle_down': 'simd_shuffle_down r5, r6, r7l',
    'simd_shuffle_up': 'simd_shuffle_up r5, r6, r7l',
    'simd_shuffle_xor': 'simd_shuffle_xor r5, r6, r7l',
    'simd_shuffle_rotate_up': 'simd_shuffle_rotate_up r5, r6, r7l',
    'quad_shuffle': 'quad_shuffle r5, r6, r7l',
    'simd_iadd': 'simd_iadd r5, r6',
    'simd_prefix_iadd': 'simd_prefix_iadd r5, r6',
    'simd_fadd': 'simd_fadd r5, r6',
    'simd_min.u': 'simd_min.u r5, r6',
    'quad_iadd': 'quad_iadd r5, r6',
    'quad_and': 'quad_and r5, r6',
    'wait': 'wait 0',
}
DEST = {5}       # r5 is the destination of every baseline
lane_mix = lambda r: agx_loop.encode(f'iadd r{r}, r{r}, r24, lsl 4')


def tools():
    assemble, g = agx_loop._tools()   # puts applegpu on sys.path
    return assemble, g


def long_form(text):
    """Assemble and force the longest encoding; return (int, nbytes, descriptor)."""
    assemble, g = tools()
    b = bytes(assemble.assemble_line(text)); n = g.opcode_to_number(b); d = g.get_instruction_descriptor(n)
    lo, hi = d.sizes
    n &= (1 << (8*len(b)))-1
    if len(b) < hi:
        n |= 1 << d.length_bit_pos
    if d.decode_size(n) != hi or ' '.join(str(d.disassemble(n)).split()) != ' '.join(str(d.disassemble(g.opcode_to_number(b) & ((1 << 8*len(b))-1))).split()):
        raise ValueError('long form changes meaning: '+text)
    return n, hi, d


def gap_bits(d):
    lo, hi = d.sizes
    cov = d.mask | d.fields_mask | ((1 << d.length_bit_pos) if lo != hi else 0)
    return [b for b in range(8*hi) if not cov >> b & 1]


HIGH = []   # set by --high-preload: extra registers preloaded with D.pre(r)


def build(cand, layout):
    """D.build with lane-varied preloads: r2..r15 += lane*16 after the uniform preload."""
    body, seg = D.build(cand, layout)
    out = []
    for name, b in seg:
        out.append((name, b))
        if name == 'preload':
            out.append(('lane-mix', b''.join(lane_mix(r) for r in range(2, 16))))
            if HIGH:
                out.append(('high-preload', b''.join(agx_loop.encode(f'mov_imm r{r}, {D.pre(r)}, 0b0') for r in HIGH)))
    return b''.join(b for _, b in out), out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--only', help='comma list of BASELINES keys (default all)')
    p.add_argument('--subops', help="instead of gap bits: 'key.field' sweeps every value of that field")
    p.add_argument('--bits', help='comma list of extra bit positions to flip (in addition to gap bits)')
    p.add_argument('--no-gaps', action='store_true')
    p.add_argument('--baseline', action='append', default=[], help="extra KEY=ASM baseline (repeatable)")
    p.add_argument('--raw', action='append', default=[], help="KEY:LABEL=HEX raw candidate compared with KEY's baseline (repeatable)")
    p.add_argument('--high-preload', help='first,last register to also preload with distinct values (needs --gprs > 2*last)')
    p.add_argument('--sweep', action='append', default=[], help='KEY:start:size sweeps every value of that bit range (repeatable)')
    p.add_argument('--prefix', default='', help='hex bytes placed before every candidate (and the reference), e.g. input setup')
    p.add_argument('--max-faults', type=int, default=1, help='stop after this many faults (each must be followed by a passing control)')
    p.add_argument('--names', help='regex: only run jobs whose name matches (search)')
    p.add_argument('--masks', help='comma list of hex XOR masks to apply as extra flips (multi-bit)')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--gprs', type=int, default=64)
    p.add_argument('--timeout', type=int, default=20)
    p.add_argument('--output', type=Path)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    _, g = tools()
    if a.high_preload:
        lo_r, hi_r = map(int, a.high_preload.split(','))
        if a.gprs <= 2*hi_r: sys.exit('--gprs must cover the high preload')
        HIGH.extend(range(lo_r, hi_r+1))
    for kv in a.baseline:
        k, asm = kv.split('=', 1); BASELINES[k] = asm
    keys = a.only.split(',') if a.only else list(BASELINES)
    jobs = []
    prefix = bytes.fromhex(a.prefix)
    def job(name, key, n, size, flip):
        cand = prefix+n.to_bytes(size, 'little')
        for layout in 'AB':
            body, seg = build(cand, layout)
            D.decode_check([s for s in seg if s[0] not in ('lane-mix', 'high-preload')])
            jobs.append({'name': f'{name}-{layout}', 'key': key, 'flip': flip, 'layout': layout, 'body': body, 'cand': cand.hex()})
    for layout in 'AB':
        body, _ = build(bytes.fromhex(a.prefix)+D.WAIT, layout)
        jobs.append({'name': f'ref-wait-{layout}', 'key': 'ref', 'flip': None, 'layout': layout, 'body': body, 'cand': '3800'})
    plan = {}
    for key in keys:
        n, size, d = long_form(BASELINES[key])
        if a.subops:
            k2, field = a.subops.split('.')
            if k2 != key: continue
            st, sz = next((s, z) for s, z, nm in d.fields if nm == field)
            base_v = (n >> st) & ((1 << sz)-1)
            vals = [v for v in range(1 << sz) if v != base_v]
            plan[key] = {'field': field, 'start': st, 'size': sz, 'base_value': base_v}
            job(f'{key}-base', key, n, size, None)
            for v in vals:
                job(f'{key}-{field}{v}', key, (n & ~(((1 << sz)-1) << st)) | v << st, size, {'field': field, 'value': v})
            continue
        for sw in a.sweep:
            k2, st, sz = sw.split(':'); st, sz = int(st), int(sz)
            if k2 != key: continue
            cur = (n >> st) & ((1 << sz)-1)
            for v in range(1 << sz):
                if v != cur:
                    job(f'{key}-s{st}_{v}', key, (n & ~(((1 << sz)-1) << st)) | v << st, size, {'field': f'b{st}+{sz}', 'value': v})
        bits = [] if a.no_gaps else gap_bits(d)
        bits += [int(x) for x in a.bits.split(',')] if a.bits else []
        plan[key] = {'descriptor': d.name, 'size': size, 'baseline_hex': n.to_bytes(size, 'little').hex(), 'bits': bits}
        job(f'{key}-base', key, n, size, None)
        for b in bits:
            job(f'{key}-b{b}', key, n ^ (1 << b), size, {'bit': b})
        for m in (a.masks.split(',') if a.masks else []):
            job(f'{key}-m{m}', key, n ^ int(m, 16), size, {'mask': m})
    for kv in a.raw:
        kl, hx = kv.split('='); key, label = kl.split(':')
        b = bytes.fromhex(hx)
        job(f'{key}-r{label}', key, int.from_bytes(b, 'little'), len(b), {'raw': label, 'hex': hx})
    if a.names:
        import re
        jobs = [j for j in jobs if j['key'] == 'ref' or re.search(a.names, j['name'])]
    print(json.dumps({'jobs': len(jobs), 'plan': plan if a.dry_run else len(plan)}), flush=True)
    if a.dry_run:
        return 0
    if os.environ.get('CONFIRM_GPU_FAULTS') != '1':
        sys.exit('refusing: flipped bits are untested encodings. Re-run with CONFIRM_GPU_FAULTS=1.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/bitflip')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode: sys.exit('build failed: '+r.stderr.decode()[-400:])
    state = {'utc': stamp, 'gprs': a.gprs, 'plan': plan, 'results': [], 'complete': False}
    save = lambda: (out/'record.json').write_text(json.dumps(state)+'\n')
    count = 32

    def run(jb):
        code = drm.build_main(jb['body']); cpath = out/'code.bin'; cpath.write_bytes(code+bytes(16))
        table = out/'table.bin'; table.write_bytes(struct.pack('<I', D.SENTINEL)*(D.SLOTS*32))
        rb, dump = out/'readback', out/'table.out'
        rec = {k: jb[k] for k in ('name', 'key', 'flip', 'layout', 'cand')}
        try:
            res = subprocess.run([str(exe), a.device, str(cpath), str(count), str(rb), '1', str(a.gprs), str(table)],
                                 capture_output=True, timeout=a.timeout, env=dict(os.environ, AGX_TABLE_OUT=str(dump)))
            ev = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
            smp = [e for e in ev if 'rep' in e]
            rec['fw_ns'] = [e['fw_ts'][1]-e['fw_ts'][0] for e in smp]
            rec['host_ns'] = [e['host_ns'] for e in smp]; rec['returncode'] = res.returncode
            normal = res.returncode == 0 and bool(smp) and all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in smp)
            if res.returncode == 0:
                w = list(struct.unpack('<64I', rb.read_bytes()))
                guards = all(w[i] == D.SENTINEL for i in range(8)) and all(w[i] == D.SENTINEL for i in range(40, 48)) and \
                    w[48:] == [0xa5a50000+j for j in range(16)]
                t = list(struct.unpack(f'<{D.SLOTS*32}I', dump.read_bytes()))
                rec['table'] = [t[s*32:s*32+32] for s in range(D.SLOTS)]
            else:
                guards = False; rec['stdout_tail'] = res.stdout.decode(errors='replace')[-300:]
            rec['fault'] = not (normal and guards)
        except subprocess.TimeoutExpired:
            rec['fault'] = True; rec['timed_out'] = True
        return rec

    ctrl_body = bytes.fromhex('620978563412')
    try:
        faulted = set()
        for jb in jobs:
            if jb['name'][:-2] in faulted:
                continue   # layout B of an encoding that already faulted in layout A: one recovery is enough
            rec = run(jb); state['results'].append(rec)
            if rec['fault']: faulted.add(jb['name'][:-2])
            print(json.dumps({'name': rec['name'], 'fault': rec['fault']}), flush=True)
            if rec['fault']:
                import time
                time.sleep(2)
                chk = run({'name': 'recovery', 'key': 'ctrl', 'flip': None, 'layout': '-', 'body': ctrl_body, 'cand': ''})
                state.setdefault('faults', []).append({'name': rec['name'], 'control_after_ok': not chk['fault']})
                save()
                if chk['fault'] or len(state['faults']) >= a.max_faults:
                    raise RuntimeError(f"fault on {rec['name']} (control after: {'FAILED' if chk['fault'] else 'ok'})")
            if len(state['results']) % 40 == 0: save()
        state['complete'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        save()
        print(json.dumps({'complete': state['complete'], 'n': len(state['results']), 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
