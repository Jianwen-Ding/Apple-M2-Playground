# A kernel with a stack costs ~7.5 us more per command

Status: confirmed on one device (M2 Max G14C), commands as agx_runtime submits them (`agx_run_hw --back-to-back 500`,
the empty kernel of 2026-11-01-zluda-launch-cost); our own kernel; nothing disassembled or decompiled.

## Claim

The same empty kernel launched with a per-thread stack (`--stack 64`: the launch sets up scratch memory through its
helper program, as zluda_agx does for kernels that use stack_load / stack_store) costs per command:
38 workgroups 2.9 -> 10.0 us, 3,610 workgroups 11.3 -> 19.5 us, 15,200 workgroups 41.6 -> 44.6 us. The cost is a
fixed ~7-8 us per command, almost nothing per workgroup.

## Implications

- A short kernel that spills or keeps a dynamically indexed private array pays more for its stack's setup than for
  its launch: avoiding the stack in such kernels (registers, threadgroup memory) saves ~7.5 us per launch, besides the
  stack traffic itself ([stack memory](../2026-11-01-stack-memory/README.md)). llama.cpp's mul_mat_vec_f kernels use
  64-80 bytes of stack on the AIR route.
- The simulator's zluda profile adds it (`agx_dispatch --stack`).

## Reproducer and evidence

`agx_run_hw code.bin --grid N*32 --wg 32 --regs 8 [--stack 64] --back-to-back 500` with the empty kernel.
[Evidence](../../results/2026-11-01-stack-launch/hardware.txt).
