#!/usr/bin/env python3
"""Offline checks of the SLC / shared-cache capacity measurement (results/2026-10-18-slc) and of the cost model's SLC capacity."""
import gzip
import json
from pathlib import Path
import statistics as st
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
rec = json.load(gzip.open(ROOT/'results/2026-10-18-slc/slc.json.gz'))
ok = []
TRAFFIC = 512*1048576


def check(name, cond):
    ok.append(bool(cond))
    print('PASS' if cond else 'FAIL', name)


def med(d, w):
    ns = sorted(d['windows'][str(w)]['fw_ns'])
    return ns[len(ns)//2]


sw = rec['sweep']
W = sorted(int(w) for w in sw['windows'])
check('sweep: 19 windows 4..128 MiB, 31 dispatches each, the clock keeper held the top clock, every sampled output word exact',
      len(W) == 19 and all(len(v['fw_ns']) == 31 and v['outputs_exact_sampled'] for v in sw['windows'].values()) and sw['keeper'] and sw['keeper_stopped'])
gbs = {w: TRAFFIC/med(sw, w) for w in W}
check('cache regime: windows of 4, 8, 12 and 14 MiB stream at 1.4-1.6 TB/s effective (%s GB/s)' % ', '.join(f'{gbs[w]:.0f}' for w in (4, 8, 12, 14)),
      all(1400 <= gbs[w] <= 1650 for w in (4, 8, 12, 14)))
check('DRAM regime: windows of 36 MiB and up stream at 355-380 GB/s (%s)' % ', '.join(f'{gbs[w]:.0f}' for w in W if w >= 36), all(355 <= gbs[w] <= 380 for w in W if w >= 36))
check('cache regime is about 4x the DRAM regime (%.1fx)' % (gbs[4]/gbs[128]), 3.8 <= gbs[4]/gbs[128] <= 4.8)
t = [med(sw, w) for w in W]
check('time is non-decreasing from 12 MiB to 40 MiB (the degradation is smooth, no cliff): max step back %.1f%%' % (100*max(0, max((a-b)/a for a, b in zip(t[2:], t[3:])))),
      all(b >= 0.97*a for a, b in zip(t[2:14], t[3:15])))
lo, hi = med(sw, 4), med(sw, 128)
mid = (lo+hi)/2
cross = next(w for w in W if med(sw, w) >= mid)
check('half-way point between the cache and DRAM times (%.2f ms) is crossed between %d MiB and %d MiB (about 21 MiB); the time is +%.0f%% of the 4 MiB time at 14 MiB, +%.0f%% at 16 MiB, and %.0f%% of the 128 MiB time at 32 MiB' %
      (mid/1e6, W[W.index(cross)-1], cross, 100*(med(sw, 14)/lo-1), 100*(med(sw, 16)/med(sw, 14)-1), 100*med(sw, 32)/hi),
      (W[W.index(cross)-1], cross) == (20, 22) and med(sw, 16) > 1.05*med(sw, 14) and med(sw, 14) < 1.12*lo and med(sw, 32) > 0.93*hi)
for T in ('cpu1', 'cpu8'):
    d = rec[T]
    rel = [abs(med(d, w)/med(rec['cpu0'], w)-1) for w in (8, 16, 20, 24, 28, 40)]
    check(f'{T}: CPU streaming ({d["cpu_threads"]} thread(s), 64 MiB each) changes no window by more than 13% (worst {100*max(rel):.0f}%) against the idle run', max(rel) < 0.13)
check('without the clock keeper the same windows take 2-3x longer in some processes (clock state), which is why the sweep uses it: 8 MiB 0.45 vs 1.0 ms',
      any(x > 900000 for x in rec['no_keeper_small']['windows']['8']['fw_ns']) and any(x < 480000 for x in rec['no_keeper_small']['windows']['8']['fw_ns']))
if '--no-sim' not in sys.argv:
    sys.path.insert(0, str(ROOT/'scripts'))
    import run_drm_compute as drm
    import run_drm_slc as R
    AD = ROOT.parent/'AGX-Performance-Simulator/rust/target/release/agx_dispatch'
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td/'out.bin').write_bytes(b'\xcd'*(4*(8+65536+8+16)))
        with open(td/'table.bin', 'wb') as f:
            f.truncate(128 << 20)
        pred = {}
        for wm in W:
            (td/'c.bin').write_bytes(drm.build_main(R.body(R.TRIPS, wm*262144))+bytes(16))
            r = subprocess.run([str(AD), str(td/'c.bin'), '--grid', '65536,1,1', '--wg', '32,1,1', '--regs', '64', '--clock', '1398', '--uniform', '5=65536',
                                '--uniform', '6=%d' % (0x1100008000 & 0xffffffff), '--uniform', '7=%d' % (0x1100008000 >> 32),
                                '--uniform', '8=%d' % (0x1100100000 & 0xffffffff), '--uniform', '9=%d' % (0x1100100000 >> 32),
                                '--map', f'0x1100008000={td/"out.bin"}', '--map', f'0x1100100000={td/"table.bin"}'], capture_output=True, text=True)
            pred[wm] = json.loads(r.stdout)['time_us']
    err = {w: abs(pred[w]/(med(sw, w)/1000)-1) for w in W}
    check('cost model (slc_bytes = 19 MiB): cache-regime time (< 600 us) up to 20 MiB (%.0f us at 20), DRAM-regime time (> 1200 us) from 24 MiB (%.0f us), the step is at about 22 MiB (%.0f us at 22): a step where the hardware falls off smoothly' %
          (pred[20], pred[24], pred[22]), all(pred[w] < 600 for w in W if w <= 20) and all(pred[w] > 1200 for w in W if w >= 24) and 600 < pred[22] < 1200)
    check('cost model over the 19 windows: median |error| %.1f%% (<= 12%%), worst %.0f%% (in the 18-26 MiB transition), DRAM floor %+.0f%% at 40 MiB' %
          (100*st.median(err.values()), 100*max(err.values()), 100*(pred[40]/(med(sw, 40)/1000)-1)),
          st.median(err.values()) <= 0.12 and max(err, key=err.get) in range(18, 27) and abs(pred[40]/(med(sw, 40)/1000)-1) < 0.08)
sys.exit(0 if all(ok) else 1)
