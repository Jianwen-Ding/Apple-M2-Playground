# fp32 exp2 and sin_pt_2 algorithms, and AGX transcendentals against PTX's accuracy rules

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute.
- Every kernel was straight-line (load, the instruction or Mesa's instruction sequence, store), using forms the
  coverage suite had already recorded safely. No faults or timeouts.
- About 1.2 G results were recorded: all 2^23 mantissas of 76 exp2, 60 sin_pt_2 and 9 new log2 binades, plus 2 M
  sin / cos sequence results.

## Claims

1. **exp2 reads x as Q.23 fixed point, truncated, with a ones'-complement negative.** For every finite fp32 x:

   ```
   t = trunc(|x| * 2^23)
   q = (x < 0 && t != 0) ? ~t : t           // ~t, not -t: exact multiples of 2^-23 come out one unit low
   exp2(x) = 2^(q >> 23) * 1.G[q mod 2^23]  // +inf if the exponent reaches 128, +0 below the normal range
   ```

   - G is one 2^23-entry mantissa table, the [1,2) recording itself.
   - This matches **all 637,534,208 inputs of 76 binades from -2^127 to 2^127**, both signs.
   - Consequences: x is used with only 23 fraction bits, so every |x| < 2^-23 returns exactly 1.0, and
     exp2(-1.0) = 0x3efffffe (0.49999988) while exp2(1.0) = 2.0.
2. **sin_pt_2 reads |x| as Q.23 fixed point, truncated, and looks it up in one table.**
   - sin_pt_2(x) = H[trunc(|x| * 2^23)] for |x| < 1, 1.0 at |x| = 1, and the canonical NaN beyond.
   - The ~218 M positive inputs fill all 2^23 entries of H with 0 conflicts. The negative inputs read the same entry:
     the function is even, with no ones' complement.
   - H never rounds up: it is 0, 1 or 2 ulp below the correctly rounded sin(pi x / 2) / x.
3. **log2's fixed-point model holds on the full range.** The simulator's e + F(m) model, truncated, matches every
   input of 9 new binades from 2^-126 to 2^127.
4. **Against PTX** (`.approx.f32`, normal inputs and results). The figures are exhaustive over the recorded or
   modelled inputs.

   | PTX instruction | PTX bound | AGX | Verdict |
   |---|---|---|---|
   | `rcp.approx` | 1 ulp | 0.750 ulp | within |
   | `rsqrt.approx` | rel 2^-22.9 | rel 2^-23.41 | within |
   | `ex2.approx` | 2 ulp from correctly rounded | 2 ulp (2.315 ulp from exact; worst for negative x) | exactly at the bound |
   | `lg2.approx` | abs 2^-22 on (0.5, 2), rel 2^-22 elsewhere | abs 2^-22.05, rel 2^-22.22 | within, barely |
   | `sin.approx` | abs 2^-20.5 on [-2pi, 2pi] | Mesa's sequence 2^-21.11 | within |
   | `cos.approx` | abs 2^-20.4 on [-2pi, 2pi] | **Mesa's sequence 2^-20.29** at x = 5.0188923 | **exceeds** |

   - **Mesa's cosine fails PTX** on the GPU itself, not only in a model. The cause is its range reduction:
     `turns = x * (float)(1/2pi)`, then `+ 0.25`, each rounded to fp32.
   - **Fix for ZLUDA:** split the constant and use one fma, `turns = fma(x, C_hi, x * C_lo)` with
     C_hi = (float)(1/2pi) and C_lo = (float)(1/2pi - C_hi). This costs one extra fmul. Measured on the GPU:
     **cos 2^-20.70, sin 2^-21.53**, both within PTX.
   - Subnormals: AGX fp32 transcendentals flush denormal inputs and results (the simulator's established rule). So
     only the `.ftz` forms map 1:1. The default PTX forms need a scaling fix-up when an input or result is
     subnormal.

## Method

`scripts/record_trans_ranges.py` in AGX-Performance-Simulator records all 2^23 mantissas of a binade (each 2^18-lane
chunk runs twice and must agree). `scripts/record_sincos_chain.py` runs Mesa's exact sin / cos instruction sequence
(`fmul32`, `fadd32`, `floor`, `sin_pt_1`, `sin_pt_2`), or the fma variant, on chosen inputs.

The sin / cos accuracy over all fp32 inputs in [-2pi, 2pi] comes from a float32 replica. The replica reproduced the
GPU's words on all 2,097,152 hardware-run inputs, including a dense window around each worst case.

The raw recordings stay in scratch and can be regenerated. The simulator now uses these models: test suite
721 / 721 exact, and SPIR-V verify 164 PASS, with the remaining CLOSE workloads differing only by atomic order.

## Reproduce

```sh
make verify-transcendentals   # offline: models and PTX comparisons against the retained hardware words
```

Evidence: [results/2026-10-16-transcendentals](../../results/2026-10-16-transcendentals/). `hw_samples.json.gz` holds
1,026 inputs per binade and 32,768 per sin / cos variant. `exp2_G.bin.gz` and `sin_pt_2_H.bin.gz` are the tables.
PTX bounds are from the PTX ISA (sections 9.7.3.13-9.7.3.21).
