# Stack (scratch) memory is interleaved across a SIMD group's lanes, and costs device-memory bandwidth

Status: confirmed on one device (M2 Max G14C), stack_load / stack_store emitted by the LLVM AGX backend for a
dynamically indexed `.local` array, launched through zluda_agx. Our own kernels, timed with firmware timestamps;
nothing was disassembled or decompiled.

## Claim

1. With every lane at the same stack offset, 2000 load-add-store iterations cost 384 us at 16 SIMD groups per core;
   with a different offset per lane, 1997 us (5.2x). Lanes at one offset therefore share memory rows: the stack is
   interleaved across the lanes of a SIMD group (a word at a time is the layout the simulator now assumes), not one
   contiguous region per lane.
2. Stack traffic scales with occupancy like device memory, not like registers: scattered offsets 450 us at 1 group
   per workgroup (38 x 32), 1997 us at 16 groups per core, 10079 us at 64 (304 x 256); lane-uniform 345 / 384 / 1362.
   A spill-heavy kernel is bandwidth-bound on its stack.

## Implications

- Compiler (AGX backend): spills and private arrays indexed by lane-varying values are expensive (up to 32 rows per
  access); keep spill offsets lane-uniform (they are, for register spills) and avoid dynamically indexed private
  arrays where a register or threadgroup layout works.
- Simulator: stack accesses go through the memory model with that layout (AGX-Performance-Simulator b61d0ed:
  errors -39..-93% -> -2..-42%).

## Reproducer and evidence

`results/2026-11-01-stack-memory/stack.ptx` and `stackuni.ptx`: `agx_bench_kernel K.ptx KERNEL --grid N --block T
buf:BYTES u32:2000` with `ZLUDA_AGX_CAPTURE`, then `agx_run_hw` on the capture with `--back-to-back 200 --stack 304`.
[Evidence](../../results/2026-11-01-stack-memory/hardware.txt).
