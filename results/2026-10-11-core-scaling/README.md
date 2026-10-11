# Core-scaling evidence (2026-10-11)

Direct DRM, driver-reported M2 Max G14C B1. Produced by `scripts/scale_probes.py` (copy of the
AGX-Performance-Simulator probe). Each row: `op`, `chains`, `groups` (SIMD groups in the one workgroup per
core), `idle` (SR53 indices given no OP work), `core_cycles_per_step` (median over stable cores, reference
units), `mhz` (clock inferred from the reference), `stable_cores`, `spread` (min/max over cores), and `slots`
(SR17 of the groups, first cores).

| File | Contents |
| --- | --- |
| `grid.json` | 23 forms × chains 1, 8 × groups 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32 (32/128-step bodies, 500 trips) |
| `chains.json` | iadd_imm, fadd32_imm, fadd32, imadd, log2 × chains 2, 3, 4, 6 × groups 4–32 |
| `idle.json` | iadd_imm, 8 chains, groups 4–12 with chosen SR53 indices idle (scheduler-assignment test) |
| `slots.json` | SR17 slots per group (contiguous 0…G−1 within a workgroup) |

`make verify-core-scaling` checks the finding's claims against these files.
Discarded runs (not retained): 8/32-step bodies (loop overhead biases the slope; gave > 4 instructions per
cycle at 16 groups) and a first full grid whose non-power-of-two group counts selected the reference group
with a bit mask (fixed by SR53).
