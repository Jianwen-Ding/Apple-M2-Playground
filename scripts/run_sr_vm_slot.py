#!/usr/bin/env python3
"""SR21 (Mesa: vm_slot) across concurrent and sequential GPU VMs, on the direct DRM path.

Every drm_compute process creates its own VM and queue. The kernel is the proven 256-selector scan
(run_drm_sr_scan.scan_body: straight-line get_sr + stores) followed by the emulator-gated delay loop, so each
submission stays resident for a few ms. K processes are started together, each submitting REPEATS times, so their
VMs are live at the same time; then the same number run one after another. Each process's final table gives SR21
(and SR113, SR20, SR17) for every lane. Hypothesis: SR21 is the hardware VM (UAT context) slot the VM is bound to:
uniform per process, distinct between VMs that are live together, in 1..63.

Output: one JSON summary line per process, and record.json in the run directory.
"""
import argparse, datetime, json, os, shlex, struct, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import run_drm_sr_scan as scan  # noqa: E402

SENTINEL = scan.SENTINEL
SELECTORS = (17, 20, 21, 113)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--concurrent', type=int, default=8)
    p.add_argument('--sequential', type=int, default=8)
    p.add_argument('--repeats', type=int, default=20)
    p.add_argument('--delay', type=int, default=8000, help='delay-loop trips after the scan (4000 is about 1 ms)')
    p.add_argument('--lanes', type=int, default=64)
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    p.add_argument('--gaps-ms', default='', help='comma list: sleep before each sequential process (cycled); records SR113 '
                   'against the firmware duration of every submission')
    a = p.parse_args()
    if not 1 <= a.concurrent <= 32 or a.delay > 20000:
        sys.exit('refusing: at most 32 concurrent processes and 20000 delay trips (keeps each submission well under the hang check)')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/sr-vm-slot')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    S = (a.lanes+31)//32*32
    code = scan.drm.build_main(scan.scan_body(range(256), S, a.lanes, 1, a.delay))
    (out/'scan.bin').write_bytes(code+bytes(16))
    state = {'utc': stamp, 'kind': 'sr-vm-slot', 'args': vars(a) | {'output': str(out)}, 'phases': {}, 'passed': False}

    def launch(tag):
        d = out/tag
        d.mkdir()
        (d/'table.bin').write_bytes(struct.pack('<I', SENTINEL)*(256*S))
        env = dict(os.environ, AGX_TABLE_OUT=str(d/'dump.table'))
        cmd = [str(exe), a.device, str(out/'scan.bin'), str(a.lanes), str(d/'readback'), str(a.repeats), '32', str(d/'table.bin')]
        return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE), d, time.monotonic()

    def collect(proc, d, t0):
        so, _ = proc.communicate(timeout=120)
        t1 = time.monotonic()
        ev = [json.loads(l) for l in so.decode(errors='replace').splitlines() if l.startswith('{')]
        reps = [e for e in ev if 'rep' in e]
        rec = {'returncode': proc.returncode, 'reps': len(reps), 'wall_s': [t0, t1],
               'fw_ns': [e['fw_ts'][1]-e['fw_ts'][0] for e in reps if e.get('fw_ts')],
               'normal': bool(reps) and all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in reps)}
        if proc.returncode or not rec['normal']:
            rec['stdout_tail'] = so.decode(errors='replace')[-600:]
            return rec
        w = list(struct.unpack(f'<{S+32}I', (d/'readback').read_bytes()))
        exp = [SENTINEL]*(S+16)+[0xa5a50000+j for j in range(16)]
        exp[8:8+a.lanes] = [0x12345678]*a.lanes
        t = struct.unpack(f'<{256*S}I', (d/'dump.table').read_bytes())
        rec['buffer_ok'] = w == exp
        rec['values'] = {s: sorted(set(t[s*S:s*S+a.lanes])) for s in SELECTORS}
        rec['per_lane'] = {s: list(t[s*S:s*S+a.lanes]) for s in SELECTORS}
        for f in ('dump.table', 'table.bin', 'readback'):
            (d/f).unlink(missing_ok=True)
        return rec

    try:
        for phase, n, together in (('concurrent', a.concurrent, True), ('sequential', a.sequential, False)):
            recs = []
            if together:
                procs = [launch(f'{phase}-{i}') for i in range(n)]
                recs = [collect(*x) for x in procs]
            else:
                gaps = [int(g) for g in a.gaps_ms.split(',') if g]
                for i in range(n):
                    if gaps:
                        time.sleep(gaps[i % len(gaps)]/1e3)
                    recs.append(collect(*launch(f'{phase}-{i}')))
                    recs[-1]['gap_ms'] = gaps[i % len(gaps)] if gaps else 0
            state['phases'][phase] = recs
            for i, rec in enumerate(recs):
                print(json.dumps({'phase': phase, 'proc': i, 'ok': rec.get('buffer_ok'), 'normal': rec['normal'],
                                  'sr21': rec.get('values', {}).get(21), 'sr113': rec.get('values', {}).get(113),
                                  'fw_us': [round(x/1e3) for x in rec['fw_ns']], 'gap_ms': rec.get('gap_ms'),
                                  'wall_ms': round(1e3*(rec['wall_s'][1]-rec['wall_s'][0]))}), flush=True)
            bad = [i for i, r in enumerate(recs) if not (r['normal'] and r.get('buffer_ok'))]
            if bad:
                raise RuntimeError(f'{phase}: processes {bad} failed the oracle or the hang check')
        state['passed'] = True
    except Exception as e:
        state['error'] = f'{type(e).__name__}: {e}'
    finally:
        (out/'record.json').write_text(json.dumps(state)+'\n')
        print(json.dumps({'passed': state['passed'], 'output': str(out), 'error': state.get('error')}), flush=True)
    return 0 if state['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
