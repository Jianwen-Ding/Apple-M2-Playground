# Queue priority has no measurable effect; a second queue's work shares the GPU at workgroup granularity

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, kernel
6.19.14-400.asahi. Simulator task safe-04 step 1.

## Claim and scope

**Test:**
- **Process A:** queue priority 0 (LOW). It fills the GPU with a large grid of the delay kernel: 17-22 ms per
  dispatch, 48-64 dispatches back to back.
- **Process B:** submits the 32-lane control kernel every 1.5 ms, at priority 1 (MEDIUM) and then at 0 (LOW) as the
  control. Priorities 2 and 3 are rejected by the kernel (`docs/drm-interface.md`).
- Both kernels passed the simulator's `agx_run` oracle before any GPU use, and every readback was exact.
- Three load shapes for A.

| A's load | B command start after SUBMIT (while A runs) | B run time (firmware start → end) |
|---|---|---|
| 4 M lanes, 32-lane workgroups, 0.13-0.4 ms each | median 80-83 µs, max 156 µs | 7.5 / 10.3 µs |
| 1 M lanes, 32-lane workgroups, ~0.64-2 ms each | median 62-76 µs, max 303 µs | 6.1 / 8.5 µs |
| 1 M lanes, **128-lane** workgroups (all 96 SIMD-group slots per core full) | median 79-82 µs, max 260 µs | **291 / 280 µs** |

(The two run times in each row are priority 1 / priority 0.)

- **A second queue's command starts within ~80 µs even while another process saturates the GPU.** The firmware
  interleaves queues; it does not wait for A's dispatch (17-22 ms) to finish.
- Its workgroups then need a free SIMD-group slot:
  - 32-lane workgroups leave about 40 of 96 slots unused per core (occupancy finding), so B runs at once (6-10 µs);
  - when A's 128-lane workgroups fill all 96 slots, B waits for one of A's workgroups to retire (~0.28 ms, about
    half a workgroup's lifetime).
- **MEDIUM against LOW priority made no difference** (within 15%, and in both directions across shapes). No
  preemption of running workgroups was observed.

**Not established:**
- whether the firmware time-slices across queues when neither has free slots for long periods (A's workgroups here
  lasted ≤ 2 ms);
- the effect of priority on queue *start* order when many commands are pending;
- HIGH / REALTIME, which are rejected without driver support.

## Reproducer and evidence

- `make queue-priority`: GPU, three shapes.
- `make verify-queue-priority`: offline, 19 checks.
- Runner: `scripts/run_drm_priority.py`.
- [Evidence](../../results/2026-10-16-queue-priority/), with harness snapshots. Runs 1 and 2 predate the runner's
  `--a-local` option (default 32).

## Runtime implications (CUDA)

- CUDA stream priorities (`cudaStreamCreateWithPriority`) have no hardware effect through this UAPI. Treat them as
  hints.
- A latency-sensitive kernel on another stream starts within ~0.1 ms. If the busy stream fills every slot, it
  finishes only after a resident workgroup retires. Long-running workgroups therefore delay other streams.
- Keep workgroups short when another stream needs responsiveness.
