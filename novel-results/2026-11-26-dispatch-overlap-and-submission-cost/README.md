# Launches without a barrier overlap (0.55 us each); 0x160 orders for 3.15 us; submissions pipeline to ~45 us

Status: measured on one device (M2 Max G14C B1, 38 cores, AC power), direct DRM through metal-cpp/asahi
(libmetal_asahi of 2026-11-26, `bench/bench dispatch`); own kernels compiled from AIR by the in-tree AGX backend;
nothing disassembled or decompiled. GPU times are the compute commands' firmware timestamps.

## Claims

1. **Within one CDM control stream, launches with no barrier word between them overlap.** An empty 32-thread
   kernel launched 256 or 1024 times costs 0.52-0.58 us of GPU time per launch with no barrier, 3.86-3.91 us with
   `3 << 29 | 0xff7ff` after each launch, and 3.13-3.18 us with Mesa's base set `0x160`. (The 2026-11-10
   [barrier-bits](../2026-11-10-cdm-barrier-bits/README.md) entry saw no difference for an empty kernel with any
   mask. Its 2.6-3 us per dispatch came from a CUDA graph through ZLUDA, a different launch path.)
2. **`0x160` orders launches and makes their writes visible on other cores.** 64 ping-pong launches per stream,
   152 threadgroups of 256 threads, each thread reading an element another threadgroup wrote in the launch before
   (`out[i] = in[(i + 28693) % n] + 1`): exact in 20 of 20 runs of 8 streams. With `0x7f`, the first element was 249
   instead of 512 (metal-cpp/asahi `tests/commands.cpp` `serial_dispatches_see_other_cores_writes`).
3. **One submission's round trip is ~110-150 us; most of it is the wait.** For an empty 1-launch compute command,
   `DRM_IOCTL_ASAHI_SUBMIT` takes ~30 us and the syncobj wait ~100 us. The wait is bimodal: about every other
   submission waits ~530-570 us when the GPU was idle between them.
4. **Submissions on one queue pipeline.** With 8 command buffers in flight (each one submission of one empty
   launch, no in-syncs, the queue's FIFO order relied on), the cost is 41-62 us per submission instead of 188 us
   one at a time. Depth 16 is no faster than 8 (45-55 us).

## Implications

- Encoders that may overlap (Metal's `MTLDispatchTypeConcurrent`) should emit no barrier between launches. Serial
  ones need only `0x160` between launches; keep the full `0xfffff` at the end of a stream.
- A runtime should keep several submissions in flight and retire them in order, not wait on each one. Per-token
  inference loops that commit many small command buffers gain about 4x in launch overhead.

## Related: SIMD-group matrices reach 69 % of FP32 peak from device memory

An SGEMM in which each SIMD group keeps 4x4 8x8 `simd_matrix_fmadd32` accumulators (32x32 of C) and loads its
A and B 8x8 tiles straight from device memory (no threadgroup staging) runs at 9.4 TFLOP/s at 2048^3 (7.8 at
1024^3, 7.3 at 4096^3), against a 13.6 TFLOP/s FMA peak. The best scalar register-blocked kernel reaches 2.6
(metal-cpp/asahi `kernels/bench.cl` `sgemm_simd`, `sgemm_reg4x4`).
