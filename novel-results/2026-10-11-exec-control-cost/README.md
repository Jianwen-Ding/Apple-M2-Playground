# Exec-stack instructions chain through r0l and count as ALU work for `wait` and memory

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, one SIMD group. Reference units
(1 unit = 1.049 cycles). Only the exact `push_exec` / `pop_exec` encodings of the loop skeleton were run.

Found while looking for a spacer that separates ALU work from a device store without being ALU work or a `wait`.
The cost model had never measured control instructions: it priced them at an assumed 1 cycle, with no
dependency and no effect on memory or `wait`.

## Claims

| body per repetition (× 8) | measured | old model | new model |
| --- | --- | --- | --- |
| `push_exec`, `pop_exec` | 3.7 | 1.9 | 3.7 |
| 16 × (`push_exec`, `pop_exec`) | 61.5 | 30.5 | 60.9 |
| `push_exec`, `iadd`, `pop_exec`, `iadd` | 3.8 | 4.0 | 4.0 |
| 4 pairs, `wait` | 34.2 | 8.6 | 32.2 |
| `iadd`, 4 pairs, `wait` | 36.3 | 19.0 | 33.3 |
| `iadd`, k pairs, device load, `wait` (k = 0 / 1 / 2 / 4 / 8) | 63.8 / 66.6 / 71.5 / 82.2 / 97.9 | 64.9 flat | 64.9 / 67.9 / 71.7 / 79.3 / 94.6 |
| `iadd`, k pairs, device store (k = 0 / 1 / 2 / 4 / 8) | 35.8 / 38.6 / 42.3 / 52.8 / 70.0 | 36.7 flat | 36.7 / 39.7 / 43.5 / 51.1 / 66.4 |

1. **Dependency through the nesting counter.** Back-to-back `push_exec` / `pop_exec` cost 1.9 units each,
   which is the control latency of 2 cycles. Interleaving one independent `iadd` hides it entirely. Both
   instructions read and write r0l, and the model had dropped r0l from their sources.
2. **They count as ALU work.** A `wait` after them drains about 17 units past their completion, like after ALU
   work ([wait-drain finding](../2026-10-11-wait-drain/README.md)). Loads and stores after them wait out the
   memory quiet time measured from the last control instruction, not from the last `iadd`
   ([load-after-ALU finding](../2026-10-11-load-after-alu/README.md)).

So exec-stack instructions are not a usable non-ALU spacer for the store-window question; that stays open.

Not established: other control instructions (`if_icmp`, `while_icmp`, `else_*`, `jmp_exec_*`) in isolation;
divergent exec masks; several SIMD groups.

## Reproducer and evidence

`results/2026-10-11-cost-model/ctlspacer.json`; checked by `scripts/verify_cost_model.py` (13 cases, max 8.4%).

## Compiler implications

* Short `if` regions are not free: each `push_exec` / `pop_exec` pair with nothing between costs ~3.7 units,
  and a `wait` or memory instruction right after one pays the drain or quiet time as if ALU work preceded it.
* Put independent ALU work between a push and its pop when possible; it hides the r0l chain.
