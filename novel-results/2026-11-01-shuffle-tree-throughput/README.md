# Shuffle-reduction trees: ~0.7 core cycles per shuffle-or-add at full occupancy; shared-memory values cost one round trip

Status: confirmed on one device (M2 Max G14C), our own kernels through ZLUDA's AIR route, back to back.

## Claim

A 5-step `shfl.sync.bfly` + `add.f32` tree (a SIMD-group sum), looped (shfltree.ptx, workgroups of 64 threads):

- One chain, few groups (38 workgroups): 66 ns an iteration, ~18 cycles a shuffle+add step: latency-bound.
- Eight independent chains, 32 groups a core (608 workgroups): 1243 ns an iteration for 32 x 80 shuffles and adds a
  core, ~0.68 core cycles each: shuffles and FP32 adds then share one throughput limit (the simulator's opt-in
  `AGX_SHFL_PIPE` 0.6 fits).
- Feeding the trees from shared memory (store, bar.sync, load, tree, bar.sync) adds one round trip, ~200 ns an
  iteration at 38 workgroups (tree1 66 -> 260, tree8 161 -> 658), not a cost per shuffle: FMAs and shuffles that read
  loaded threadgroup values directly do not wait again behind later ALU work.

## Implications

- Kernels ending in several independent SIMD-group reductions (one per output column) are shuffle/add-throughput
  bound at high occupancy: about 0.7 cycles a step per core, not one cycle per shuffle per group.
- AGX Performance Simulator: settle-on-read is now its default (its old deferral was +161% on tree8_tg).

## Reproducer and evidence

`results/2026-11-01-tg-reduction-tail/shfltree.ptx`; numbers in its [hardware.txt](../../results/2026-11-01-tg-reduction-tail/hardware.txt).
