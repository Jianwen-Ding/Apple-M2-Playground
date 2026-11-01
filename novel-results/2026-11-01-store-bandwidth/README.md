# GPU-wide store bandwidth ~365 GB/s, also for writes that fit the system-level cache

Status: confirmed on one device (M2 Max G14C), commands back to back as zluda_agx submits them; our own kernels.

## Claim

1520 workgroups of 256 threads, each thread storing 1, 4 or 16 words (1.5, 6, 24 MB in all), cost 9.9, 22.0 and
72.1 us per command: the workgroups' launch (~4 us, 100 ns per workgroup per core), then the bytes at ~365 GB/s, then
the ~2.3 us fixed cost. Writes small enough for the 48 MB system-level cache are not absorbed faster: their bandwidth is
the same as that of writes four times as large. A kernel that writes anything at all costs ~0.7 us more than an
empty one (3.0 against 2.3 us).

With thousands of workgroups per core the launch and the stores overlap instead: Geekbench's gradient (9,672
workgroups per core, ~967 us of launch, ~500 us of stores at 365 GB/s) takes 1036 us. The cost is the stores'
time plus the launch up to that long (`store + min(launch, store)`), which covers both cases.

## Implications

- Write traffic is a throughput cost whatever its size: a kernel writing N bytes takes at least N / 365 GB/s after
  its launch.
- The simulator's zluda profile floors a dispatch at its workgroups' launch plus its writes at 365 GB/s
  (AGX-Performance-Simulator `store_gbps`).

## Reproducer and evidence

`results/2026-11-01-store-bandwidth/st.ptx`, `stn*.ptx`: `agx_bench_kernel stnN.ptx stnN --grid 1520 --block 256
buf:BYTES` with `ZLUDA_AGX_CAPTURE`, then `agx_run_hw --back-to-back 1000` on the capture.
[Evidence](../../results/2026-11-01-store-bandwidth/hardware.txt).
