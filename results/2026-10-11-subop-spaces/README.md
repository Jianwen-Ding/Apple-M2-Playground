# Sub-op space sweeps — 2026-10-11

`scripts/run_drm_bitflip.py --sweep/--masks/--prefix` on the direct DRM path; identification
by `scripts/identify_funop.py`, `scripts/identify_simd_op.py`, `scripts/identify_shuffle.py`;
offline checks `scripts/verify_subop_spaces.py` (16 checks, `make verify-subop-spaces`).

| File | Baseline / inputs | Encodings |
| --- | --- | --- |
| `funop2`, `funop3` | `floor r5, r6`, r6 = 0.37·lane − 3.3 | op bits 28–33 (all 64), single bits 34–41. 24 GPU timeouts (recovered, control passed after each) |
| `iunop` | `bitrev r5, r6`, r6 = preload | op2 × op1 (16), single bits 28–37 |
| `simdop-ints`, `simdop-flts` | `simd_iadd r5, r6`, r6 = hashed ints / (lane−10)·0.37 | 5-bit Mesa simd_op × 4 kinds (128 each) |
| `shuf-uni`, `shuf-perm24`, `shuf-perm13` | `quad_shuffle r5, r6, r7l`, A = lane id, B = 3 / (7·lane+3)&31 / (13·lane+6)&31 | op1 × op2 × op3 (32) |
