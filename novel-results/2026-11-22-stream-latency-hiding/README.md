# Sequential and gap-strided device-load streams hide DRAM latency; one core uses well over 256 KB of L2

Status: one device (driver-reported M2 Max G14C B1), direct DRM via `agx_run_hw` back to back, the kernels passed the
emulator gate first. Raw data: AGX-Performance-Simulator `results/2026-11-22-l2-prefetch/hw/`.

## Stream latency hiding (`scripts/probe_l2_share.py`, 8 SIMD groups per workgroup, one workgroup per core)

Each trip makes 4 coalesced loads (4 KB per core), then `wait`, then dependent fadds: one full memory latency per trip
unless the data arrives early.

| region per core, trip step | 1 core | 32 cores |
|---|---|---|
| 16 KB (L1/L2 resident), step 4 KB (round 5 log) | 314 us | 337 us |
| 2 MB contiguous, step 4 KB (round 5 log) | 418 us | 432 us (~590 GB/s, 64 MB footprint) |
| 2 MB, every other 4 KB chunk skipped (1 MB touched) | 369 us | 388 us |

185-216 ns per dependent trip is well below the ~400 ns DRAM/SLC latency. The memory system prefetches ascending
streams, including ones with 4 KB gaps. A next-line prefetcher model fits the contiguous case but not the gapped one.
A 16 KB-region model fits both, but on the simulator's real-program set it speeds up tile GEMMs that the hardware does
not speed up. So the trigger or the region is narrower than a 16 KB page. Not established: stride limits, descending
streams, and how many streams a core can track.

## Per-core L2 share

Round-4 stack probes on 1 workgroup (1 core): 256 KB/core 701 us, 512 KB ~510-620 us, 1 MB ~475 us (b2b 20; noisy).
A larger stack footprint is not slower on one core, so a single core's usable L2 is well above 256 KB. This is
consistent with the GPU-wide L2 of ~6.5 MB (2026-11-10-l2-gpu-capacity).
