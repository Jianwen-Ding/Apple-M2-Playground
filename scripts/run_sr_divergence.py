#!/usr/bin/env python3
"""All 256 get_sr selectors read under divergent execution (direct DRM).

The proven 256-selector scan (run_drm_sr_scan.scan_body: straight-line get_sr + stores) runs inside `depth` nested
`if_icmp r0l, ult, rM, r21, 1` ... `pop_exec r0l, 1` blocks (the masked-ALU harness's encodings; no jumps), where
rM = r1 & mask_k and r21 = 1, so lane i executes the reads only when (i & mask_k) == 0 for every level. The control
value r2 is written after the last pop, by every lane, so the whole-buffer oracle still proves the dispatch ran.
Patterns: depth 1-3 with masks 1, 2, 4 (16 / 8 / 4 of 32 lanes active) and `quad` (mask 3: one lane per quad).
Each pattern is compared lane for lane with a uniform scan (no if) of the same launch; inactive lanes' table slots
must keep the sentinel.
"""
import argparse, datetime, json, os, shlex, struct, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import run_drm_sr_scan as scan  # noqa: E402
agx_loop = scan.agx_loop
SENTINEL = scan.SENTINEL
CONTROL = bytes.fromhex('620978563412')     # r2 = 0x12345678
PATTERNS = {'uniform': [], 'depth1': [1], 'depth2': [1, 2], 'depth3': [1, 2, 4], 'quad': [3], 'quad-depth2': [3, 4]}


def body(S, lanes, masks):
    inner = scan.scan_body(range(256), S, lanes)
    assert inner.endswith(CONTROL)
    inner = inner[:-len(CONTROL)]
    pre = agx_loop.chains.mov_imm(21, 1)
    for k, m in enumerate(masks):
        pre += agx_loop.chains.mov_imm(22, m)+agx_loop.encode(f'and r{24+k}, r1, r22')
    opens = b''.join(agx_loop.encode(f'if_icmp r0l, ult, r{24+k}, r21, 1') for k in range(len(masks)))
    closes = b''.join(agx_loop.encode('pop_exec r0l, 1') for _ in masks)
    return pre+opens+inner+closes+agx_loop.encode('wait 0')+CONTROL


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--patterns', default=','.join(PATTERNS))
    p.add_argument('--lanes', type=int, default=64)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/sr-divergence')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    S = (a.lanes+31)//32*32
    state = {'utc': stamp, 'kind': 'sr-divergence', 'lanes': a.lanes, 'patterns': {}, 'passed': False}
    try:
        for name in a.patterns.split(','):
            masks = PATTERNS[name]
            (out/'k.bin').write_bytes(scan.drm.build_main(body(S, a.lanes, masks))+bytes(16))
            (out/'table.bin').write_bytes(struct.pack('<I', SENTINEL)*(256*S))
            env = dict(os.environ, AGX_TABLE_OUT=str(out/'dump'))
            res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(a.lanes), str(out/'rb'), '1', '32', str(out/'table.bin')],
                                 env=env, capture_output=True, timeout=60)
            ev = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
            reps = [e for e in ev if 'rep' in e]
            if res.returncode or not reps or not all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in reps):
                raise RuntimeError(f'{name}: failed or hang signature: {res.stdout.decode(errors="replace")[-300:]}')
            w = list(struct.unpack(f'<{S+32}I', (out/'rb').read_bytes()))
            exp = [SENTINEL]*(S+16)+[0xa5a50000+j for j in range(16)]
            exp[8:8+a.lanes] = [0x12345678]*a.lanes
            t = struct.unpack(f'<{256*S}I', (out/'dump').read_bytes())
            active = [i for i in range(a.lanes) if all((i & m) == 0 for m in masks)]
            vals = {s: list(t[s*S:s*S+a.lanes]) for s in range(256)}
            rec = {'masks': masks, 'buffer_ok': w == exp, 'active_lanes': active,
                   'inactive_untouched': all(vals[s][i] == SENTINEL for s in range(256) for i in range(a.lanes) if i not in active),
                   'active_written': all(vals[s][i] != SENTINEL for s in range(256) for i in active),
                   'values': {s: [vals[s][i] for i in active] for s in range(256)}, 'fw_ns': reps[0]['fw_ts'][1]-reps[0]['fw_ts'][0]}
            state['patterns'][name] = rec
            if not (rec['buffer_ok'] and rec['inactive_untouched'] and rec['active_written']):
                raise RuntimeError(f'{name}: oracle failed (buffer {rec["buffer_ok"]}, inactive {rec["inactive_untouched"]}, active {rec["active_written"]})')
            base = state['patterns'].get('uniform')
            diff = []
            if base and name != 'uniform':
                pos = {i: k for k, i in enumerate(base['active_lanes'])}
                for s in range(256):
                    b = [base['values'][s][pos[i]] for i in active]
                    if b != rec['values'][s]:
                        diff.append(s)
            rec['differs_from_uniform'] = diff
            print(json.dumps({'pattern': name, 'active': len(active), 'ok': True, 'differs_from_uniform': diff,
                              'samples': {s: rec['values'][s][:8] for s in diff}}), flush=True)
        state['passed'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        (out/'record.json').write_text(json.dumps(state)+'\n')
        print(json.dumps({'passed': state['passed'], 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
