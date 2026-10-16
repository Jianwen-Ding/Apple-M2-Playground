#!/usr/bin/env python3
"""Offline check of novel-results/2026-10-16-battery-clock-states against results/2026-10-16-battery-clock-states."""
import json, statistics, sys
from pathlib import Path

ev = json.loads((Path(__file__).resolve().parents[1] / 'results/2026-10-16-battery-clock-states/evidence.json').read_text())
fails = 0


def check(ok, msg):
    global fails
    print(('ok   ' if ok else 'FAIL ') + msg)
    fails += not ok


runs = ev['sequence'] + [r for r in ev['earlier_same_session'] if 'us' in r]
allv = [v for r in runs for v in r['us']]
fast = [v for v in allv if v < 2000]
slow = [v for v in allv if v > 3400]
mid = [v for v in allv if 2600 < v < 3000]
check(len(fast) + len(slow) + len(mid) + sum(1 for v in allv if 2000 <= v <= 2600 or 3000 <= v <= 3400) == len(allv), 'every sample classified')
ratio = statistics.median(slow) / statistics.median(fast)
check(2.0 < ratio < 2.2, f'fast / slow states {statistics.median(fast):.0f} / {statistics.median(slow):.0f} us, ratio {ratio:.3f}')
check(len(mid) >= 4, f'an intermediate state exists: {len(mid)} samples at {min(mid)}-{max(mid)} us')
check(ev['power']['ac_online'] == 0 and ev['power']['battery_status'] == 'Discharging', 'on battery')
warm = [r for r in runs if r['warmup_ms'] >= 300]
check(all(min(r['us']) > 3400 for r in warm), 'after >= 300 ms of sustained submissions every timed run is in the slow state')
cold = [r for r in ev['sequence'] if r['warmup_ms'] == 0]
check(sum(1 for r in cold if r['us'][0] > 3400) >= 3, 'the first submission after 3 s idle is often slow')
check(sum(1 for r in cold if statistics.median(r['us']) < 2000) >= 3, 'with host gaps between submissions most runs reach the fast state')
pred = ev['model_top_clock_prediction_us']
check(0.8 < pred / statistics.median(fast) < 1.5 and pred / statistics.median(slow) < 0.7, 'the fast state is the top clock the cost model assumes')
fb = ev['llvmpipe_fallback']
check(fb['output_sha256_fallback_run'] == fb['output_sha256_forced_lavapipe'] != fb['output_sha256_gpu'],
      'fallback output is bit-identical to forced lavapipe and differs from the GPU')
check(fb['fallback_rel_error_vs_fp64_reference'] < 1e-6 and min(fb['observed']['host_ns_per_submit']) > 10 * max(fast) * 1e3,
      'fallback results look correct; only the 30x host time and sub-us "GPU" time give it away')
print(f'{fails} failures')
sys.exit(1 if fails else 0)
