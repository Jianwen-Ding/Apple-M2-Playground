# ALU bit-flip runs — 2026-10-11

`scripts/run_drm_bitflip.py` (direct DRM, opcode-describe body with lane-varied preloads),
`scripts/analyze_bitflip.py` for classes, `scripts/verify_alu_bitflip.py` (50 offline checks).
Every file is a gzipped runner record (per-lane r0..r23 for both length layouts).

| File | Contents |
| --- | --- |
| `full1` | Every applegpu gap bit of 53 register-only instructions (213 flips, 534 submissions, 0 faults). Classes in `gap-bit-classes.json`. |
| `t1` | First pass (iadd, wait), used to find that r0h is uninitialized noise |
| `fma1`, `fma10` | fmadd32 bits 52/53 with tiny C; bytes 8–9 of the 10-byte form, one bit at a time |
| `fma-ext2` | Pass-through forms (result = C, B or A) with r34–r47 preloaded, bytes 8–9 single bits |
| `fma-lane`, `fma-lane-bc` | Lane offset k and bits 64–74 with k = 1; which source is shifted |
| `fma-hazard`, `fma-cross-rep` | Cross-half reads: write-to-read distance, layout dependence, 8 repeats |
| `fma-b52`, `fma-b52b`, `fma-b52c`, `fma-b52d` | Bit 52 (8-byte form) over register sets and 31 chosen float triples |
| `fma16-lane` | fmadd16 10-byte form |

Gap-bit result: 210 of 213 flips had no observable effect on any register, lane or the
instruction length. The other three are fmadd32 b52, fmadd32 b53 and fmadd16 b53; see the
[finding](../../novel-results/2026-10-11-fmadd-lane-offset/README.md).
"No observable effect" is for these inputs (32-bit register operands, finite values, all lanes
active): a bit could still matter for 64-bit or immediate operands or special values.
