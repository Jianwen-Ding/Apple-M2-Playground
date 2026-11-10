#!/usr/bin/env python3
"""clock.py TRIPS N GAP_US [GROUPS] [REPS]: GPU clock ramp study. A dependent-iadd loop (16 iadd per trip, one SIMD
group per workgroup, GROUPS workgroups) submitted N times back to back (GAP_US<0) or each after the previous one ended
plus GAP_US of idle (agx_run_hw with AGX_RUN_HW_GAP_US). Writes every command's start/end to
/scratch/agx-r5/clock/t<TRIPS>-n<N>-g<GAP>-w<GROUPS>-<rep>.txt"""
import os, sys, subprocess, time
sys.path.insert(0, '/save/workspace/AGX-Performance-Simulator/scripts')
import probe_tg_alu as P
trips, n, gap = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
groups = int(sys.argv[4]) if len(sys.argv) > 4 else 38
reps = int(sys.argv[5]) if len(sys.argv) > 5 else 1
pre_idle = float(os.environ.get('IDLE_S', '2'))
code = P.program('p' * 16)
d = '/scratch/agx-r5/clock'; f = d + '/k.bin'; open(f, 'wb').write(code)
common = [f, '--grid', f'{32 * groups},1,1', '--wg', '32,1,1', '--regs', '64', '--uniform', f'5={trips}']
chk = subprocess.run([P.RUN] + common, capture_output=True, text=True)
assert '"instructions"' in chk.stdout, chk.stdout[-300:] + chk.stderr[-300:]
for r in range(reps):
    time.sleep(pre_idle)
    out = f'{d}/t{trips}-n{n}-g{gap}-w{groups}-{r}.txt'
    env = dict(os.environ, AGX_RUN_HW_TRACE=out)
    if gap >= 0: env['AGX_RUN_HW_GAP_US'] = str(gap)
    h = subprocess.run(['/scratch/agx-r5/hwbuild/release/agx_run_hw'] + common + ['--back-to-back', str(n), '--timeout-ms', '10000'], capture_output=True, text=True, env=env)
    print(out, h.stdout.strip()[-120:], h.stderr[-200:], flush=True)
