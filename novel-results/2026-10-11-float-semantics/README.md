# Float semantics: fp32 flushes denormals before rounding, fma is fused, NaNs are canonical, fp16 is full IEEE

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Only known, round-tripping encodings were used; the inputs vary, not the encodings.

## Claim and scope

Over about 1,300 input triples per instruction (all pairs of 30 edge values: ±0, smallest and
largest subnormals, smallest normal, ±1 and neighbours, max finite, ±inf, quiet/signalling NaNs
with payloads, rounding ties; targeted denormal-boundary and fused-vs-unfused cases; 400 random and
near-cancelling triples), exactly one exact host model matches every lane:

| Instruction | Matching model |
| --- | --- |
| `fadd32`, `fmul32`, `fmadd32` | round to nearest even; **denormal inputs read as ±0**; a result whose **exact** value is below the smallest normal becomes ±0 (tininess before rounding) |
| `fmadd32` | **fused** (single rounding); unfused models fail on 20–28 triples |
| `fadd16`, `fmul16`, `fmadd16` | full IEEE binary16 round to nearest even, **denormals preserved** in and out; `fmadd16` fused |
| `.sat` (bit 6) on the fp32 ops | clamp to [0, 1] after the op; NaN → +0 |
| any NaN result | canonical quiet NaN: `0x7fc00000` (fp32), `0x7e00` (fp16); input payloads and NaN sign are dropped |

The before-rounding flush shows only where a result rounds up to the smallest normal:
`0x00ffffff × 0.5` and `2^-126 × (1 − 2^-24)` both give 0 on hardware, while rounding first would
give `0x00800000`. For fadd32 both flush timings agree because sums of flushed inputs are exact.

Update 2026-10-18: compare and min/max semantics, including the subnormal flush and NaN rules, are in the
[fcmp finding](../2026-10-18-fcmp/README.md).

Not established: other rounding modes (Mesa advertises none for ALU ops; `convert` has
its own rounding bit), fmin/fmax and compare NaN rules, transcendental accuracy, fp16 `.sat`,
mixed 16/32-bit operand forms, and source modifiers (`.neg`, `.abs`) beyond assembly round trips.

## Reproducer and evidence

`make test-float-semantics` (hardware), `make verify-float-semantics` (offline, 0 failures).
Runner: `scripts/run_drm_float.py`. [Evidence](../../results/2026-10-11-float-semantics/README.md).

## Relationship to existing knowledge

Mesa's Honeykrisp driver advertises fp32 flush-to-zero, fp16 denorm preserve, RTE only and
signed-zero/inf/NaN preserve (`hk_physical_device.c`), and `agx_nir_lower_fminmax.c` says "AGX
generally flushes FP32 denorms". Neither states input-vs-output flushing, the tininess point,
fma fusion, NaN canonicalisation or saturate NaN handling; those are measured here.

## Compiler implications (PTX)

* `add/mul/fma.rn.ftz.f32` map directly. **Non-`.ftz` `.f32` is not exact on this hardware**
  for denormal operands or results; exact emulation needs a software path (scale into the normal
  range or use integer ops). CUDA's default `-ftz=false` therefore needs a policy decision;
  `--use_fast_math` code is native.
* The FTZ result differs from NVIDIA's `.ftz` only at the min-normal rounding boundary
  (NVIDIA flushes after rounding). That is a 1-ulp-of-min-normal difference.
* `fma.rn.f32` is genuinely fused, so `fmaf` is exact; `mul`+`add` must not be contracted into
  `fmadd32` where PTX forbids it (`.rn` on mul/add).
* `.f16`/`.f16x2` arithmetic is IEEE-exact including denormals.
* PTX NaN results are canonical on NVIDIA too (0x7fffffff); only the bit pattern differs, which
  matters for bitwise comparisons of NaN outputs.
* `.sat` maps to bit 6, with NaN → 0 as PTX requires.
