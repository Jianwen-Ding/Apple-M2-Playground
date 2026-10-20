# B32: asynchronous submit cost, batching, and ordering without barriers (2026-10-20)

Blocker B32 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: the host cost is ~20-27 us per
command whether commands are sent one per SUBMIT or 64 per SUBMIT (the kernel's SUBMIT time grows with the number of
commands); batching only shortens the firmware gap between commands (2.6-11 us instead of ~16-22 us). Consecutive
commands on one queue never overlapped and always saw each other's writes, even with `cdm_barrier = NONE`.**
For zluda_agx: keep one asynchronous SUBMIT per launch; batching would save at most ~20% of per-launch host time.

`tests/drm_compute.c` gained a train mode: `AGX_TRAIN=N` launches without waiting, `AGX_TRAIN_BATCH` commands per
SUBMIT, `AGX_TRAIN_BARRIER` = `single` (first command of a submit `cdm_barrier = 0`, command i in the submit `i`),
`none` (first 0, the rest NONE) or `free` (all NONE); a timestamp slot per command; one wait for the last submit.
Kernels (`build.py`, checked in `agx_run`): the pinned control (32 threads) and a counter (thread 0: plain load of a
table word, +1, plain store). AC power, 0 faults.

## Timing (control kernel, median of 3; `timing.jsonl`)

| Launches | Commands per SUBMIT, barrier | Host us per launch | Kernel SUBMIT time per submit | Firmware span | Mean gap between commands |
| --- | --- | --- | --- | --- | --- |
| 1 | 1, single | 440 (includes wake-up) | 92 us | 7.5 us | - |
| 8 | 1, single / 64, none / 64, single | 81 / 101 / 94 | 25 us / 285 us / 197 us | 158 / 83 / 130 us | 15.9 / 5.4 / 11.9 us |
| 64 | 1, single / 64, none / 64, single | 32 / 40 / 55 | 27 us / 1.44 ms / 1.79 ms | 1.75 / 0.52 / 1.02 ms | 22.2 / 2.6 / 10.4 us |
| 512 | 1, single / 64, none / 64, single | **23.3 / 19.1 / 24.3** | 21 us / 0.98 ms / 1.02 ms | 11.3 / 7.2 / 9.9 ms | 18.9 / 11.1 / 16.3 us |

A 64-command SUBMIT costs ~1-1.8 ms in the kernel, i.e. ~15-28 us per command, the same as single submits.

## Ordering without barriers (counter kernel, 1,000 launches, 3 runs each)

| Commands per SUBMIT, barrier | Final counter | Overlapping commands (timestamps) | Mean gap |
| --- | --- | --- | --- |
| 1, single | 1000, 1000, 1000 | 0 | 17-18 us |
| 64, single | 1000, 1000, 1000 | 0 | 17 us |
| 64, none | 1000, 1000, 1000 | 0 | 9.6-10.4 us |
| 1, free (all NONE) | 1000, 1000, 1000 | 0 | 16-16.3 us |
| 64, free (all NONE) | 1000, 1000, 1000 | 0 | 9.8-10.3 us |

So the compute subqueue of one queue runs its commands in order and each command's plain stores are visible to the
next command's plain loads, with or without barrier words. (Concurrency across queues is separate: safe-04 found at
most 4 concurrent commands GPU-wide.)
