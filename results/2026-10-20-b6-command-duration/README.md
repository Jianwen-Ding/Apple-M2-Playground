# B6: longest single compute command (2026-10-20)

Blocker B6 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: no limit found for a command that keeps
issuing instructions; one compute command ran 79.9 s and completed with the correct result.** A command that stops
making progress is different: the barrier deadlock in B26 was ended by the firmware after ~0.50 s.

`b6.py`: one SIMD group runs `agx_loop.loop_body(TRIPS, 8)` (8 dependent `iadd` per trip). The same program with
1,000 trips passed `agx_run` against its oracle first (only the trip-count immediate differs; the long versions are
too slow to simulate). `tests/drm_compute.c` gained `AGX_WAIT_MS` (host syncobj wait limit, default 3,000) for these
runs. AC power, one run per length, 0 faults; hang budget unchanged.

| Trips | Firmware time | Host time | Fence | Output |
| --- | --- | --- | --- | --- |
| 1,000,000 | 42.6 ms | 0.05 s | ok | correct |
| 11,700,000 | 0.44 s | 0.44 s | ok | correct |
| 23,500,000 | 0.88 s | 0.88 s | ok | correct |
| 47,000,000 | 1.76 s | 1.76 s | ok | correct |
| 94,000,000 | 3.50 s | 3.51 s | ok | correct |
| 188,000,000 | 7.00 s | 7.00 s | ok | correct |
| 376,000,000 | 13.99 s | 14.00 s | ok | correct |
| 752,000,000 | 27.98 s | 27.98 s | ok | correct |
| 1,504,000,000 | 55.95 s | 55.95 s | ok | correct |
| 2,147,483,647 (loop maximum) | **79.89 s** | 79.89 s | ok | correct |

(37.2 ns per trip at length, against 42.6 ns at 1 M trips: the clock ramps up.)

**For a CUDA runtime:** report `kernelExecTimeoutEnabled = 0`; long kernels are not killed. Deadlocked kernels
(no forward progress, e.g. a barrier that cannot complete) are ended after ~0.5 s with a successful fence and unwritten
timestamps, which B20's timestamp check turns into `CUDA_ERROR_LAUNCH_FAILED`.

Not tested: a kernel that loops forever while issuing instructions (it may never be ended by the firmware; a runtime
would need its own cancellation), commands longer than 80 s, and whether several cores busy at once change anything.
