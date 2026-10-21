# B38: VMs and queues in one process (2026-10-21)

Blocker B38 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM through agx_runtime,
battery power. 0 faults; hang budget unchanged.

**Result: no limit was reached. One process created 2,048 VMs (one queue each) or 2,048 queues on one VM, all alive at
once, and every one ran a launch correctly.** Creation never failed; memory is the only practical bound (agx_runtime
gives each queue 4.25 MiB of rings).

`b38_limits.rs CODE V Q` (local agx_runtime example, not pushed to ZLUDA) creates V VMs x Q queues, submits one 64-lane
launch of `sr21count.bin` (`build.py`, checked in `agx_run`: every lane adds 1 to the launch's own counter and stores
SR21) on every queue **without waiting**, then waits for all. `runs.jsonl`:

| VMs x queues | Created | Launches correct | Distinct SR21 (VM slot) | Wall time |
| --- | --- | --- | --- | --- |
| 1x1, 2x1, 4x1, 16x1 | all | all | 1, 2, 4, 16 | 1-14 ms |
| 1x16, 4x16, 16x16 | all | 16, 64, 256 | 1, 4, 16 | 16-226 ms |
| 64x1 | 64 | 64 | **63** | 76 ms |
| 128x1, 512x1, 2,048x1 | all | all | 62-63 | 0.11-1.7 s |
| 1x256, 1x1,024, 1x2,048 | all | all | 1 | 0.21-1.6 s |

- **VMs are not limited by the 63 hardware VM slots** (SR21 = 1..63, `novel-results/2026-10-16-special-registers`):
  the kernel binds a VM to a slot only while it has work, so 2,048 live VMs with queued work all completed, sharing
  at most 63 slots. Each VM saw exactly one slot during its launch.
- **Queues per VM:** at least 2,048 (the earlier interface map stopped at 64). At most 4 commands run at once GPU-wide
  (`2026-10-16-queue-concurrency`), so more queues add ordering freedom, not parallelism.
- **Priorities** (already measured, `2026-10-16-queue-priority`, `docs/drm-interface.md`): only LOW (0) and MEDIUM (1)
  are accepted; HIGH, REALTIME and 4 give EINVAL; LOW against MEDIUM changes nothing measurable.

For ZLUDA: one VM per CUDA context and one queue per stream are fine at any realistic count;
`cuStreamCreateWithPriority` should accept the priority range but map every stream to MEDIUM (reporting
`cuCtxGetStreamPriorityRange` as [0, 0] is the honest answer).

Bug found while writing the probe: pipeline words embed the uniform buffer's address, so they cannot be shared between
launches with different uniform buffers (a shared copy made every launch read uniforms at 0, complete "successfully"
and write nothing). agx_runtime already stages them per launch.
