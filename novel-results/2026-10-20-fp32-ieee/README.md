# Exact IEEE fp32 on AGX: non-`.ftz` add/mul/fma and `.rz/.rm/.rp`, bit-exact on hardware, with costs

Status: one device (driver-reported M2 Max G14C B1), direct DRM, straight-line integer code plus Mesa's structured `if`
form, simulator-gated before every hardware run. 0 faults, hang budget unused.

## Why

The fp32 unit always flushes: subnormal operands read as ±0, and an exact result below 2^-126 becomes ±0 before
rounding ([float semantics](../2026-10-11-float-semantics/README.md)). It only rounds to nearest even. PTX's default
`add/sub/mul/fma.f32` (no `.ftz`, which is what nvcc emits unless `-ftz=true` / `--use_fast_math`) must preserve
subnormals. `.rz/.rm/.rp` must round in that direction. The [conversions finding](../2026-10-16-conversions/README.md)
recorded "exact non-`.ftz` needs a software path". This finding builds and measures that path.

## What was built (`scripts/softfp32.py`)

- **`ffma32(P, a, b, c, mode)`**: branch-free binary32 fused multiply-add from 32-bit integer ops (the
  [soft-fp64](../2026-10-18-fp64/README.md) DSL). It covers subnormal inputs and outputs, the four rounding modes,
  overflow to inf or max-finite per mode, the IEEE signs of exact-zero sums (`-0` in `.rm`), inf/NaN rules, and the
  canonical NaN `0x7fc00000` (the unit's own). About 337 instructions, registers up to r48.
  `add = ffma32(a, 1.0, b)`, `mul = ffma32(a, b, -0.0)`.
- **`needs_ieee(P, a, b, c, r)`**: 14 integer ops that flag lanes where the native `fmadd32` result `r` may be wrong.
  A lane is flagged when an operand is subnormal (`|x| - 1 < 0x7fffff` unsigned), or when `r` is ±0 while neither factor
  is zero (the flush case). Zero factors with a normal `c` are not flagged.
- **Hybrid lowering** for the PTX default `.rn` forms: `fmadd32`, then `needs_ieee`, then
  `if_icmp ... nueq ...; jmp_exec_none; <ffma32>; pop_exec`. SIMD groups with no flagged lane skip the soft path.

## Exactness (hardware)

Dataset: the 30 × 30 × 10 edge cube (signed zeros, smallest/largest subnormals, min normal and neighbours, 1 and
neighbours, max finite, inf, NaN, binade edges), plus 12,000 random triples biased to the subnormal boundary, a third of
them with near-cancelling addends. 21,024 lanes in all. The reference is exact rational arithmetic (`ref_fma32`).

| Program | Result |
|---|---|
| `ffma32` `.rn` / `.rz` / `.rm` / `.rp` | **21,024 / 21,024 bit-exact in every mode**, 3 runs each, identical to the simulator |
| hybrid (native + check + soft under `if`) | **21,024 / 21,024 bit-exact**, 3 runs, identical to the simulator |
| native `fmadd32` alone | agrees with the reference on all 5,668 normal-domain lanes, an independent check of the reference. It differs from IEEE on 5,813 lanes, every one with a subnormal operand or an exact result in (0, 2^-126). That includes 4 lanes where IEEE rounds up to 2^-126 and the unit flushes to 0 |
| `needs_ieee` | flags every lane where the native result is wrong (no false negatives) |

## Cost (dependent chains `x = fma(x, b, c)`, 131,072 lanes, firmware time)

The clock is held at its top state by `scripts/clock_keeper.py`. Slopes use K = 16 → 32, and K = 1024 → 2048 for the
native op. A first sweep without the keeper ran at mixed clock states, about 2-3× slower in absolute terms, with ratios
of the same order. Both sweeps are retained.

| Lowering | Instructions per step | µs per step (clock held) | vs native | first sweep (clock not held) |
|---|---|---|---|---|
| native `fmadd32` | 1 | 0.06 | 1 | 0.17 |
| hybrid, all-normal data (no group takes the soft path) | 18 (fma + 14 check + if/jmp/pop) | 1.0 | ≈ 15 | 2.6 |
| soft `ffma32` alone | ≈ 337 | 12.8 | ≈ 200 | 36.5 |
| hybrid, one subnormal lane in every SIMD group | 18 + 337 | 15.5 | ≈ 240 | 40.8 |
| hybrid, every lane subnormal | 18 + 337 | 14.4 | ≈ 225 | 41.5 |

One subnormal lane costs a SIMD group as much as 32 of them: the soft path runs once per group.

## Follow-up: what the fast path actually costs, and a 1.75× faster layout

A 9-op check (`CHECK9`) flags exactly the same lanes as the 14-op `needs_ieee` on all dataset lanes. For each operand it
computes `t = 2|x| - 1` with one shifted-source `iadd t, M1, x, lsl 1`. A subnormal gives t < 0xfffffe and zero gives
0xffffffff. Two `min`s, one `max` and a zero test on r follow, and the final selects fold into the `if_icmp`.

The cheaper check did **not** speed anything up. Decomposing the fast path (clock held, µs per dependent step, 131,072
lanes; native `fmadd32` = 0.055):

| Variant (fma + ...) | µs |
|---|---|
| CHECK9, no control flow | 0.41 |
| `if_icmp` + `pop_exec`, no jump | 0.24 |
| `if_icmp` + **untaken** `jmp_exec_none` + 1-op block + `pop_exec` | 0.30 |
| `if_icmp` + **taken** `jmp_exec_none` over a 1-op block + `pop_exec` | **1.05** |
| full if-skip hybrid, and the same with the 337-op soft block replaced by a 1-op stub | 1.72, 1.53 |

**A taken `jmp_exec_none` costs about 0.75 µs per step more than an untaken one, ≈ 14 native fma.** That is roughly 10
issue cycles per SIMD group at 1,398 MHz, and other groups cannot hide it at full occupancy. The skipped code size does
not matter: the stub costs the same. The usual structured-`if` layout, which Mesa also uses, pays this exactly in the
common case, because the jump is taken when no lane needs the fix. (Compare the ~38-cycle taken loop iteration in the
[loop finding](../2026-10-10-agx-loop-alu-timing/README.md).)

**Out-of-line layout (`hybrid3`).** `if_icmp`, then a `jmp_exec_any` to a block after the main body (taken only when some
lane is flagged), then the soft path and a `jmp_exec_any` back, then `pop_exec`. The common case falls through an untaken
jump. Result: **0.98 µs per step against 1.72 µs for the if-skip layout (1.75×)**. It is bit-exact on the 21,024-lane
dataset (3 runs, identical to the simulator) and under one subnormal lane per group.

**Constant-condition probes** (the branch direction does not depend on data). Each step is fma, then `if_icmp`, then
`jmp_exec_none` over one instruction, then `pop_exec`. Cycles per SIMD group per step at full occupancy (131,072 lanes,
1,398 MHz):

| Probe | hardware | simulator before | simulator after (2026-10-20 rule) |
|---|---|---|---|
| jump taken (no lane passes) | 11.48 | 3.13 | 11.38 |
| jump not taken (block runs) | 3.78 | 3.40 | 3.40 |
| out-of-line form (untaken `jmp_exec_any`) | 3.43 | 2.60 | 2.60 |

The simulator charged its taken-branch penalty only to backward `jmp_exec_any` (loop trips), and as a per-group latency
that other groups hide. `AGX-Performance-Simulator/rust/src/cost.rs` now gives a **taken forward jump** (`jmp_exec_none`,
or a forward `jmp_exec_any`) the loop-fitted latency plus a **33-cycle scheduler hold** (`branch_forward_sched_real`),
fitted to these probes. The change leaves `make verify-cost-model` output byte-identical. It also leaves `suite-check`
(721/721) and `coverage-check` (the same 5 known timing rows) unchanged, so no calibrated workload had a taken forward jump.

**Single group:** one SIMD group running these 40 KB straight-line probes costs about 124 cycles per untaken step and
about 350 per taken step. That is instruction-fetch-bound: no sibling groups share the fetched lines, and a taken jump
breaks sequential fetch for about 226 cycles. Do not use single-group long-code timings for branch costs.

Compiler rule for AGX: put rarely taken blocks out of line so the common path never takes a branch. This applies to
every IEEE fix-up here and to other guard-style code (bounds checks, NaN fix-ups, slow atomics).

## Compiler implications (ZLUDA)

- **`.ftz` forms and fast-math kernels map 1:1** onto `fadd32/fmul32/fmadd32`.
- **Exact default forms cost ≈ 15× on subnormal-free data** (clock held), because the check, not the soft path, dominates. Ways to
  cut this:
  - Skip the check for operands provably normal or zero (constants, already-checked values).
  - Specialize: `mul` has `c = -0`, so its check covers only a, b and r; `add` has `b = 1`.
  - Hoist checks of warp-uniform operands.
  - Offer a ZLUDA option that treats non-`.ftz` as `.ftz`. That breaks bit-exactness only when subnormals actually occur.
- **Directed rounding** (`add/mul/fma.rz/.rm/.rp.f32`, `__fadd_rz`, etc.) has no hardware form and costs about 215×.
  It is rare in CUDA code.
- `div.rn.f32`: see the [fdiv32 finding](../2026-10-20-fdiv32/README.md). Not covered: `sqrt.rn` / `rcp.rn` non-ftz, `.sat` with
  directed modes, `f16` (the fp16 unit is already full IEEE with RNE), and lowering the check to fewer instructions.

## Reproduce

`python3 -B scripts/run_drm_softfp32.py offline|hardware --op soft|hw|hybrid [--round rn|rz|rm|rp]` (exactness);
cost: `--data normal|sparse|dense --lanes 131072 --chain K --check 512`. Offline: `make verify-fp32-ieee`
(21 checks against [results/2026-10-20-fp32-ieee](../../results/2026-10-20-fp32-ieee)).
