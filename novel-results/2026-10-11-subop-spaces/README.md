# ALU sub-op spaces fully mapped: funop, iunop, simd_op, shuffles, convert, conditions, bitop

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute.

## Claim

**funop (opcode 0x0a, op bits 28–33).** The 6-bit op is a 4-bit function (bits 28–31) and a
2-bit rounding mode (bits 32–33) that only function 0 uses (floor / ceil / trunc / round-even).
* Functions 0, 1 (srsqrt), 4 (dfdx), 6 (dfdy), 8 (rcp), 9 (rsqrt), 10 (sin_pt_1), 12 (log2),
  13 (exp2), 14 (sin_pt_2) run. For all but 0, bits 32–33 are ignored: the 27 unnamed values
  `xx0001`, `xx0100`, … are bit-identical aliases.
* **Functions 2, 3, 5, 7, 11, 15 (any rounding bits, 24 encodings) hang the GPU** (~502 ms
  firmware timeout, recovered; the kernel log shows the asahi "GPU timeout" recovery).
* Constant bits 34–41 are ignored.
* dfdx / dfdy work in compute shaders: exact `x[lane|1] − x[lane&~1]` and `x[lane|2] − x[lane&~2]`.

**iunop (0x3e with bits 28–37 zero).** op2 (bits 26–27): **00 = Morton bit spread** (bit i of the
low 16 bits → bit 2i; unnamed in applegpu and Mesa), 01 bitrev, 10 popcount, 11 index of the highest
set bit (applegpu/Mesa call it `ffs`). op1 (bits 38–39) and bits 28–37 are ignored.

**simd_op (0x6f, bit 15 = 1).** Mesa's 5-bit op (bit 28, bits 38–40, bit 47) × kind (bits 29–30:
quad reduce, simd reduce, quad exclusive prefix, simd exclusive prefix). All 128 combinations run.
* bit 0 = float: bits 1–2 = fadd, fmul, fmin, fmax (bits 3–4 ignored).
* integer, bit 4 = 0: bits 1–2 = and, or, xor, and; but `x0110` in the prefix kinds returns 0.
* integer, bit 4 = 1: bit 2 = 0 → iadd (bit 1 = 0) or or (bit 1 = 1); bit 2 = 1 → min/max
  (bit 1), signed/unsigned (bit 3).
* Exclusive prefix identities: 0 for add/or/xor, all-ones for and, 1.0 for fmul,
  **NaN for fmin/fmax** (not ±inf).
* The other op2 bits (26, 27, 31–37, 41) are ignored.

**Shuffles (0x6f, bit 15 = 0, bit 27 = 0).** op2 (bits 38–39) × window (bit 26: quad / simd) ×
op1 (bit 47):
* op1 = 0: shuffle, xor, up, down (Mesa). Up/down out-of-range lanes keep their own value.
* op1 = 1, op2 = 2: rotate up (applegpu). op2 = 3: quad = down, simd = reads (i + B) & ~3.
  op2 = 0, 1: rotate-like up/down with some lanes undefined; not usable.
* **Bit 27 set is not a shuffle**: the encoding becomes the 8-byte `simd_matrix_fmadd16` /
  `simd_matrix_fmadd32` (applegpu), which swallows the next two bytes.
* Quad-divergent shuffle indices: the low two index bits are ORed over the quad (as Mesa's
  `agx_lower_divergent_shuffle.c` describes); measured here on two index patterns.

**convert (0x3e, bit 15 = 1).** What applegpu/Mesa call the 2-bit `round` field (bits 26–27) is
a **direction** bit plus a hang bit: bit 26 = 0 float→int, 1 int→float; bit 27 set (values 2, 3)
**hangs the GPU**. The 6-bit mode (bits 16–21): bit 0 signed, bit 1 rounding (0 toward zero,
1 nearest-even), bits 2–3 width, bits 4–5 ignored. Model check: 7,864 lane results, 0 mismatches.
* Widths 8 / 16 / 32 saturate float→int; signed 8/16-bit results are **not sign-extended**
  (−8 → 0xf8). Int→float reads the low 8/16/32 bits, signed per bit 0, rounding per bit 1.
* **Width code 3** (modes 12–15) is a non-saturating float→int (signed results wrap; with the
  rounding bit it rounds half up, not to even). Its unsigned form of a negative x returns
  2^(e+9) − |x| (e = exponent), and |x| ≥ 2^31 gives an unsaturated, unmodelled pattern. In the
  int→float direction it reads 32 bits, and the "signed" form returns −(unsigned value) when bit 31 is set.
* Mesa's names line up as: F_TO_U16 = 4 means f→u16 *toward zero* (with bit 26 = 0), U16_TO_F = 6
  means u16→f *nearest* (with bit 26 = 1); 2/3, 6 (f→), 12–15 and every value ≥ 16 are unnamed.
* Bits 22–25 are the operand type of the mode slot: **bit 22 or 23 = mode read from a
  register** (the 6-bit field is then the half-register index), **bit 24 = from a uniform
  register**. Conversion mode can therefore differ per lane. Bits 38–39 and 42–43 are ignored.

**Condition codes.** icmpsel / fcmpsel (cc bits 61–63) and icmp/fcmp ballots (cc 61–63, invert
bit 47): the unnamed **icond 3 and 7 and fcond 4 are "never"**; with the invert bit they are
"always", so `icmp_ballot` with cc = 3 and invert = 1 returns the active-lane mask in one
instruction. The other codes match Mesa (ltn/gtn equal lt/gt for the non-NaN inputs used).

**bitop truth tables (bits 26, 27, 38, 39).** With truth-table index (b << 1) | a, 14 of 16 tables
compute f(a, b) bitwise. The two B-only tables (0011 = ¬b, 1100 = b) return **A unchanged**
(applegpu's `bitop_mov_a`): there is no single-bitop ¬b or b.

## Relationship to existing knowledge

Mesa `agx_opcodes.py` / `agx_compiler.h` name 13 funop values, 3 iunop values, 12 simd_op values, 8 shuffles and 10 convert modes;
applegpu adds rotate-up. This sweep accounts for every value of those fields: the hangs, the
aliases, the Morton spread, the 128-entry simd_op structure and NaN prefix identities are new here.
Expected values come from Python models of each operation applied to the per-lane inputs read
back from the same dispatch.

## Compiler implications

* PTX `brev`, `popc`, `bfind` map to iunop 01/10/11; iunop 00 gives a one-instruction Morton
  spread for 2D tiling.
* Never emit funop functions 2/3/5/7/11/15: they hang the GPU.
* `__shfl_*_sync` with lane-divergent indices must use Mesa's quad-uniform lowering.
* `__reduce_*_sync` and warp scans map directly onto simd_op; seed exclusive fmin/fmax scans
  explicitly (lane 0 gets NaN).

Reproduce: commands in [the evidence README](../../results/2026-10-11-subop-spaces/README.md);
verify offline with `make verify-subop-spaces`.
