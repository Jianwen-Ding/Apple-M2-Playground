# More than eight outstanding loads, and the shared unit as an int8 bottleneck: G14C — 2026-11-11

M2 Max (G14C), Asahi 6.19.14, ZLUDA's direct DRM path. Status: observed on one device, in real kernels (no dedicated
probe yet).

## 1. Sixteen asynchronous loads outstanding are correct and faster than eight

The AGX backend's `AGXInsertWaits` kept at most 8 requests outstanding (a `wait` before the 9th), a limit taken from
Mesa, never measured. With `-agx-max-pending=16` (llvm-project 2026-11-11) the double-buffered f16 / f32 tile GEMMs
of zluda_blas_agx (12 loads per K step: 4 A fragments as 2 x i16, 8 single i16 B^T elements) lose two of six waits
in the K loop.

- Correctness: 32 alpha/beta GEMM checks against a CPU reference (f16 and f32, 4 transpositions, shapes 512x4864x896,
  200x136x1000, 64x64x4100, 1000x1000x8): every max-relative-error and checksum bit-identical to the 8-request build.
- Speed (gemmbench, best of 40, two alternating rounds, us): 4864x512x896 f16 766 -> 745, f32 741 -> 728;
  896x512x4864 801 -> 788; 4096^3 21400 -> 20813 (f16), 20512 -> 20225 (f32); 1024^3 453 -> 435; 128x4096x4096
  876 -> 854.
- Not known: the real limit (if any) of outstanding requests per scoreboard slot. A probe with N independent loads
  into distinct registers before one wait, N = 8..64, checking every value, would settle it.

## 2. convert / bit-field / imad share one unit per half: int8 matrix code is bound by it

`2026-10-11-core-scaling` measured one unit per half for transcendentals, imad, bit-field ops (bfi, bfeil, extr,
asr, shlhi/shrhi), convert, floor and 64-bit add: a core rate of 1.0 instruction / cycle against 4.0 for the ALU.
Real-kernel confirmation (llama.cpp's MMQ, int8 mma emulated on the f32 matrix unit, Q5_1 module):

- Folding `sitofp(fptosi(x))` of the exact integer mma sums: converts 29.5k -> 15.2k (instructions only -4.8%),
  prompt processing +22-23%.
- s8 operands as `trunc i8` + `sitofp i8` (convert `s8_to_f` reads the low byte of either 16-bit half, so byte 2 needs
  no shift; bytes 1 and 3 one shift each) instead of shl/ashr pairs (a bfi and an asr): shared-unit ops 46.3k -> 35.2k,
  the s8 mma microbenchmark ~2x (k32 0.94 -> 1.86, k16 1.53 -> 2.68 Gmma/s), MMQ +1-3% on top.

Count `convert|bfi|bfeil|asr|imadd` (and 64-bit adds, ~4x the occupancy) against all instructions / 4 to see whether
a kernel is shared-unit bound.
