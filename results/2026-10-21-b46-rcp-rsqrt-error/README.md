# B46: worst-case error of `rcp` and `rsqrt` (2026-10-21)

Blocker B46 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM, battery power. 0 faults;
hang budget unchanged.

**Result: rcp is within 0.7496 ulp (relative 2^-23.42) and rsqrt / rsqrt_special within 0.8177 ulp (relative 2^-23.42)
of the exact value, over every fp32 significand and independent of the exponent.** That is about 9 bits inside the
backend's 2^-19.7 requirement for the software f64 division / square-root seed, and well inside "a few ulp" for
AGXStrictFP's float division. The results are **not** correctly rounded: 19.3 % of rcp and 19.8 % of rsqrt results are
1 ulp away from the correctly rounded value (almost always one ulp above it). The simulator already applies these
measured tables (`rust/src/transtab.rs`), not the correctly rounded value as B46's text assumed.

## Exhaustive part (offline, from tables recorded on this GPU)

`b46_offline.py` reads the simulator's `testsuite/transcendental/{rcp,rsqrt,rsqrt_special}.bin.gz` (hardware result
minus the correctly rounded result for every mantissa: rcp on [1, 2), rsqrt on [1, 4), recorded by
`record_transcendentals.py`) and measures each result against the exact value (the maximum confirmed with exact
rational / 60-digit arithmetic). `offline.json`:

| Op | Inputs | Max error | At x | Max relative error | Off correctly rounded (-1 / +1 ulp) |
| --- | --- | --- | --- | --- | --- |
| rcp | 8,388,608 | 0.7496 ulp | 0x3fdfa046 | 8.92e-8 = 2^-23.418 | 19,587 / 1,600,138 |
| rsqrt | 16,777,216 | 0.8177 ulp | 0x3f89f038 | 8.94e-8 = 2^-23.415 | 4 / 3,323,271 |
| rsqrt_special | 16,777,216 | identical to rsqrt | | | |

## Exponents and denormals (GPU, `b46_gpu.py`)

1,024 random mantissas of every normal binade (both signs for rcp) and 65,536 positive denormals, compared with the
table result scaled by the exponent (`gpu.json`):

- **Normal inputs with normal results: 516,097 (rcp) and 260,098 (rsqrt) inputs, 0 mismatches.** The error is the
  same in every binade, so the [1, 2) / [1, 4) figures are the maxima over the whole normal range.
- **Denormal inputs are flushed:** every positive denormal gives +inf for both ops (as +0 does); -0 gives -inf.
- **Results below the normal range are flushed:** rcp of |x| >= 2^126 (exponents 253, 254) gives a signed zero;
  rcp(FLT_MAX) = 0, rcp(2^-126) = 2^125.

The non-`.ftz` PTX forms therefore still need the scaling fix-up for denormal inputs and results (as the
transcendentals finding of 2026-10-16 says); the `.ftz` forms map 1:1.
