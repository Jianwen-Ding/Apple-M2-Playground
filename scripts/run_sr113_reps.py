#!/usr/bin/env python3
"""SR113 over consecutive submissions of one process (direct DRM).

Every lane of every submission atomically adds its SR113 to one table word (device atomic add, validated in
sr-direct-drm), then the usual control store. With L lanes and R submissions the word ends at
sentinel + L * sum(SR113 per submission), so (word - sentinel) / (8 L) counts the submissions that read 8.
A second word gets 1 per lane per submission, proving every submission ran (= L * R).
Processes with R = 1, 2, 3, 5, 10, 20 submissions, each several times, optionally after an idle gap.
"""
import argparse, datetime, json, os, shlex, struct, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'scripts'))
import run_drm_sr_scan as scan  # noqa: E402
agx_loop = scan.agx_loop
SENTINEL = scan.SENTINEL


def timeline_body(S, delay, base=0, middle=None, preload_end=None):
    """Each lane reads SR113 before and after the delay loop (or `middle`, e.g. a pointer chase): word base+S += start,
    base+3S += end, base+4S += start ^ end, base+2S += 1. A nonzero base+4S word means SR113 changed while the dispatch ran."""
    w = lambda k: base+k*S
    b = scan.get_sr(113, 6)+agx_loop.chains.mov_imm(5, w(1))+agx_loop.atomic_add(8, 5, 6)
    b += agx_loop.chains.mov_imm(5, w(2))+agx_loop.chains.mov_imm(9, 1)+agx_loop.atomic_add(8, 5, 9)
    b += scan.get_sr(21, 11)+agx_loop.chains.mov_imm(5, w(6))+agx_loop.atomic_add(8, 5, 11)+agx_loop.encode('wait 0')
    b += middle if middle is not None else scan.delay_loop(delay)
    if preload_end is not None:     # a get_sr that did not write would leave this value in r7
        b += agx_loop.chains.mov_imm(7, preload_end)
    b += scan.get_sr(113, 7)+agx_loop.chains.mov_imm(5, w(3))+agx_loop.atomic_add(8, 5, 7)
    b += agx_loop.encode('xor r8, r6, r7')+agx_loop.chains.mov_imm(5, w(4))+agx_loop.atomic_add(8, 5, 8)
    # SR21 (VM slot) at the end, summed: word 5 / (lanes x submissions) is the slot when it never changed
    b += scan.get_sr(21, 10)+agx_loop.chains.mov_imm(5, w(5))+agx_loop.atomic_add(8, 5, 10)
    b += agx_loop.encode('wait 0')+bytes.fromhex('620978563412')
    return b


