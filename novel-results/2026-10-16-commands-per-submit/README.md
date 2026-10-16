# Commands in one SUBMIT run strictly in order (0.4-2.5 µs apart without barriers); the clock ramps 3.1x over ~15 ms

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, kernel
6.19.14-400.asahi. Simulator task safe-04 step 4.

## Claim and scope

**Test:**
- `tests/drm_compute.c` `AGX_CMDS=N` puts N identical compute commands (the same CDM stream) into one `SUBMIT`,
  each with its own firmware start / end timestamps.
- `AGX_CMD_BARRIER=chain` sets `cdm_barrier = k` (command k waits on the k before it). `none` sets `NONE` for every
  command after the first.
- Kernels: the pinned control kernel (5.6 µs) and a 4,000-trip delay loop. Both passed the simulator's `agx_run`
  oracle before any GPU use.
- N = 1, 2, 4 ... 64 (the firmware limit `max_commands_per_submission`), 8 repeats each. Every readback was exact.

| | gap between consecutive commands (median) | commands overlap? |
|---|---|---|
| `cdm_barrier = NONE` | **0.4 µs** (delay kernel), 0.7-2.5 µs (control kernel) | **never** (0 of 1,800+ pairs) |
| chained barrier | **~11 µs** (control), ~22.5 µs (delay kernel) | never |
| separate SUBMITs, waiting for each (`2026-10-16-submission-latency`) | ≥ 100 µs round trip (warm) | — |

- **Commands of one queue run strictly in order, one at a time, even without a barrier.** `NONE` only removes the
  wait cost, about 10-20 µs per command.
- Concurrency needs separate queues (`docs/drm-interface.md` §4).
- 64 control commands in one SUBMIT complete in 0.55 ms (no barrier), against about 64 × 110 µs ≈ 7 ms as separate
  synchronous submits.

**Clock ramp (DVFS) under sustained load.** 16 SUBMITs × 64 delay commands back to back, starting from an idle
GPU:

| time since load began | delay-kernel time | implied clock (top = 1,398 MHz) |
|---|---|---|
| 0-6.9 ms | 402-404 µs | ~446 MHz (lowest) |
| 6.9-8 ms | 234 → 222 → 207 µs | ~770-870 MHz |
| 8-15.2 ms | 185 µs | ~973 MHz |
| ≥ 15.3 ms | 128.5-129 µs (959 of 1,024 commands) | 1,398 MHz |

- On AC power, the GPU needs about 15 ms of continuous load to reach its top clock. Short bursts run at about a
  third of peak.
- Consequences for earlier measurements:
  - The "0.40 ms" kernels of the cross-queue sync test were measured in the lowest clock state.
  - On battery, sustained load instead *lowers* the clock (`2026-10-16-battery-clock-states`).
- The clock state is set by the firmware. Kernel durations of a few ms or less must report which state they ran in.

**Not established:**
- whether a chained barrier's cost scales with kernel size (it was ~11 µs for 1 workgroup and ~22.5 µs for 2);
- the full list of clock levels;
- how quickly the clock decays after load stops;
- several *dispatches* inside one command's CDM stream (needs new CDM words; not run).

## Reproducer and evidence

- `make commands-per-submit`: GPU, matrix plus ramp.
- `make verify-commands-per-submit`: offline, 16 checks.
- Runner: `scripts/run_drm_cmds.py`.
- [Evidence](../../results/2026-10-16-commands-per-submit/), with a snapshot of the harness source used.

## Runtime implications (CUDA)

- Put a stream's consecutive kernels into one SUBMIT (≤ 64 commands). Use `cdm_barrier = NONE` when the kernels are
  independent and a chained barrier when one depends on the previous (an extra ~11-23 µs each).
- Order inside a queue is free. Use queues for concurrent streams.
- **Benchmarks:** warm up with ≥ 20 ms of continuous load before timing, or report the clock state. A single short
  kernel measures the 446 MHz state.
