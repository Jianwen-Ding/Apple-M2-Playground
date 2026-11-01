# Ten independent FMA accumulator chains run at ~5 cycles per FMA per SIMD group (correction of a first claim)

Status: confirmed on one device (M2 Max G14C), our own kernels, commands as zluda_agx submits them.

**Correction.** This entry first claimed that threadgroup loads feeding FMAs issue every ~4 cycles. That was wrong:
the AGX backend hoists the kernel's threadgroup loads out of the loop (their addresses do not change; the simulator's
instruction profile shows each executed once), so the loop measured is ten FMAs into ten accumulators, each the
next step of its own chain. Nothing here measures threadgroup loads.

## Claim

`tg10.ptx`'s loop, as compiled: per iteration 10 `fmadd32`, each into its own accumulator (operands: a value loaded
before the loop and a constant), 500 iterations. 21.7 us per command with one SIMD group per core, 25.4 with two,
26.5 with four (38 workgroups). One group: ~26k cycles for 5000 FMAs, ~5.2 cycles per FMA. `tg2.ptx` (2 chains):
17.8 us with four groups.

## Implications

- The simulator charges each of these FMAs ~21 units (84.4 us for tg10, whatever the groups): its rule that only the
  last 8 written registers are fast and older values wait a ~17-cycle writeback
  ([result cache](../2026-10-11-result-cache/README.md)) does not hold for ten chains each reading its own
  accumulator one iteration later. GEMM inner loops with many accumulators (Geekbench's gemm_block_size_bias, +43%)
  are likely affected the same way. To be resolved against the result-cache measurements before changing the model.

## Reproducer and evidence

`results/2026-11-01-fma-accumulator-chains/tg10.ptx`, `tg2.ptx`: `agx_bench_kernel tg10.ptx tg10 --grid 38 --block
B buf:19456 u32:500 f32:1.0001` with `ZLUDA_AGX_CAPTURE`, then `agx_run_hw --back-to-back 1000` on the capture.
[Evidence](../../results/2026-11-01-fma-accumulator-chains/hardware.txt).
