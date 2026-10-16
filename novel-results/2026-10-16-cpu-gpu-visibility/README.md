# CPU ↔ GPU visibility: GPU stores reach the CPU mid-dispatch only as coherent stores followed by f533; the round trip is under 1 µs

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, WRITEBACK BOs (the
CPU mapping is cached). Simulator task safe-03 step 4.

## Claim and scope

**Shared timebase:** the firmware / `GET_TIME` nanosecond counter equals the ARM generic timer:
`CNTVCT × 1e9 / 24e6`, within the ~100-500 ns read bracket (`tests/drm_timebase.c`, host only).

**Test (`scripts/run_drm_visibility.py`):** a ping-pong with fixed counts only, so nothing waits on a value.
- One SIMD group runs N = 4,096 iterations of:
  - store token k+1 to word T, using one of 6 store / fence variants;
  - f59d, then coherent loads of the CPU's echo word E and clock word C;
  - record both.
- A CPU thread in `tests/drm_compute.c` (`AGX_CPU_ECHO`) logs each new token with its `CNTVCT`, echoes it into E,
  and keeps writing C.
- The kernel passed the simulator's `agx_run` first (with no CPU thread, E and C keep their initial values).
- 4 trials per variant, and every readback was exact.

| Token store, then | CPU sees tokens during the dispatch? |
|---|---|
| plain store (Mesa u4 = 4) | **no**: only the last token, at command end |
| plain + f533 (release) | no |
| coherent store (u4 = 7) | no: only the last token, ~2-4 µs before command end, once the line stops being rewritten |
| plain + Mesa's queue-family sequence (f596 f533 f59a f59e f503 f599 f59d) | no |
| **coherent store + f533** | **yes**: 3,712-4,076 of 4,096 tokens |
| **coherent store + Mesa's sequence** (contains f533) | **yes**: 3,911-4,055 |

- **GPU → CPU needs both a coherent store and the f533 release.** Otherwise the data stays in the GPU's caches until
  the command ends, which flushes them.
- **CPU → GPU** works mid-dispatch with f59d + a coherent load (`2026-10-11-in-shader-clock`). The CPU clock word
  read this way was monotonic in every trial.

**Latency (coherent + f533):**
- The echo of token k is first read at iteration k+1 (median; ≥ 95%). So the full round trip (GPU store → CPU sees
  it → CPU writes → GPU reads) is **under one loop iteration: 0.65-1.2 µs**, depending on clock state.
- The CPU sees the token a median **~250 ns** after the clock value the GPU read just after storing it.
- With Mesa's slower full sequence, the echo already arrives within the same iteration.
- Occasional iterations stall for 5-37 µs, probably firmware or clock events. They show up as outliers.

**Not established:**
- the exact one-way split. The GPU-side time of each iteration is not uniform: per-iteration time varies with the
  clock state, so the firmware start / end interpolation gave negative latencies and was not used;
- write-combined (non-WRITEBACK) BOs;
- the cost of coherent store + f533 in a throughput loop.

## Reproducer and evidence

- `make cpu-gpu-visibility`: GPU.
- `make verify-cpu-gpu-visibility`: offline, 20 checks.
- [Evidence](../../results/2026-10-16-cpu-gpu-visibility/), with the timebase readings and harness snapshots.

## Runtime implications (CUDA)

- Mapped / unified memory written by a kernel is visible to the host **only at kernel end**, unless the kernel uses
  coherent stores followed by f533. That is the lowering of `st.release.sys` / `__threadfence_system()`.
- Host writes become visible to a running kernel through f59d + coherent loads: `ld.acquire.sys` / `volatile`
  system-scope loads.
- A device ↔ host mailbox (progress counters, host-side polling) is feasible with sub-microsecond latency.
- Without these, CUDA's "zero-copy" polling patterns deadlock or stall until kernel end. **A kernel must never spin
  on a host value without a bound.**
