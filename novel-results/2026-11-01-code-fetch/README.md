# Every command fetches its code cold: ~104 ns per 64-byte line of straight-line code

Status: confirmed on one device (M2 Max G14C), commands back to back as zluda_agx submits them; our own kernels.

## Claim

A single thread running N straight-line fma (four independent chains, so the ALU is not the limit) costs, per
command: 102 B of code 3.7 us, 294 B 2.8 us, 1062 B 4.2 us, 4134 B 9.0 us. From 294 to 4134 bytes that is +6.25 us
for 60 more lines, ~104 ns per 64-byte line (~0.6 GB/s for one SIMD group): the instruction cache does not keep a
kernel's code from one command to the next (consistent with the command boundary's cache invalidation,
[2026-10-16 L2 command boundary](../2026-10-16-l2-command-boundary/README.md)), and the fetch is not prefetched far
ahead of straight-line execution. Loops hide it: a kernel's later iterations and waves hit the cached lines, and many
groups' work overlaps the fetch (llama.cpp's 138-line Q8_0 kernel shows no extra cost).

## Implications

- Short kernels with long straight-line code (unrolled, inlined helpers) pay ~0.1 us per 64 bytes per launch: for a
  4 KB kernel that is more than its launch cost. Smaller code (less unrolling and inlining) helps such kernels.
- The simulator's zluda launch profile models it (AGX-Performance-Simulator, fetch_line_ns).

## Reproducer and evidence

`results/2026-11-01-code-fetch/line*.ptx`: `agx_bench_kernel lineN.ptx lineN --grid 1 --block 1 buf:64 f32:1.0001
f32:0.5` with `ZLUDA_AGX_CAPTURE`, then `agx_run_hw --back-to-back 1000` on the capture.
[Evidence](../../results/2026-11-01-code-fetch/hardware.txt).
