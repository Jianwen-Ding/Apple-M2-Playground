# Shared-cache capacity by bandwidth: streaming reuse stays cached up to about 14 MiB and reaches DRAM speed by 32 MiB (half-way at about 21 MiB)

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power, GPU clock held at the top state by the clock
keeper. Resolves the open part of safe-03 ("the SLC capacity cannot be read from latency, a bandwidth probe is needed";
[memory-parameters finding](../2026-10-16-memory-parameters/README.md)). A bounded counted loop, emulator-gated, with no data-dependent exit;
the program was also checked in the simulator against an exact oracle. 0 faults. (Hang-budget note: a first run with too few declared
registers lost its timestamps and my wrapper recorded it as an event, so the budget reads 5 of 30 instead of 4.)

## Test

All 65,536 lanes of a dispatch (2,048 SIMD groups on all 38 cores) sweep a shared window of W MiB: lane i loads word `(i + j x 65536) mod W` for
2,048 loads, so every word of the window is read once per pass and the dispatch makes `512 MiB / W` passes. **Total traffic is 512 MiB for every W**,
so the dispatch time shows where the passes after the first stop being served from the caches. One dispatch is one command: a command boundary
flushes the GPU-wide L2 (see the [command-boundary finding](../2026-10-16-l2-command-boundary/README.md)), so only reuse inside a dispatch is
measured, and the first pass is always cold. Table `T[w] = w`; the sums each lane accumulates equal the oracle in every sampled lane of every run.
`scripts/run_drm_slc.py`; 31 dispatches per window; medians.

## Result

| Window | 4 | 8 | 12 | 14 | 16 | 18 | 20 | 22 | 24 | 26 | 28 | 30 | 32 | 36 | 40 | 48 | 64 | 96 | 128 MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Time, ms | 0.337 | 0.344 | 0.359 | 0.372 | 0.429 | 0.540 | 0.676 | 0.961 | 0.999 | 1.190 | 1.341 | 1.379 | 1.408 | 1.431 | 1.442 | 1.461 | 1.455 | 1.474 | 1.497 |
| Effective GB/s | 1,594 | 1,562 | 1,496 | 1,444 | 1,252 | 995 | 795 | 559 | 537 | 451 | 400 | 389 | 381 | 375 | 372 | 368 | 369 | 364 | 359 |

* **Cache regime: 1.4-1.6 TB/s effective for windows up to 14 MiB** (4.4x the DRAM regime). Above the per-core L2 (about 256 KiB x 38 = 9.5 MiB in
  all) the cache that serves reuse must be the shared system-level cache.
* **DRAM regime: 355-380 GB/s from about 32 MiB** (the same 360-370 GB/s the earlier streaming rows give after launch and tail).
* **The transition is smooth, not a cliff:** +10% time at 14 MiB, +15% more at 16, half-way between the two regimes (0.92 ms) at **about 21 MiB**
  (20 MiB: 0.68 ms, 22 MiB: 0.96 ms), 94% of the DRAM time at 32 MiB. A cache of C bytes with strict LRU would step at C under this cyclic access;
  the gradual fall-off says the replacement is not strict LRU (or that other agents hold part of the cache). **Effective capacity for GPU streaming reuse:
  about 21 MiB (14-30 MiB), well below the 48 MB the chip is published with**.
* **CPU streaming does not change it:** with 1 or 8 CPU threads each reading its own 64 MiB in a loop, no window moves by more than 9% (16, 20, 24, 28
  MiB: 0.40 / 0.73 / 1.05 / 1.36 ms idle, 0.44 / 0.67 / 1.08 / 1.25 with 1 thread, 0.43 / 0.67 / 1.13 / 1.28 with 8). The CPU's own bandwidth was not measured.
* **Clock state matters:** without the keeper the same window takes about 0.45 or about 1.0 ms depending on the process (a low GPU clock), which hid
  the structure in the first sweeps. The keeper's 6.3 ms commands flush the cache now and then (only inside the dispatch they land in).

## Cost model

`slc_bytes` in `cost.rs` was 16 MiB and is now **19 MiB**. The model's LRU steps at about 1.15 x `slc_bytes` (22 MiB), which puts the step at the measured
half-way point; the hardware is smooth, so the model is wrong by up to 54% inside the 18-26 MiB transition. Over the 19 windows the model's
`agx_dispatch` prediction has a median error of 9.7% (the same as with 16 MiB, whose step was at about 19 MiB) with the DRAM floor 7% high and the cache
regime about 10% low. `make verify-memory-model` and the other model checks are unchanged (they do not exercise the capacity).

Not established: the replacement policy, the capacity seen by a single core or a few cores, the capacity under CPU *writes*, and whether other GPU
processes share the capacity (the keeper process held only 2 SIMD groups).

## Reproduce

`python3 scripts/run_drm_slc.py offline|hardware [--keeper] [--cpu-threads N] [--windows ...]` (`tests/cpu_stream.c` is the CPU streamer);
`make verify-slc` (offline: 11 checks against [results/2026-10-18-slc](../../results/2026-10-18-slc), including live cost-model predictions; `--no-sim`
skips them).
