# B44: a fault or deadlock in one VM (or queue) does not disturb another (2026-10-21)

Blocker B44 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM through agx_runtime,
battery power. Owner-authorized fault classes already exercised in B20 / B26. `build.py` (control = B20's control kernel,
gated in agx_run; `deadlock.bin` = B26's 1,024-thread / 112-halves barrier kernel, its barrier-free form gated) and
`b44_isolation.rs` (local agx_runtime example): A runs the disturbance, B runs 20 control kernels submitted right behind
it without waiting. Times: GPU us from GET_TIME just before A's submit. A known-good control passed after each layout.

| Layout | A | B correct | B first command (start, end) | B last command end | All done |
| --- | --- | --- | --- | --- | --- |
| two VMs | none (baseline) | 20 / 20 | 317-324 us / 219-223 us | 892 / 922 us | ~1 ms |
| two VMs | op54 instruction fault (timestamps 0) | **20 / 20** | 1,118-1,125 us | 1,603 us | 1.7 ms |
| two VMs | deadlock (ended by the firmware) | **20 / 20** | 483-490 us | **946 us** | 503 ms (A) |
| one VM, two queues | none | 20 / 20 | 148-158 / 125-129 us | 727 / 660 us | ~0.8 ms |
| one VM, two queues | op54 fault | **20 / 20** | 470-477 us | 1,851 us | 2.0 ms |
| one VM, two queues | deadlock | **20 / 20** | 478-485 us | **952 us** | 503 ms (A) |

**Result: faults and deadlocks stay within their command.** Another VM's, and another queue's of the same VM, commands
run correctly and on time: during A's ~0.5 s deadlock, B's 20 commands all finished within the first millisecond (the
deadlocked workgroup holds only its own core's slots). An instruction fault costs B at most ~1 ms of delay. A's fence
signals success with zero timestamps, as in B20. For the simulator's multi-context mode (`agx_device`) this is the
default it already has: a faulted command touches only its own context and the others run on.
