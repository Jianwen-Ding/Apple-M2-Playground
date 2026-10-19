# fp64 div / sqrt / rcp / cvt, all rounding modes (2026-10-19)

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power.
Extends the [fp64 add/mul/fma work](../2026-10-18-fp64/README.md) with the remaining arithmetic:
correctly-rounded division, square root, reciprocal, float<->float and float<->int conversions,
all in PTX rounding modes (`.rn .rz .rm .rp` where PTX defines them). Same method: branch-free
integer code (`iadd`/`isub`/`imadd`, `and`/`or`/`xor`, `extr`, `ffs`, `icmpsel`, `mov_imm`),
each program run in the Rust simulator before hardware. 0 faults.

## What was built (`scripts/softfp64.py`)

* `fdiv64` — restoring division, 55 quotient bits + sticky, ~1085 instructions. The one subtle
  point: the first 52 iterations provably produce zero (remainder < divisor throughout), so the
  integer bit is computed directly and only 54 fraction iterations run.
* `fsqrt64` — binary digit recurrence over **pairs** (two input bits per one root bit, trial
  divisor `(Q << 2) | 1`), 55 iterations, ~1498 instructions. An earlier single-bit-per-iteration
  draft silently stalled on remainders (it can never set low quotient bits); the pair form carries
  the proven invariant `X = Q^2 + R` with `R < 2Q + 1` and is verified bit-exact, including the
  odd-exponent path (53-bit vs 54-bit working mantissa selected by the exponent LSB).
* `frcp64` — `1/x` through the divider (2 extra moves).
* Conversions: `cvt_f32_f64` (exact widening), `cvt_f64_f32` (all 4 modes, subnormal-aware rounding
  with the guard bit re-derived after the subnormal shift), `cvt_s32/u32_f64` (exact),
  `cvt_f64_s32/u32` (all 4 modes, x86-like saturation: NaN -> INT_MIN / 0, overflow clamps;
  PTX leaves some of this undefined, so the choice is documented, not claimed as PTX-exact).

Two implementation traps worth recording: (1) the disassembled `0x7fefffff` constant was
mistyped `0x7ffefffff` (9 hex digits) in one place — caught by a one-ulp directed-rounding
mismatch, not by review; (2) the new `round_pack` for f32 used OR instead of ADD to merge the
hidden bit, dropping the carry exactly when `(e-1)` is odd — same symptom class (single-bit
errors on directed modes only).

## Correctness

| op | modes | hardware lanes x runs | result |
|---|---|---|---|
| `div.rn/rz/rm/rp.f64` | all 4 | 2624 x 3 | 0 differ from exact rationals |
| `sqrt.rn/rz/rm/rp.f64` | all 4 | 224 x 3 | 0 differ |
| `rcp.rn/rz/rm/rp.f64` | all 4 | 224 x 3 | 0 differ |
| `cvt` x 15 forms | as listed | 256 x 3 | 0 differ |

Edge coverage: all 48 x 48 edge pairs (NaN/inf/zeros/subnormals/max/near-1), exact ties
(`(2^53+1)/2^53`, `(2^53+3)/2^53`), over/underflow boundaries, subnormal quotients and results,
negative sqrt, directed-mode corners, plus 800/200 random operands per op (30% uniform bit
patterns) and exact-halfway cases. References are exact (`Fraction`), not host floats, so
directed modes and ties are checked, not just RN.

## Cost (131,072 lanes, chained K = 1/4/8, keeper on, slope of medians)

| operation | instructions | time per op per 131,072 lanes | vs native fp32 fma |
|---|---|---|---|
| `div.rn.f64` | 1085 | ~46.6 us | ~710x |
| `sqrt.rn.f64` | 1498 | ~67.8 us | ~1000x |
| `cvt.rn.f32.f64` (widening) | 56 | 23.6 us (chain 1), 31 us (chain 8) | — |
| `cvt.rn.f64.f32` | 97 | 23.7 us (chain 1), 38 us (chain 8) | — |
| `cvt.rn.f64.s32` | 110 | 22.6 us (chain 1), 39 us (chain 8) | — |

The conversion chains repeat the same conversion of the same input (the output type differs, so
it cannot be fed back), so their slope is not a per-operation cost. The `cvt.f64.s32` chain-4 point
(59 us) is an outlier against chain 8 (39 us); the conversions are measured at chain 1 and 8 only.
Their instruction counts are 26-113 per form, and their time is dominated by the fixed dispatch
cost at this lane count, not the arithmetic.

Throughput ratios use the 0.5 ps native-fmadd baseline from the earlier finding and carry the
same ~+-15% run-to-run spread. A double-precision divide costs on the order of a thousand
native fmas; conversions are two orders of magnitude cheaper than arithmetic.

## For PTX / ZLUDA

* `div.rn/rz/rm/rp.f64`, `sqrt.rn/rz/rm/rp.f64`, `rcp.*.f64`, `cvt.f64.f32` (widening, exact),
  `cvt.rn/rz/rm/rp.f32.f64`, `cvt.rn.f64.s32` and `cvt.rn.f64.u32` (exact), and
  `cvt.rn/rz/rm/rp.s32.f64` / `cvt.rn/rz/rm/rp.u32.f64` can be lowered to these sequences today and are
  exact on the cases above (modulo the documented int-saturation assumption).
* Still open: transcendentals (`sin`/`cos`/`exp`/`log` in double); double-precision
  library calls would need non-uniform control flow (see the call/ret finding).

## Reproduce

`scripts/run_drm_softfp64.py offline|hardware --op div|sqrt|rcp [--round MODE] [--random N]`;
`scripts/run_drm_cvt.py offline|hardware --op OP [--random N]`; `make verify-fp64-divsqrt`
(offline: retained records, fresh interpreter checks, simulator replay with `agx_run` built;
`--no-sim` skips the replay). Records: [results/2026-10-19-fp64-divsqrt](../../results/2026-10-19-fp64-divsqrt).
