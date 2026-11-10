# The L2 is one GPU-wide capacity of roughly 6-7 MB: per-core working sets of 256 KB slow down beyond ~24 busy cores, and the cores' stacks (6 MB apart) also alias

Status: confirmed on one device (M2 Max G14C), 2026-11-10. Our own PTX probes (hand-written, compiled by ZLUDA's zoc
for agx-g14c, captured with `ZLUDA_AGX_CAPTURE` from `agx_bench_kernel`) and our clang-built llama.cpp MMQ kernel,
replayed with `agx_run_hw --back-to-back 200`. Nothing disassembled or decompiled. This explains the open part of
[MMQ busy cores](../2026-11-10-mmq-busy-cores/README.md).

## Probes

`stackmix` (1072 B of stack per thread like MMQ Q5_K): a 1 KiB `.local` array filled once, then per trip three
lane-uniform stack loads of consecutive words and (st = 1) one stack store, words masked to `mask + 1` (footprint
per thread 4 x (mask + 1) bytes). One workgroup per core (gridDim <= 32, workgroups placed in chunks of 8 per
cluster). `stackrng`: the same, workgroups outside [lo, hi) return at once. `devmix`: the same pattern in device
memory with the scratch layout (word w of lane l at base + wg x stride + group x 48 KB + 128 w + 4 l).

## Result (us, firmware, median of 2 x 200 back to back)

| probe (per core) | 8 cores | 16 | 24 | 32 |
|---|---|---|---|---|
| stack 256 KB, 3 loads + store (A) | 737.6 | 743.0 | 1045.1 | 1183.6 |
| stack 256 KB, loads only (B) | 648.5 | 653.5 | 659.3 | 953.8 |
| stack 2 KB per group (C) | 742.2 | 745.8 | 753.3 | 760.1 |
| stack 128 KB, + store (E) | 737.2 | 742.8 | 749.4 | 866.5 |
| stack 128 KB, loads only (F) | 648.4 | 653.5 | 659.1 | 665.3 |
| stack 512 KB (16 groups), + store (G) | 540.5 | 824.7 | 1071.2 | 1545.4 |
| stack 512 KB (16 groups), loads only (H) | 475.4 | 655.1 | 819.7 | 1085.1 |
| stack 1 MB (32 groups), + store (D) | 472.9 | 827.7 | 1211.9 | 1586.2 |
| device twin, 6 MB between workgroups | 802.4 | 804.8 | 999.3 | 1238.3 |
| device twin, packed 384 KB apart | 802.7 | 804.8 | 807.0 | 1261.6 |
| stack A, scratch padded 2 MB between cores | | 742.9 | 748.8 | 1123.8 |
| stack A, padded 16 KB / 64 KB / 1 MB | | 743 | 800.5 / 911.9 / 1047.6 | 1162 / 1245 / 1263 |
| MMQ Q5_K pp512 (us; padding 0 / 16 KB / 1 MB) | | 1644 / 1629 / 1659 | | 2105 / 2083 / 2155 |

- It is the number of busy cores and their footprint, not a slow cluster: at grid 32 with only 8 workgroups working
  (any cluster: [0,8), [8,16), [16,24), [24,32)) 737 us; any 16 (0-15 or 16-31) 743; all 32: 1184.
- Two effects. (1) Capacity: total footprints of ~4-6 MB are free, ~8 MB costs 25-60% (packed twin at 32 cores,
  stack A at 32 even with padding, loads-only B at 32, G / H / D at 16+). Stores (dirty lines) make it worse than
  loads alone (E vs F at 32: +17% vs +2%). (2) Aliasing: the stacks of the cores lie 6 MB apart (Mesa's scratch
  layout, 128 slots x 48 KB per core), and at 24 cores such regions conflict: the strided twin slows (999) where
  the packed one does not (807), and 2 MB of padding between cores removes the step (1045 -> 749). Pads of 16 KB /
  64 KB / 1 MB help partly / less / not at all.
- MMQ Q5_K (274 KB of stack per core plus its tiles) does not change with padding: its slowdown from 16 to 32 cores
  is the capacity effect. The earlier [region streaming](../2026-11-10-l2-region-streaming/README.md) probe did
  not see it because sequential loads with 4 per wait are prefetched / bandwidth-bound; these probes have little
  memory-level parallelism (3 loads per wait), so each lost line costs an SLC round trip.
- The earlier "256 KB L2 per core" (2026-10-11 memory hierarchy) holds only while ~24 or fewer cores keep that much
  live; a full GPU has ~170 KB per core for a cyclic working set.

## Implications

- Compiler / runtime (ZLUDA AGX backend): spill-heavy kernels (MMQ: 1072-1376 B of stack per thread, ~1.6 M stack
  accesses per workgroup) lose 25-30% at full occupancy to L2 capacity; fewer spills (or spilling to threadgroup
  memory) is the lever, not the scratch layout. Padding the per-core scratch stride by ~2 MB removes the aliasing
  step for kernels near 24 busy cores (not worth it for MMQ).
- Simulator: AGX-Performance-Simulator `AGX_L2_GPU` (GPU-wide L2 capacity shared by the busy cores' working sets).

## Reproducer and evidence

PTX and job scripts with logs in [results](../../results/2026-11-10-l2-gpu-capacity/) (`300`: A-D, `310`: active
ranges and device twins, `315`: E-H, `320`: scratch padding and MMQ; `305`: rms_norm / soft_max grid sweeps, unrelated).
Padding used a local copy of `agx_runtime` with `AGX_SCRATCH_PAD` (extra bytes after each core's slots).
