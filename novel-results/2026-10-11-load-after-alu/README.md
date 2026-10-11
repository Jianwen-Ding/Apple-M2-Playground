# Device loads are slower after ALU work, and ALU work in flight defers them

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, one SIMD group, warm L1
(the same word every repetition). Known-safe encodings only; reference units (× 1.049 = real cycles).

## Claim and scope

A `device_load` + `wait 0` costs **44.8 units (47 real cycles)** when no ALU instruction has issued in that
SIMD group since the previous `wait`, and **~63 units (66 real cycles)** when one has, whatever the ALU
instruction (`iadd`, `fadd16`, `mov_imm`, `get_sr`), whether or not it produces the load's address, and however
far before the load it issued (0–24 instructions) or whether its result was evicted from the result cache.

| Body per repetition | units |
| --- | --- |
| load, wait | 44.8 |
| load → load (index produced by the first load), each with its wait | 89.6 (= 2 × 44.8) |
| iadd, load, wait | 63.9 |
| fadd16 / mov_imm / get_sr, load, wait | 63.8 / 60.1 / 67.6 |
| load, iadd, wait (ALU while the load is in flight) | 44.8 |
| load, wait, iadd (the iadd precedes the next load) | 61.6 |
| store, load, wait | 52.9 |

ALU instructions issued **while the load is pending** are free for the first ~8, then push completion out:
with a = ALU instructions before the load and b after it (30-point grid, `load-alu-grid.json`), completion
is at least ~31 units (a = 0) or ~56 units (a ≥ 1) after the last ALU instruction issued before the wait.

| a \\ b | 0 | 4 | 8 | 16 | 24 | 32 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 44.8 | 45.8 | 46.1 | 53.8 | 62.2 | 69.1 |
| 1 | 63.8 | 65.7 | 69.2 | 77.1 | 84.6 | 92.4 |
| 4 | 67.6 | 71.5 | 73.9 | 80.6 | 88.8 | 95.9 |
| 8 | 75.5 | 75.8 | 76.8 | 84.6 | 92.0 | 100.7 |

Interpretation (not proven): the group's memory request is not dispatched while the group keeps issuing ALU
instructions, and a load following ALU work pays an extra ~18 units of pipeline transition.

This resolves the discrepancy with the [load-latency finding](../2026-10-10-agx-load-latency/README.md): its
pointer chase alternates load and wait with no ALU work between, so it measured the fast case (36 ns at
1,398 MHz, ~50 cycles including 1/16 of the loop); a CPU writer on the buffer (tested) and the declared register
count (16–128 halves, tested) do not matter.

Not established: several SIMD groups, other memory types, misses beyond L1, stores in detail, and whether a
non-ALU instruction (control flow, `wait` on another slot) resets the fast state.

## Reproducer and evidence

`results/2026-10-11-cost-model/load-alu-grid.json` (grid), `memory.json`; reproduce with
`python3 scripts/cost_probes.py loadgrid` (grid) and `memory`. The rule is part of `scripts/agx_cost.py`.

## Compiler implications

* Issue a group's loads back to back before ALU work, and put ALU work between the loads and their `wait`
  only up to ~8 instructions; a load after ALU work costs ~19 extra cycles.
* Pointer chasing and gather loops pay ~66 cycles per load in practice (address arithmetic precedes each load),
  not the ~50 of a pure chase.
