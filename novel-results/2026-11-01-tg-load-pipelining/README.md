# Independent threadgroup loads, each feeding an FMA, issue every ~4 cycles per SIMD group

Status: confirmed on one device (M2 Max G14C), our own kernels, commands as zluda_agx submits them.

## Claim

A loop of 10 threadgroup loads per iteration (consecutive lanes, no bank conflicts), each feeding an FMA into its own
accumulator, 500 iterations: 21.7 us per command with one SIMD group per core, 25.4 with two, 26.5 with four. One
group issues a load + FMA pair every ~5 cycles (~4 per load); four groups share the core's threadgroup memory at
~1.6 cycles per load. This is much faster than the ~21-31 cycles per access measured for dependent or
wait-separated threadgroup accesses ([2026-10-11 shared memory](../2026-10-11-shared-memory-sync/README.md)): the
issue interval of a group's threadgroup loads depends on what lies between them.

## Implications

- GEMM-style inner loops that stream operands from threadgroup memory into FMAs run near the core's threadgroup
  bandwidth, not at one access per ~21 cycles per group.
- The simulator's single tg_load_issue (21 units) overstates them (Geekbench's gemm_block_size_bias +43%); a global
  value of 4 breaks the calibrated cases where 21 holds, so the model needs a rule that tells the patterns apart.

## Reproducer and evidence

`results/2026-11-01-tg-load-pipelining/tg10.ptx`, `tg2.ptx`: `agx_bench_kernel tg10.ptx tg10 --grid 38 --block B
buf:19456 u32:500 f32:1.0001` with `ZLUDA_AGX_CAPTURE`, then `agx_run_hw --back-to-back 1000` on the capture.
[Evidence](../../results/2026-11-01-tg-load-pipelining/hardware.txt).
