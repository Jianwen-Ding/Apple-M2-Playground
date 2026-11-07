# A threadgroup load holds its SIMD group ~28 cycles, and one after ALU work issues only after a ~21-cycle quiet time

Status: confirmed on one device (M2 Max G14C, AC power), 2026-11-07; our own hand-assembled loops (threadgroup_load,
iadd, fmadd32, wait, loop control) through agx_run_hw, back to back, firmware times. 66 loop shapes x group counts,
one held-out set of 24. Nothing was disassembled or decompiled.

## Claim and scope

Loops of 8 threadgroup loads per trip (per-lane word addresses, 8 base registers, no bank conflicts) with ALU
instructions in between, 32 workgroups (one per core) of 1-32 SIMD groups, slope between 2048 and 6144 trips, core
cycles at 1398 MHz (an ALU reference loop measures the model's 45.8 cycles, so the GPU ran at the top clock):

| per trip | 1 group | 8 | 32 |
|---|---|---|---|
| 8 loads | 261 | 261 | 293 |
| load, iadd, load, iadd, ... (8 each) | 402 | 403 | 416 |
| 2 loads, 2 iadd, x4 | 326 | 329 | 355 |
| 4 loads, 4 iadd, x2 | 288 | 293 | 329 |
| 8 loads, 8 iadd | 269 | 273 | 306 |
| load, wait 0, x8 | 261 | 261 | 292 |
| 8 xy loads | 271 | 283 | 592 |
| 8 loads with an immediate base (all lanes word 0) | 224 | | |

1. A threadgroup load holds its group's issue for ~28 cycles with a register base, ~24 with an immediate base: an
   independent iadd after it waits until then (load + iadd pairs cost 50 cycles, not 29).
2. A threadgroup load after ALU work issues ~21 cycles after the last ALU instruction, so every run of ALU
   instructions between loads costs ~20 cycles whatever its length (1, 2, 3, 7 iadd or fmadd32 alike):
   trip = loads x 28 + runs x 21 + ALU instructions. This is the load-after-ALU quiet time of
   [2026-10-11-load-after-alu](../2026-10-11-load-after-alu/README.md), but here it stalls the group, not only the result.
3. A wait right after a threadgroup load is free: the result arrives within the hold.
4. Per core: x loads ~0.87 per cycle at 32 groups (barely slower than 1 group); xy loads ~2.3 cycles each at 32 groups.

Not tested: threadgroup stores, bank conflicts with ALU interleaving, the G13 family.

## Relationship to existing knowledge

Explains the 50-70% cost of ALU instructions between threadgroup loads in
[Geekbench gemm probes](https://github.com/Jianwen-Ding/AGX-Performance-Simulator/blob/main/novel-results/2026-10-23-geekbench-captures/README.md) and
corrects its "2.2x slower at 32 groups per core": those runs used 38 workgroups of 1024 threads, and the cluster split
puts two of them on four cores (64 groups), which the firmware time follows; with 32 workgroups 32 groups per core run
at nearly the 1-group rate. The in-shader 31.4 cycles per load of `mem_probes.py` agree (8 loads then a wait).

## Compiler implications and limitations

Group threadgroup loads into runs and put the ALU work that uses them after the run (the hardware pays one quiet time
per ALU run, not per instruction): an inner loop of `ld.shared; fma; ld.shared; fma` costs ~50 cycles per pair per
group, the same loads issued together then the FMAs ~28 per load + ~21 once. Immediate threadgroup addresses are
~4 cycles cheaper per load than register bases. The AGX Performance Simulator models 1-3 since 2026-11-07
(held-out median error 31% -> 1.8%).

## Reproducer and evidence

AGX-Performance-Simulator `scripts/probe_tg_alu.py [hw|sim|both] PATTERN...` (env NG, T1, T2, B2B, ADDR); kernels
must start with `iadd r0l, 0, 0` before exec-stack instructions under agx_run_hw (without it push/pop_exec faulted,
Bad address, 5 recorded faults). Raw rows: [results](../../results/2026-11-07-tg-load-issue-hold/).
Caveat: 100 commands of 256-768 trips (< 0.3 ms each) landed in two clock states (261 vs 201 cycles for one loop);
use >= 1 ms kernels.
