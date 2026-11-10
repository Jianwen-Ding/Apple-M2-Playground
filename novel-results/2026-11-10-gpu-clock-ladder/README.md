# The GPU clock climbs an 8-step ladder (~3.1x) one step every ~5-7 ms of continuous work; idle gaps of 50 us keep it at the bottom; CPU load does not lower it

Status: confirmed on one device (M2 Max G14C, Asahi, AC power, battery charging), our own probe kernel through
agx_runtime (agx_run_hw copy with per-command timestamps), 2026-11-07 and again 2026-11-10 (same values).

## Test

A dependent-iadd loop (16 `iadd` per trip, one SIMD group per workgroup, 38 workgroups: one per core) built with
`agx_asm`, at 35 / 350 / 3500 trips (~4.7 / 20 / 173 us at the top clock), submitted back to back 1000 times
(`--back-to-back`, nothing waits in between) or one at a time with an idle gap after each (`AGX_RUN_HW_GAP_US`).
Every command's firmware start and end time is recorded (`AGX_RUN_HW_TRACE`, last 1000 commands). The probe is
ALU-bound, so its time is inversely proportional to the core clock.

## Results

1. **Eight discrete states.** The 3500-trip command takes 542, 394, 310, 249, 227, 196, 181 or 173 us, nothing in
   between: 3.13, 2.28, 1.79, 1.44, 1.31, 1.13, 1.04 and 1.00x the top state, i.e. about 446, 614, 781, 971, 1066,
   1236, 1340 and 1398 MHz if the top state is 1398 MHz (the cost model's calibration clock).
2. **The climb.** From an idle GPU, back-to-back work starts at the bottom state and moves up one state roughly every
   5-7 ms of busy time (13 commands at 542 us, 14 at 394, 19 at 310, 19 at 249, 29 at 227, ...): ~35 ms to reach the
   top from cold (t3500 run 0 on 2026-11-07). When the previous run ended a few seconds earlier it starts higher (249 us)
   and reaches the top after ~9-11 ms.
3. **Short commands climb slower.** A ~4.7 us command (t35) stays at ~2.5x (11.7-11.9 us) for 400-500 commands, then
   ~1.5x, ~1.3x, and reaches the top only after ~800 of 1000 commands (~8 ms of busy time, but a longer wall time:
   each short command adds fixed per-command time that does not count as busy). The median of the second half of a
   1000-command burst of such kernels can be anywhere between 1.0x and 1.5x the top-clock time; 5000 commands
   (median of the last 1000) give stable values (re-timed llama.cpp and Halide kernels: repeats within 3%).
4. **Idle gaps pin the clock low.** 300 commands of 3500 trips each followed by 50, 200, 500, 1000, 2000 or 5000 us
   of idle: every command 542-544 us (the bottom state). Submitted one at a time with no extra gap (only the host round
   trip): 249 us (the 4th state). Programs with frequent GPU idle time (a CPU-side gap after each small launch) run
   at a fraction of the top clock however long they run.
5. **CPU load does not lower the GPU clock.** The 350-trip probe at the top state: 20.04-20.08 us (median of the last
   500 commands) with an idle CPU, with 10 CPU threads spinning and idle again.

## Implications

- Kernel times "at the top clock" (the simulator's predictions) need >= ~40 ms of continuous GPU work first; for
  kernels under ~20 us take >= 5000 back-to-back commands.
- In-application launch times can be 1.4-3x the warm times when the application leaves the GPU idle between launches
  (earlier observations: Rodinia in-run times 2.6-3x warm). A clock model needs the application's GPU duty cycle, not
  the kernel alone.
- Earlier "two clock states" observations (261 vs 201 cycles) are two neighbouring steps of this ladder.

## Reproduce

`results/2026-11-10-gpu-clock-ladder/clock.py TRIPS N GAP_US [GROUPS] [REPS]` (needs the AGX Performance Simulator's
`scripts/probe_tg_alu.py` and an agx_run_hw that writes per-command start/end times; the copy used is
/scratch/agx-r5/zcopy, a copy of ZLUDA's agx_runtime with `--back-to-back` up to 20000 and `AGX_RUN_HW_TRACE`).
`clock-cpu.sh` is the CPU-load A/B. Traces: one line per command, `start end` in ns from the first one;
`t3500-n300-g<GAP>-w38-0.txt` are the gap runs (2026-11-07), `cpu-*.txt` the CPU-load runs.
