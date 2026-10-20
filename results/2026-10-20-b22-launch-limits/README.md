# B22: launch limits on the M2 Max (2026-10-20)

Blocker B22 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. **Result: the CDM global sizes are full 32-bit
thread counts in every dimension, a workgroup can be 1,024 threads along x, y or z, and a larger workgroup silently
runs nothing.**

`count.bin` (`build.py`, checked in `agx_run` first): the control kernel with its bounds check opened (u5 =
0xffffffff); lanes whose x grid position is a multiple of 32 atomically add 1 to a counter, and every output store
goes to VA 2^39 (outside the VM, dropped by soft faults). `b22_limits.rs` (local agx_runtime example, not pushed)
builds the CDM stream by hand so sizes above agx_runtime's own limits can be sent. 0 faults in the final runs.

| Global (x, y, z) | Local | Counter | Expected | Firmware time |
| --- | --- | --- | --- | --- |
| 1024, 1, 1 | 1024, 1, 1 | 32 | 32 | 9 us |
| 1, 1024, 1 | 1, 1024, 1 | 1024 | 1024 (all x = 0) | 13 us |
| 1, 1, 1024 | 1, 1, 1024 | 1024 | 1024 | 13 us |
| 2^28, 1, 1 | 1024 | 8,388,608 | 8,388,608 | 28.5 ms |
| 2^30, 1, 1 | 1024 | 33,554,432 | 33,554,432 | 126 ms |
| **2^31, 1, 1** | 1024 | 67,108,864 | 67,108,864 | 261 ms |
| **2^32 - 32, 1, 1** | 32 | 134,217,727 | 134,217,727 | 1.13 s |
| 32, 65,535 / 65,536, 1 | 32 | 65,535 / 65,536 | same | 0.16 ms |
| 32, 1, 65,535 / 65,536 | 32 | 65,535 / 65,536 | same | 0.16 ms |
| 32, 4,194,304, 1 | 32 | 4,194,304 | 4,194,304 | 9.8 ms |
| 2048, 1, 1 | **2048, 1, 1** | **0** | 64 | invalid timestamps (end < start); fence ok; ~1 ms |

**For `cuDeviceGetAttribute`:** MAX_THREADS_PER_BLOCK = 1024; MAX_BLOCK_DIM_X/Y/Z = 1024 / 1024 / **1024** (more than
Metal's 64 for z); MAX_GRID_DIM_X up to 2^32 - 1 threads in total along x (4,194,303 blocks of 1024, or 2^31 - 1
blocks if reported as CUDA does, as long as threads fit 32 bits); y and z at least 65,535 blocks (65,536 and 4,194,304
tested). The runtime must reject local sizes over 1,024 itself: the hardware runs nothing and reports success.

## Caution from the first attempt

The first huge-grid runs pointed the output at a 64 KiB buffer and relied on soft faults to drop out-of-range stores.
Stores are only dropped where *nothing* is mapped: past the buffer they overwrote the counter, uniforms and CDM
stream of the same VM, giving over-counts, partial counts and invalid timestamps (one event recorded in the hang
budget). The final runs send every output store outside the VM.
