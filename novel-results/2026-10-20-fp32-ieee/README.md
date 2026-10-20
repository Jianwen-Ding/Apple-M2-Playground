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

## Cost (dependent chains `x = fma(x, b, c)`, 131,072 lanes, firmware time, slope over K)

| Lowering | Instructions per step | µs per step | vs native |
|---|---|---|---|
| native `fmadd32` (K = 1 → 2048) | 1 | 0.17 | 1 |
| hybrid, all-normal data (no group takes the soft path) | 18 (fma + 14 check + if/jmp/pop) | 2.6 | ≈ 15 |
| soft `ffma32` alone | ≈ 337 | 36.5 | ≈ 215 |
| hybrid, one subnormal lane in every SIMD group | 18 + 337 | 40.8 | ≈ 240 |
| hybrid, every lane subnormal | 18 + 337 | 41.5 | ≈ 245 |

One subnormal lane costs a SIMD group as much as 32 of them: the soft path runs once per group.

## Compiler implications (ZLUDA)

- **`.ftz` forms and fast-math kernels map 1:1** onto `fadd32/fmul32/fmadd32`.
- **Exact default forms cost ≈ 15× on subnormal-free data**, because the check, not the soft path, dominates. Ways to
  cut this:
  - Skip the check for operands provably normal or zero (constants, already-checked values).
  - Specialize: `mul` has `c = -0`, so its check covers only a, b and r; `add` has `b = 1`.
  - Hoist checks of warp-uniform operands.
  - Offer a ZLUDA option that treats non-`.ftz` as `.ftz`. That breaks bit-exactness only when subnormals actually occur.
- **Directed rounding** (`add/mul/fma.rz/.rm/.rp.f32`, `__fadd_rz`, etc.) has no hardware form and costs about 215×.
  It is rare in CUDA code.
- Not covered: `div.rn` / `sqrt.rn` / `rcp.rn` non-ftz (they build on fma but need their own fix-ups), `.sat` with
  directed modes, `f16` (the fp16 unit is already full IEEE with RNE), and lowering the check to fewer instructions.

## Reproduce

`python3 -B scripts/run_drm_softfp32.py offline|hardware --op soft|hw|hybrid [--round rn|rz|rm|rp]` (exactness);
cost: `--data normal|sparse|dense --lanes 131072 --chain K --check 512`. Offline: `make verify-fp32-ieee`
(13 checks against [results/2026-10-20-fp32-ieee](../../results/2026-10-20-fp32-ieee)).
