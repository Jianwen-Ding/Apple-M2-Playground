# Stores of one dispatch are visible to cached loads of the next, even with normal stores and no invalidate

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. One process, one queue.
Straight-line program, no loops or spin-waits, Mesa-emitted encodings only. Gated in the Rust simulator (including a
planted-staleness table to check the stale counter) before submitting.

## Test

`drm_compute` submits the same program 16 times (one dispatch per SUBMIT, in order) over one persistent table. Each of
65,536 lanes (32-lane workgroups; partner lane = i ^ 32) does: `c` = coherent load of its own counter (authoritative);
`pc` = load of the partner's counter, **cached** (Mesa u4 = 4) or coherent, optionally after `device_barrier_1` (f59d);
then `counter = c + 1` with a normal (u4 = 4) or coherent (u4 = 7) store. `pc < c` counts as a stale read: the partner
counter at dispatch k must be at least k - 1. No fence is used inside the program.

## Result

* **0 stale reads** in 24 runs (8 variants x 3 repeats): cached or coherent load, normal or coherent store, with or
  without f59d before the load. That is 24 x 15 dispatch boundaries x 65,536 lanes of reads after a boundary.
* Every lane counter ended at exactly 16 and every dispatch had firmware timestamps (all ran, in order).
* A dispatch boundary therefore flushes the previous dispatch's stores and drops stale cached lines: **a CUDA runtime
  does not need an explicit cache invalidate or fence at kernel start** for data written by an earlier kernel in the
  same stream/queue, even when that kernel used ordinary stores.
* Contrast: within one dispatch, a cached load of another core's data can be stale without f59d
  ([memory-ordering finding](../2026-10-11-memory-ordering/README.md)); the boundary supplies that invalidate.

Not established: other processes or queues (see the [command-boundary finding](../2026-10-16-l2-command-boundary/README.md)
for the L2 effect of other queues' boundaries), CPU-written data (CPU/GPU visibility has its own
[finding](../2026-10-16-cpu-gpu-visibility/README.md)), several commands in one SUBMIT with `AGX_CMD_BARRIER=none`,
and whether the cached line was actually resident on the reading core before each boundary.

## Reproduce

`scripts/run_drm_dispatch_visibility.py` (hardware; registers beyond r23 need `--gprs 64`, which the runner passes),
`make verify-dispatch-visibility` (offline, 4 checks against
[results/2026-10-18-dispatch-visibility](../../results/2026-10-18-dispatch-visibility)).
