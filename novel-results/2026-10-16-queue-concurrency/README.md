# At most 4 compute commands run at once, GPU-wide, whatever the number of queues or processes

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute, AC power, kernel
6.19.14-400.asahi. Simulator task safe-04 step 2.

## Claim and scope

**Test:**
- `tests/drm_compute.c` `AGX_QUEUES=N` creates N queues on one VM. Each repeat, every queue submits the same
  64-lane delay command (~0.40 ms in the low clock state), with no dependencies, and all are waited for.
- The kernel passed the simulator's `agx_run` oracle before any GPU use.
- N = 2, 4, 8, 16, 32 with 8 repeats each, then two processes × 4 queues at the same time (3 trials). Every readback
  was exact.

| Queues | Commands running at the same instant (firmware timestamps) |
|---|---|
| 2 | 2 |
| 4 | 4 |
| 8, 16, 32 (one process) | **4** |
| 2 processes × 4 queues | **4** in total |

- With N > 4, the fifth command starts 0-20 µs after the first running command ends: a slot is handed over.
- Each command's own time is unchanged (402 µs). The 64-lane commands use 2 of 38 cores, so the limit is not
  cores: **the firmware runs at most four compute commands concurrently, across all processes.**
- Submitting N queues back to back takes 20-230 µs on the host. Start times spread by 16-57 µs for N ≤ 4.

**Not established:**
- whether render (VDM) commands count against the same four;
- whether the limit differs with priorities;
- how slots are chosen when more than four queues are ready (the order looked like submission order).

## Reproducer and evidence

- `make queue-concurrency`: GPU.
- `make verify-queue-concurrency`: offline, 11 checks.
- Runner: `scripts/run_drm_queues.py`.
- [Evidence](../../results/2026-10-16-queue-concurrency/), including the two-process trials and a harness snapshot.

## Runtime implications (CUDA)

- At most four CUDA streams can have kernels executing at the same time on this GPU through the Asahi driver. A
  fifth stream's kernel waits for one to finish, even if cores are idle.
- To fill the GPU with small kernels, merge them, or put several small kernels in one launch, instead of relying on
  many streams.
- Combined with `2026-10-16-commands-per-submit`, which shows that commands within a queue never overlap, the maximum
  concurrency is four commands.
