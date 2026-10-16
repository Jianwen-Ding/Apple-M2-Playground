# Cross-lane reductions and scans: 16-bit and 64-bit sources, and the SIMD scan network

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute. Offline analysis of hardware
words recorded on 2026-10-12. No new encodings were run.

## Claim

For `simd_*` / `quad_*` reductions (`and or xor iadd fadd fmul min.u max.u min.s max.s min.f max.f`) and
`simd_prefix_*` / `quad_prefix_*` exclusive scans:

1. **A 16-bit source combines at 16 bits.** Integers wrap at 2^16. `fadd` / `fmul` are fp16, rounded at every step,
   with **fp16 denormals kept** (fp32 forms flush them). `min.f` / `max.f` compare fp16. The destination's other half
   is untouched. Identities are the 16-bit ones (e.g. `fmul` 0x3c00, `max.s` 0x8000).
2. **A 64-bit source (`r6_r7`) is read as its low 32 bits only.** `simd_min.u r14, r6_r7` is the minimum of the low
   words, `simd_iadd` the 32-bit sum, and so on. r7 never matters, and nothing is written to r15. There is **no
   native 64-bit warp reduction**. A genuine 64-bit model misses 11,957 words over the 20 integer cases.
3. **Combining order.** Reductions are a pairwise tree, and quad prefix ops a lane-order chain. **SIMD prefix ops
   are a 32-lane Sklansky network**: at block size b = 1, 2, 4, 8, 16, every lane in the upper half of a 2b-block
   combines the last inclusive value of the lower half. Lane i receives lane i-1's inclusive value, and lane 0 the
   identity. The fp16 scans make the order visible: Sklansky fits every word, while a Kogge-Stone scan misses 66 and
   the previous model (quad tree then Kogge-Stone over quads) missed 10. The fp32 forms are also consistent with it
   (the simulator's 32-bit recordings all still pass, and one approximate fp32 test became exact).

All 122 retained cases (61 forms, all lanes active and with a quarter of the lanes inactive) match these rules on
every executing lane: 109,312 words.

## Why it matters for PTX

- `redux.sync` / `__reduce_*_sync` and shuffle-based reductions on 64-bit values (`u64`, `s64`, `f64`) need two
  32-bit operations with explicit carry / compare handling. Lowering them to one AGX reduction on a 64-bit register
  pair silently drops the high word.
- Half-precision warp reductions can use the 16-bit forms directly: fp16 rounding at each step with denormals kept,
  as CUDA's `__half` arithmetic does. The fp32 forms flush denormals, so they match CUDA fp32 only under `-ftz=true`.
- A bit-exact emulator or a reproducibility test for scans must use the Sklansky order. A different tree changes
  float results by 1-2 ulp.

## Reproduce

```sh
make verify-cross-lane-width     # offline, pure Python, < 1 s
```

Evidence: `results/2026-10-16-cross-lane-width/cases.json.gz` holds each lane's r6, r7 and hardware r14 / r15, plus
the encoded program, for the 122 cases. They are extracted from AGX-Performance-Simulator `coverage/expected/{alu,alu_masked}`,
recorded through the direct-DRM harness. The simulator implements the rules in `rust/src/fsem.rs` (`cross_lane`).
