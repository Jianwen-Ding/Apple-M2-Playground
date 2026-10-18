# Bit 52 of fmadd32 is a `pow()` special-case fixup: `D = fixup(C; A, B)`

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage, AC power. Resolves the last open question of the
[fmadd lane-offset finding](../2026-10-11-fmadd-lane-offset/README.md), whose rule was fitted on 31 triples and is wrong on 6,062 of the 13,824 below.
Straight-line program, only the exact bit pattern that ran cleanly before (`fmadd32` 8-byte form, bit 52, no other gap bit). 0 faults.

## Test

`fmadd32_b52 r14, r6, r7, r8` over (a) all 24^3 = 13,824 triples of 24 special values (+-0, the smallest and largest subnormals, the smallest normal,
+-0.5, +-1, +-2, +-3.5, 1.5, +-max, +-inf, three NaNs), and (b) 1,024 triples with integers and near-integers as B (+-3, 5, 4, -4, 7, -7, 2^23 + 1 (odd),
2^23 + 2, 2^24, 2^24 + 2, 1.0000001, 0.99999994, +-2.5, 3.0000002), signs and specials as A, and four values of C. Three identical hardware runs each.
(`scripts/run_drm_fma_b52.py`; the program was gated in the simulator with the plain fmadd32, since the model did not run bit 52 at that time.)

## Rule (fits all 14,848 hardware results, 0 exceptions)

C is a provisional value (a `pow` computed as exp2(B * log2(A)) by the compiler's sequence); the instruction replaces it where the C99 `pow(A, B)` special
cases apply. Denormal operands read as +-0.

| Condition (first match) | Result |
| --- | --- |
| B is +-0 or denormal | **1.0** (even for NaN A, NaN C) |
| A is exactly +1.0 | **1.0** (even for NaN B) |
| B is NaN | C |
| A is NaN | C, except: A with its sign bit set and B finite non-integer -> the canonical NaN 0x7fc00000 |
| B = +1.0 (denormal-flushed) | **A** (a denormal A gives +-0) |
| A = -1.0 and B = +-inf | **1.0** |
| A negative (sign bit set, non-NaN), not zero / denormal / infinity, B finite non-integer | **canonical NaN** |
| A negative (including -0, denormals, -inf) and B an **odd integer** (not +-inf; any |B| >= 2^24 is even) | **-C** (a NaN C gives the canonical NaN) |
| everything else | **C** (a denormal C reads as a signed zero; a NaN C is returned bit for bit, signalling NaNs included) |

* The odd / even integer test is exact at the 2^23 / 2^24 boundary: 2^23 + 1 is odd (-C), 2^24 + 2 even (C), 2^24 + 1 rounds to 2^24 (even).
* A has no effect when B is zero, and A = +1 wins over everything but B = +-0: the order of the table is the order of the hardware's priorities.
* This is exactly the post-processing a `powf` needs after `exp2(B * log2(|A|))`: zero exponent, base 1, exponent 1, negative base with non-integer
  exponent, sign of a negative base with an odd integer exponent, `pow(-1, +-inf)`, NaN propagation.

## For PTX / ZLUDA

CUDA `powf` / `pow` is not a PTX instruction; the NVVM libdevice implementation computes `exp2(y * log2(x))` and fixes up the special cases in
software. On this GPU one `fmadd32` with bit 52 replaces that fix-up sequence: `t = exp2(B * log2(|A|))` (the ex2 / lg2 approximation sequences
from the transcendental findings), then `fmadd32_b52 D, A, B, t`. Not measured here: the accuracy of such a `powf` against libdevice, `.sat`, `.abs` /
`.neg` source modifiers and the 16-bit forms with bit 52 (the simulator refuses them rather than guess).

## Simulator

`isa/compiled.rs` `pow_fixup` implements the table (`fmadd32_b52`); a unit test covers each row. It reproduces every hardware word of the 14,848 triples
above, of the two new coverage cases (`fmadd_b52/specials24`, `fmadd_b52/integers`, recorded twice on the GPU, deterministic, in `coverage/expected`) and
of the 98 historical bit-52 programs of 2026-10-11 (`make verify-fmadd-lane` now matches 391 retained records instead of 293).

Not established: the bit-52 form together with the 10-byte lane form (bit 53) and with other gap bits, source modifiers, saturation, 16-bit sources.

## Reproduce

`scripts/run_drm_fma_b52.py offline|hardware [--set 2]`; `make verify-fma-b52` (offline, 7 checks against
[results/2026-10-18-fma-b52](../../results/2026-10-18-fma-b52); needs `suite_check` / `agx_run` built, `--no-sim` skips the simulator checks).
