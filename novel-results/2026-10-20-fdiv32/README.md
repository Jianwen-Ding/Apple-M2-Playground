# IEEE `div.rn.f32` on AGX: Newton-refined `rcp` is correctly rounded for every mantissa, so a 6-instruction Markstein sequence is exact in range; hybrid bit-exact everywhere

Status: one device (driver-reported M2 Max G14C B1), direct DRM, simulator-gated, 0 faults, hang budget unused.
This follows the [fp32 IEEE fma finding](../2026-10-20-fp32-ieee/README.md). CUDA's `/` on `float` compiles to `div.rn.f32`
unless fast math is enabled, and it must be correctly rounded. AGX has only an approximate `rcp`, and Mesa lowers division
as `a * rcp(b)`.

## Result 1: exhaustive proof for the reciprocal (offline, from the recorded hardware `rcp` table)

`y0 = rcp(b)` is **not** correctly rounded on 1,619,725 of 8,388,607 mantissas (19%; it is within 0.75 ulp). One Newton step
with the fused unit, `e = fma(-b, y0, 1)` (exact) then `y1 = fma(e, y0, y0)`, gives **y1 = RN(1/b) on all 8,388,607
non-trivial mantissas**. This was computed in exact integer arithmetic from the simulator repo's per-mantissa hardware
`rcp` table, and the result scales exactly by exponent.

By Markstein's theorem, with y1 = RN(1/b) and q0 = RN(a·y1) within 1 ulp, `r = fma(-b, q0, a)` (exact) and
`q1 = fma(r, y1, q0)` give **RN(a/b) for every a**, provided no intermediate leaves the normal range.

## Result 2: hardware

Datasets:
- **edge**, 22,912 lanes: 30 × 30 edge pairs, 20,000 exponent-biased random pairs, and 2,000 near-1 quotients whose
  divisor mantissas are all-ones or all-zeros.
- **fast**, 131,072 lanes: random operands inside the fast domain, the same mantissa bias included.

| Lowering | Instructions | Edge set | In-domain set |
|---|---|---|---|
| Mesa `a * rcp(b)` | 2 | 9,912 wrong | 21,434 misrounded (16%), max **1.82 ulp** from exact: within PTX's 2-ulp `div.approx` / `div.full` bound on this sample |
| fast: `rcp`, 2 fma (y1), `fmul`, 2 fma, zero-sign fix | 6 + 2 int | wrong only outside `div_fast_ok` | **131,072 / 131,072 bit-exact** |
| soft `fdiv32` (restoring, 26 quotient bits + sticky) `.rn/.rz/.rm/.rp` | ≈ 279 | **22,912 / 22,912 bit-exact in every mode** | — |
| **hybrid**: `div_fast_ok ? fast : soft` (soft under `if` / `jmp_exec_none`) | ≈ 315 | **22,912 / 22,912 bit-exact** | — |

`div_fast_ok` (10 integer ops) accepts the following and sends everything else to the soft path:
- b normal with biased exponent ≤ 252, so `rcp(b)` is not flushed;
- a = ±0, or a normal with biased exponent ≥ 48, so the remainder `r` is neither inexact nor flushed;
- an estimated quotient exponent `ea - eb + 127` in [2, 252].

Everything else means subnormals, inf/NaN, near-overflow, near-underflow and very small numerators. A zero numerator
stays on the fast path; one integer select fixes the sign of 0/b, which the fma sequence gets wrong for -0/+b.

## Cost (dependent chains `x = x / b`, 131,072 lanes, clock held by `clock_keeper.py`)

| Lowering | µs per division | vs Mesa |
|---|---|---|
| Mesa `a * rcp(b)` | 0.14 | 1 |
| fast sequence only | 0.58 | ≈ 4 |
| **hybrid, all-normal data** | **1.43** | **≈ 10** |
| soft alone | 9.5 | ≈ 70 |
| hybrid, one subnormal numerator per SIMD group | 11.2 | ≈ 80 |

A first sweep without the keeper is retained. It was about 2× slower with the same ordering.

## Compiler implications (ZLUDA)

- `div.approx.f32` / `div.full.f32` (and `__fdividef`): Mesa's `a * rcp(b)` measured ≤ 1.82 ulp in range. Subnormal and
  extreme ranges need the `.ftz` semantics checked separately.
- `div.rn.f32` (default `/`): use the hybrid. If a kernel's operands are known to be in range (for example `.ftz` with
  normal data), the fast sequence alone is exact for 6 FP ops. `div.rz/.rm/.rp.f32`: the soft divider.
- The hybrid's fast path costs about 2.5× the bare sequence because of the range check and branch. Specializing
  constant divisors (y1 precomputed once) removes the reciprocal steps.

## Not established

`rcp.rn.f32` / `sqrt.rn.f32` (`sqrt` has its own refinement and needs the `rsqrt` table proof), `div.full.f32`
over its full range, and the cost of a constant-divisor specialization.

## Reproduce

`python3 -B scripts/run_drm_fdiv32.py offline|hardware --op soft|fast|hybrid|mesa [--round MODE] [--data edge|fast|normal|sparse] [--chain K]`.
Offline: `make verify-fdiv32` (13 checks, including the 8.4M-mantissa reciprocal proof; it needs the simulator repo's
`testsuite/transcendental/rcp.bin.gz`). Evidence: [results/2026-10-20-fdiv32](../../results/2026-10-20-fdiv32).
