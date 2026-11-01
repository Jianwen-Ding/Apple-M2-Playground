# GPU-wide read throughput is ~340-380 GB/s also for data that fits the system-level cache

Status: confirmed on one device (M2 Max G14C), our own kernels, commands as zluda_agx submits them.

## Claim

A kernel that reads 16 bytes per thread and writes nothing reads 8 MiB in 24.5 us (342 GB/s) and 32 MiB in 88.7 us
(378 GB/s), back to back (the 8 MiB were read by the previous command and fit the ~21 MiB system-level cache; the
32 MiB do not). A copy moves 365 and 362 GB/s (reads plus writes) at the same sizes. Reads, like writes
([store bandwidth](../2026-11-01-store-bandwidth/README.md)), do not get faster when the data is in the
system-level cache: the GPU-wide path, not DRAM, sets ~350 GB/s.

Size sweep, back to back (GB/s after the 2.3 us launch): 0.25 MiB 134, 1 MiB 268, 2 MiB 317, 4 MiB 371, 6 MiB 372,
8 MiB 382, 12 MiB 385. No size at which the previous command's data becomes cache-fast (small sizes are launch- and
ramp-bound). Inside one dispatch, by contrast, all cores re-reading a 1-16 MiB window reach 1.1-1.9 TB/s (AGX
Performance Simulator results/2026-10-11-memory-hierarchy/stream.json): the limit applies to the first touch in a
command, not to the cache.

## Implications

- Streaming kernels (FFT passes, copies, element-wise library kernels) cost bytes / ~350 GB/s whatever their size;
  keeping data in the cache saves nothing for them, only fewer passes over it does.
- The AGX Performance Simulator takes resident data as 2-3x faster (results/2026-11-01-fft-shared-captures there).

## Reproducer and evidence

`results/2026-11-01-read-bandwidth/readx.ptx`, `copyx.ptx`: `agx_bench_kernel readx.ptx c --grid G --block 256 buf:B
buf:B` (G = 2048 or 8192, B = 16 G 256) with `ZLUDA_AGX_CAPTURE`, then `agx_run_hw --back-to-back 1000` on the
capture. [Evidence](../../results/2026-11-01-read-bandwidth/hardware.txt).