def body(S, delay=0):
    b = agx_loop.chains.mov_imm(5, 1*S)+scan.get_sr(113, 6)+agx_loop.atomic_add(8, 5, 6)
    b += agx_loop.chains.mov_imm(5, 2*S)+agx_loop.chains.mov_imm(7, 1)+agx_loop.atomic_add(8, 5, 7)
    b += agx_loop.encode('wait 0')
    if delay:
        b += scan.delay_loop(delay)
    b += bytes.fromhex('620978563412')
    return b


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reps', default='1,2,3,5,10,20')
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--gap-ms', type=int, default=0, help='sleep before each process')
    p.add_argument('--lanes', type=int, default=64)
    p.add_argument('--rep-sleep-us', type=int, default=0, help='host pause between submissions (drm_compute AGX_REP_SLEEP_US)')
    p.add_argument('--chase', type=int, default=0, help='with --timeline: a pointer chase of this many hops over a 32 MiB '
                   'single random cycle (DRAM-latency bound) between the two SR113 reads, instead of the delay loop')
    p.add_argument('--preload-end', type=lambda v: int(v, 0), help='with --timeline: set r7 to this value just before the end SR113 read')
    p.add_argument('--timeline', action='store_true', help='read SR113 before and after the delay loop (needs --delay)')
    p.add_argument('--delay', type=int, default=0, help='delay-loop trips after the atomics (4000 is about 1 ms; max 20000)')
    p.add_argument('--device', default='/dev/dri/renderD128')
    p.add_argument('--output', type=Path)
    p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    a = p.parse_args()
    if a.delay > 20000:
        sys.exit('refusing: delay > 20000 trips')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = a.output or Path('/scratch/apple-m2-playground/drm-compute/sr113-reps')/stamp
    out.mkdir(parents=True, exist_ok=False)
    exe = out/'drm_compute'
    r = subprocess.run(shlex.split(a.cc)+['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', str(REPO/'tests/drm_compute.c'), '-o', str(exe)],
                       capture_output=True, timeout=60)
    if r.returncode:
        sys.exit('build failed: '+r.stderr.decode()[-400:])
    S = (a.lanes+31)//32*32
    base, prefix = 0, b''
    if a.chase:
        if not (a.timeline and 1 <= a.chase <= 20000):
            sys.exit('--chase needs --timeline and 1..20000 hops')
        foot, stride = 32 << 20, 64
        table = agx_loop.chase_table(foot//stride, stride//4, 1)
        ok, sbody, _, _ = agx_loop.check_chase(16, 1, table, active=32)
        cbody = agx_loop.chase_body(a.chase, 1)
        diff = [i for i, (x, y) in enumerate(zip(cbody, sbody)) if x != y]
        if not ok or len(cbody) != len(sbody) or any(not 8 <= i < 12 for i in diff):
            sys.exit('chase emulator gate failed')
        base, prefix = len(table), table.tobytes()
        kbody = timeline_body(S, 0, base, cbody, a.preload_end)
    else:
        kbody = timeline_body(S, a.delay, preload_end=a.preload_end) if a.timeline else body(S, a.delay)
    (out/'k.bin').write_bytes(scan.drm.build_main(kbody)+bytes(16))
    rows = []
    try:
        for t in range(a.trials):
            for R in [int(x) for x in a.reps.split(',')]:
                time.sleep(a.gap_ms/1e3)
                (out/'table.bin').write_bytes(prefix+struct.pack('<I', SENTINEL)*(7*S))
                env = dict(os.environ, AGX_TABLE_OUT=str(out/'dump'), AGX_TABLE_PEEK=','.join(str(base+k*S) for k in range(1, 7)), AGX_REP_SLEEP_US=str(a.rep_sleep_us))
                res = subprocess.run([str(exe), a.device, str(out/'k.bin'), str(a.lanes), str(out/'rb'), str(R), '32', str(out/'table.bin')],
                                     env=env, capture_output=True, timeout=60)
                ev = [json.loads(l) for l in res.stdout.decode(errors='replace').splitlines() if l.startswith('{')]
                reps = [e for e in ev if 'rep' in e]
                normal = res.returncode == 0 and len(reps) == R and all(e['fw_ts'][0] and e['fw_ts'][1] and e['host_ns'] < 50_000_000 for e in reps)
                if not normal:
                    raise RuntimeError(f'R={R}: failed or hang signature: {res.stdout.decode(errors="replace")[-300:]}')
                t_ = struct.unpack(f'<{7*S}I', (out/'dump').read_bytes()[4*base:])
                w = list(struct.unpack(f'<{S+32}I', (out/'rb').read_bytes()))
                exp = [SENTINEL]*(S+16)+[0xa5a50000+j for j in range(16)]
                exp[8:8+a.lanes] = [0x12345678]*a.lanes
                ran = (t_[2*S]-SENTINEL) & 0xffffffff
                s113 = (t_[S]-SENTINEL) & 0xffffffff
                row = {'trial': t, 'R': R, 'buffer_ok': w == exp, 'ran_ok': ran == a.lanes*R, 'sr113_sum': s113,
                       'reps_reading_8': s113/(8*a.lanes),
                       'peek': [e.get('peek') for e in reps],
                       'end_reps_reading_8': ((t_[3*S]-SENTINEL) & 0xffffffff)/(8*a.lanes) if a.timeline else None,
                       'lanes_changed': ((t_[4*S]-SENTINEL) & 0xffffffff)//8 if a.timeline else None,
                       'vm_slot_end': ((t_[5*S]-SENTINEL) & 0xffffffff)/(a.lanes*R) if a.timeline else None,
                       'vm_slot_start': ((t_[6*S]-SENTINEL) & 0xffffffff)/(a.lanes*R) if a.timeline else None, 'fw_us': [round((e['fw_ts'][1]-e['fw_ts'][0])/1e3, 1) for e in reps], 'fw_ts': [e['fw_ts'] for e in reps]}
                rows.append(row)
                print(json.dumps(row), flush=True)
                if not (row['buffer_ok'] and row['ran_ok']):
                    raise RuntimeError('oracle failed')
        passed = True
    except Exception as e:
        passed = False
        print(json.dumps({'error': f'{type(e).__name__}: {e}'}), flush=True)
    (out/'record.json').write_text(json.dumps({'utc': stamp, 'args': vars(a) | {'output': str(out)}, 'rows': rows, 'passed': passed})+'\n')
    print(json.dumps({'passed': passed, 'output': str(out)}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
