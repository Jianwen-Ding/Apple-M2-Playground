# fp32 rcp, rsqrt, exp2 and log2 return one NaN, 0x7fc00000

Status: confirmed on one device (driver-reported M2 Max G14C), direct DRM, compute. Straight-line kernels (load, the
instruction, store), 40 lanes each, no faults.

## Claim

Every NaN result of `rcp`, `rsqrt`, `exp2` and `log2` is `0x7fc00000`: for NaN inputs of several payloads and both
signs (`0x7fffffff`, `0x7f800001`, `0xffc00000`, `0xffffffff`, ...), and for the inputs where the function is
undefined (`rsqrt` and `log2` of negatives and of -inf). Input payloads and signs are dropped, as the fp32 ALU
operations do ([float semantics](../2026-10-11-float-semantics/README.md): fadd32 / fmul32 / fmadd32 give
`0x7fc00000` for any NaN).

Other results seen on the way (not the claim): `rcp(-0)` and `rcp` of a negative subnormal give -inf (the operand
read as -0), `rcp(-inf)` gives -0; `rsqrt` / `log2` of -0 and of a negative subnormal give -inf; `exp2(-inf)` is +0,
`exp2(-0)` and of a subnormal 1.0, `exp2(-1)` 0x3efffffe.

## Compiler implication (PTX)

A canonical NaN (PTX: `0x7fffffff`) for a result of these instructions is one comparison with `0x7fc00000`
(`select(x == 0x7fc00000, 0x7fffffff, x)`), not a test of the exponent and fraction.

## Reproducer and evidence

`scripts/run_drm_special_nan.py hardware --result FILE` (`offline` runs the simulator, which agrees).
[Evidence](../../results/2026-10-31-special-nan/hardware.json).
