# B43: how commands of different VMs share the GPU (2026-10-21)

Blocker B43 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM, two processes (two VMs,
one queue each), battery power. Firmware timestamps of both processes are on one GPU timebase. 0 faults.

`b43.py`: LONG = B6's loop (8 dependent iadds per trip, 3,000,000 trips) in every thread of 116,736 lanes
(128-lane workgroups, 16 register halves: 38 cores x 96 SIMD groups); SHORT = the same loop with 1,000 trips in one
SIMD group. Gate: the 1,000-trip program in `agx_run`. Every output was correct. `runs.jsonl`:

| Case | A (LONG) | B | B relative to A's start |
| --- | --- | --- | --- |
| LONG alone | 839 ms | - | - |
| B = SHORT, 200 ms later | 741 / 861 ms | **77 ms / 0.044 ms** | starts 201 / 427 ms, ends 278 / 427 ms |
| B = LONG, 100 ms later | 1,315 ms | 1,277 ms | starts 100 ms, ends 1,377 ms (62 ms after A) |
| B = LONG, together | 1,490 ms | 1,490 ms | starts 0.02 ms, ends 0.03 ms after A |

**Result: commands of different VMs run at the same time on the same cores; nothing is serialized or time-sliced
per VM.**
- Two full-GPU commands started together both took 1.49 s and **ended within 26 ns of each other**: their workgroups
  were interleaved across the cores (a serialized pair would take 1.68 s; per-VM time slicing would end them at
  different times). Together they did 13 % more work per second than one alone.
- Started 100 ms apart, the second finished 62 ms after the first, not 0.84 s after it.
- A short command of another VM ran as soon as a SIMD-group slot was free (44 us in one run, 77 ms in the other),
  consistent with the queue-priority finding (`novel-results/2026-10-16-queue-priority`): the firmware hands free
  slots to any ready command and does not preempt running workgroups.
- No switching cost was visible: the second command's start was 0.7 ms after its process was started, which is
  process start-up. The four-command limit (`2026-10-16-queue-concurrency`) is across all VMs.
- SR21 per VM: one slot per VM per launch, distinct among VMs that run together, recycled among 63 values
  (B38, `results/2026-10-21-b38-vms-queues`; `2026-10-16-special-registers`).

For the simulator's multi-context mode: model several VMs' commands as one pool of workgroups competing for slots
(no per-VM time slices, no preemption). For ZLUDA: separate contexts cost no throughput; a long kernel in one context
does not block another context's kernels except through occupied slots.
