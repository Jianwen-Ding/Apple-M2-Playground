# Launch latency on direct DRM: ~55 µs with the GPU warm, ~0.4-0.7 ms when it has to wake up

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, kernel
6.19.14-400.asahi. Simulator task safe-04 step 3.

## Claim and scope

**Test:**
- One queue submits the pinned control kernel (32 lanes) and waits for its syncobj, `repeats` times per host sleep
  ("gap") of 0 µs-100 ms. The kernel passed the simulator's `agx_run` oracle before any GPU use.
- Times are in the GPU timebase (ns): `GET_TIME` just before `SUBMIT`, firmware start / end timestamps of the
  command, and `GET_TIME` just after the wait returns.

| GPU state before SUBMIT | submit → firmware start | firmware end → host awake | control dispatch (firmware) |
|---|---|---|---|
| warm (just ran, or another process keeps it busy) | **40-140 µs** (median ~55-65) | 38-75 µs | ~2.8 µs when busy, ~5.5 µs otherwise |
| woken from idle | **0.37-0.75 ms** | same | ~6.6-7.0 µs |

**When the wake-up is paid:**
- **Idle ≥ 1 ms:** at least 13 of 15 submissions are slow.
- **Idle ≥ 30 ms:** all of them are slow.
- **Idle < 1 ms:** a mix. With no host sleep (≈ 55 µs idle between a fence and the next submit), slow and fast
  submissions **alternate** (slow, fast, slow, fast ...). The GPU starts powering down very soon after it goes idle.
- **Another process keeps the GPU busy:** 40 back-to-back processes of a 64-lane delay kernel, itself
  simulator-gated. Then **no** submission was slower than 140 µs at host sleeps of 0, 1 or 3 ms (≥ 75
  submissions). The slow path is therefore GPU power-up, not driver cost.

A synchronous submit → wait round trip of one tiny kernel therefore costs about 90-130 µs warm and about 0.45-0.8 ms
cold.

**Not established:**
- the exact power-down timer, and why it alternates at a zero gap;
- whether the 56 ms SR113 firmware cycle (`2026-10-16-special-registers`) is the same mechanism;
- behaviour on battery (record the power source with any timing; see `2026-10-16-battery-clock-states`).

## Reproducer and evidence

- `make submit-latency`: GPU, idle sweep.
- `make verify-submit-latency`: offline, 15 checks.
- Runner: `scripts/run_drm_submit_latency.py` (gate: `scripts/sim_gate.py`).
- [Evidence](../../results/2026-10-16-submit-latency/): the idle sweeps, the busy run and the background kernel.

## Compiler and runtime implications (CUDA)

- **Launch latency floor** on Asahi through direct DRM is ~55 µs from SUBMIT to execution, far above CUDA's few µs.
  Batch kernels: up to 64 commands per SUBMIT (`docs/drm-interface.md`), or several dispatches per command.
- **The GPU powers down within about a millisecond of idle**, so the first launch after a pause costs about
  0.4-0.7 ms more.
  - A runtime that wants low latency for sporadic launches must keep the GPU busy, or accept the wake-up.
  - Benchmarks must warm up, or discard the first launch after any pause.
- A cross-queue syncobj dependency adds about 0.1 ms (`docs/drm-interface.md` §4).
