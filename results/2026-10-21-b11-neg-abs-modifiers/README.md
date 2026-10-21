# B11: what the `.neg` / `.abs` source modifiers do to NaNs, denormals and zeros (2026-10-21)

Open item of blocker B11 (`AGX-Performance-Simulator/tasks/ptx-re-blockers.md`), also the "source modifiers beyond
assembly round trips" left open by `novel-results/2026-10-11-float-semantics`. M2 Max (G14C), direct DRM, battery
power, six recorded-safe forms, 0 faults; hang budget unchanged. Hardware = simulator on every lane (`gpu.json`,
`sim.json`).

**Result: the modifiers are part of the arithmetic, not a bit operation.** With `fadd32 x.neg, -0.0`,
`fadd32 x.abs, -0.0`, `fmul32 x.neg, 1.0`, `fmul32 x.abs, 1.0` (24 fp32 inputs) and `fadd16 x.neg, -0.0`,
`fadd16 x.abs, -0.0` (22 fp16 inputs), every result matches "apply the sign change, then the op's usual rules":

| Input | fp32 result | fp16 result |
| --- | --- | --- |
| normal, inf, +-0 | sign flipped / cleared, exact | the same |
| denormal | **flushed to a zero with the new sign** (0x00000001 .neg -> 0x80000000, .abs -> 0x00000000) | **preserved**, sign flipped / cleared |
| any NaN (quiet, signalling, either sign, any payload) | **0x7fc00000** (payload and sign lost, even for .abs of -NaN) | **0x7e00** |

So the bit model (sign bit only) holds on 12-13 of 24 fp32 inputs and 15-16 of 22 fp16 inputs; the arithmetic model
holds on all of them.

**For the backend and ZLUDA:**
- PTX `neg.f32` / `abs.f32` (no `.ftz`) and LLVM `fneg` / `fabs` must keep NaN payloads and denormals, so they need
  integer `xor 0x80000000` / `and 0x7fffffff` (as the strict-IEEE mode already does). Folding them into a float op's
  source modifier is only correct where that op would canonicalize / flush anyway, i.e. for `.ftz` code or when the
  value feeds a float op.
- `neg.ftz.f32` / `abs.ftz.f32` match the modifier forms except for NaN payloads (always canonical here).
- For f16, a modifier is exact except for NaNs (canonical 0x7e00).

The other B11 items are answered by existing findings: `fmadd32` is fused, one rounding
(`novel-results/2026-10-11-float-semantics`); fp32 compares read denormals as +-0, so `-0x007fffff < +0x00400000` is
false and both equal 0.0, and `min.ftz` follows from `fcmpsel`, while exact non-ftz min / max / setp need the published
integer-key fix-up (`2026-10-18-fcmp`, `2026-10-19-setp-extra`); `rcp` / `rsqrt` worst errors are in
`results/2026-10-21-b46-rcp-rsqrt-error`; `a * rcp(b)` is within 1.82 ulp and the exact div / sqrt sequences are in
`2026-10-20-fdiv32` and `2026-10-20-fsqrt32`.

Probe: `b11.py sim|gpu`; each lane loads its input with `device_load`, runs one form and stores the raw word.
