# Each SIMD-group slot's first stack use in a command costs ~1.15 us, one slot at a time per core

Status: confirmed on one device (M2 Max G14C), 2026-11-07, with one real kernel (Rodinia bfs `Kernel2`, clang-built
CUDA through ZLUDA, 80 bytes of stack per thread) replayed by `agx_run_hw --stack 80 --back-to-back 1000` at other
grids and workgroup sizes. Nothing disassembled or decompiled.

## Claim and scope

| workgroups x threads | 1 x 32 | 1 x 128 | 1 x 256 | 1 x 512 | 38 x 512 | 244 x 512 | 977 x 512 | 1954 x 512 |
|---|---|---|---|---|---|---|---|---|
| us (firmware, warm) | 7.7 | 11.6 | 16.6 | 26.5 | 46.2 | 132.5 | 140.1 | 147.8 |

- In one workgroup each SIMD group beyond the first adds ~1.15 us: the groups' stack set-up is serial per core.
- With many workgroups the time grows until every resident slot of a core (6 workgroups x 16 groups = 96 here) has
  been used once (~110 us), then hardly at all (244 -> 1954 workgroups: +15 us for 8x the work). Later workgroups in
  an already used slot do not pay again within the command.
- Workgroups of one group (3800 x 32: 45.9 us) pay less than their resident slots would predict.
- A one-group stack kernel takes 7.7-8.9 us in all (bfs, gaussian Fan2), i.e. ~5 us of stack set-up over the
  2.3 us launch, less than an empty kernel launched with a stack (+8-11 us, [stack launch](../2026-11-01-stack-launch/README.md)).

## Measurement note

Kernels under ~40 us need >= 1000 back-to-back commands: at 300 the clock had not ramped (gaussian Fan1 35.2 vs
26.3 us, particlefilter sum_kernel 13.6 vs 6.8 us), see also
[short-kernel noise](../2026-11-01-short-kernel-b2b-noise/README.md). Launches inside the Rodinia programs (bursty)
take 2.6-3.0x their warm time for most kernels (clock ~500 MHz), 1x for a 10 ms kernel (heartwall).

## Compiler implications and limitations

Kernels that keep anything on the stack (clang -O0-style argument spills, private arrays) pay ~1.15 us per resident
SIMD group per command on top of the set-up: a 1M-thread bfs step went from ~20 us of work to ~148 us. Keeping
kernel arguments and small arrays in registers removes it. Synthetic stack probes faulted (Bad address) even with the
backend's first stack instruction, so only the captured kernel was varied; the mechanism (scratch allocation by the
helper program per slot is the guess) is not established. AGX Performance Simulator models it since 2026-11-07
(Rodinia warm set 29.5% -> 6.5% median with the threadgroup-load change).

## Reproducer and evidence

AGX-Performance-Simulator `results/2026-11-07-stack-slots/` (tables, capcheck outputs); the capture is
/scratch/sim-captures/rodinia/bfs (regenerate with ZLUDA_AGX_CAPTURE on Rodinia bfs built with clang).
