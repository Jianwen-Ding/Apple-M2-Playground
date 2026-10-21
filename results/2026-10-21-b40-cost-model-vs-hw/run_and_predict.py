#!/usr/bin/env python3
"""B40 wrapper with agx_run's command line: runs the launch on the GPU (agx_run_hw: results, dumps, firmware time) and
predicts it with the simulator's whole-dispatch model (agx_dispatch, same uniforms and memory; --shared becomes
--tg-bytes, --dump is dropped), appending one JSON line per launch to $B40_LOG. Prints agx_run_hw's output."""
import hashlib, json, os, subprocess, sys
HW = '/scratch/ZLUDA-master/target/release/agx_run_hw'
PRED = '/save/workspace/AGX-Performance-Simulator/rust/target/release/agx_dispatch'
a = sys.argv[1:]
REPEAT = os.environ.get('B40_REPEAT', '20')
hw = subprocess.run([HW] + a + ['--repeat', REPEAT, '--warm-ms', os.environ.get('B40_WARM_MS', '50')], capture_output=True, text=True, timeout=600)
sys.stdout.write(hw.stdout); sys.stderr.write(hw.stderr)
pa, i = [a[0]], 1
while i < len(a):
    k = a[i]
    if k == '--dump': i += 2; continue
    pa += ['--tg-bytes' if k == '--shared' else k, a[i + 1]] if i + 1 < len(a) else [k]
    i += 2
pr = subprocess.run([PRED] + pa, capture_output=True, text=True, timeout=1800)
def last_json(s):
    for line in reversed(s.splitlines()):
        if line.startswith('{'):
            try: return json.loads(line)
            except ValueError: pass
    return {}
h, p = last_json(hw.stdout), last_json(pr.stdout)
geo = {a[j]: a[j + 1] for j in range(1, len(a) - 1) if a[j] in ('--grid', '--wg', '--shared', '--regs')}
rec = {'code': hashlib.sha1(open(a[0], 'rb').read()).hexdigest()[:10], **geo, 'fw_us': h.get('min_fw_ns', h.get('fw_ns', 0)) / 1e3, 'first_fw_us': h.get('first_fw_ns', 0) / 1e3,
       'pred_us': p.get('time_us'), 'pred_error': None if p.get('time_us') is not None else (pr.stdout + pr.stderr)[-200:],
       'hw_completed': h.get('completed')}
with open(os.environ.get('B40_LOG', '/scratch/agxsim-runs/b40/log.jsonl'), 'a') as f:
    f.write(json.dumps(rec) + '\n')
sys.exit(hw.returncode)
