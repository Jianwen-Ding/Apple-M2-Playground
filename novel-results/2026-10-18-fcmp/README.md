# fp32 compares read subnormals as zero; `ltn`/`gtn` let a NaN operand lose; exact PTX setp / min / max are an integer fix-up

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Straight-line
programs, no loops, only encodings already recorded safe (`fcmpsel` with Mesa-named condition codes, integer ALU).
Every program was run in the Rust simulator before submitting. 0 faults.

## What was measured

`fcmpsel CC` (D = A CC B ? 1 : 0) for all seven condition names (eq, lt, gt, ltn, gte, lte, gtn) over all 48 x 48 = 2,304
pairs of edge values: +-0, subnormals (smallest 0x1 to largest 0x7fffff), the smallest normals, values near 1 and 2, max
finite, +-inf and eight NaNs (quiet, signalling, payloads, both signs). Three runs per condition, identical every time.
(`fcmpsel` has no negation field; the assembler refuses `neq` and the other negated names.)

| Condition | Hardware result (matches all 2,304 pairs exactly) |
| --- | --- |
| eq, lt, gt, gte, lte | **subnormal operands are read as +-0** before the compare; any NaN operand gives false |
| ltn, gtn | the same as lt / gt (including the subnormal flush), except **true when only the second operand is NaN** ("a NaN loses": the first operand wins a min/max selection) |

* Against an IEEE compare (subnormals exact) the hardware differs on **189 of 2,304 pairs** for lt, gt, gte, lte and on
  **378** for eq; every difference has a subnormal operand (checked), and there is none without one.
* The simulator already implemented exactly this (`fsem::fcond`); the Rust replay of all seven conditions now matches
  the hardware on every result word (`make verify-fcmp`).

## Consequence for PTX (default, non-`.ftz`)

* `setp.{eq,lt,gt,le,ge}.f32` and `min/max.f32` without `.ftz` are **not** a single AGX compare. Native `fcmpsel` is wrong
  on subnormal operands; Mesa's compare-and-select min / max (`fcmpsel ltn` / `gtn`) is wrong on **190 of 2,304 pairs**
  each (subnormal ordering and the sign of zero). `.ftz` forms map directly.
* **Exact fix-up (integer compare), verified on hardware:** per operand x: `m = x & 0x7fffffff`;
  `key = x ^ (asr(x, 31) | 0x80000000)` (a monotonic unsigned key; -inf .. +inf); `key = (m == 0) ? 0x80000000 : key`
  (so -0 == +0); `nan = m > 0x7f800000`. Then `setp.lt = !nan(a) && !nan(b) && ka < kb`; `gt` swaps the keys; `le` / `ge`
  also accept `ka == kb`; `eq` is `ka == kb`; NaN gives false. About 15 instructions for one compare (12 for the two keys,
  3 for the select and NaN mask), 4 constant moves hoisted (counted from the program, not timed).
* **`min` / `max`:** use the raw key (no zero fix, so -0 < +0) to select an operand's bits, then let a NaN operand lose
  (both NaN gives a NaN). Exact on all 2,304 pairs; denormals and the sign of zero are preserved because no arithmetic
  is done. About 16 instructions.
* All seven operations were exact on all 2,304 pairs in all 3 hardware runs, and the same programs equal an independent
  host model of PTX semantics in the simulator.

Not established: `setp` with the NaN-accepting variants (`.equ`, `.ltu`, ...: they follow from the same keys by inverting
the NaN mask, not run here), `set` with a float result, fp16 compares (denormals are preserved by the fp16 ops), the
cost of the fix-up, and whether a compiler can skip it when it proves an operand is normal or the product of an
`.ftz` op.

## Reproduce

`scripts/run_drm_fcmp.py hardware` (compare record), `scripts/run_drm_fcmp_fixup.py offline|hardware` (fix-up),
`make verify-fcmp` (offline: 32 checks against [results/2026-10-18-fcmp](../../results/2026-10-18-fcmp), including the
simulator replay; needs `agx_run` built).
