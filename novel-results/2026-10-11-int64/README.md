# 64-bit integer add/sub/multiply-add and 64-bit pointer arithmetic are exact

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute stage.
Only assembler-round-tripped forms that Mesa emits were used.

## Claim and scope

With a 64-bit destination register pair, over 446 input sets each (14 edge words in all
pairings plus 250 random sets), every lane matched the host model exactly:

| Form | Result |
| --- | --- |
| `iadd r2_r3, r6_r7, r8_r9` / `isub` | 64-bit add / subtract with full carry and borrow |
| `iadd r2_r3, r6, r8` | 32-bit sources **zero-extended** (Mesa `abs` set) |
| `iadd r2_r3, r6.sx, r8.sx` | 32-bit sources **sign-extended** (Mesa default, `abs` clear) |
| `iadd r2_r3, r6_r7, r8[.sx], lsl s` | 64-bit + (extended 32-bit << s), s = 2 and 4 tested |
| `imadd r2_r3, r6[.sx], r7[.sx], r8_r9` | full 32×32→64 product (unsigned or signed) plus 64-bit addend |
| `imadd r2_r3, r6[.sx], r7[.sx], 0` | 32×32→64 multiply; the high word is PTX `mul.hi` |

64-bit pointers built in registers work as `device_load` bases:

* Uniforms are 32-bit: **u8 is the low and u9 the high word** of the 64-bit table address
  (checked without any memory access before dereferencing).
* `iadd r14_r15, r12_r13, r1, lsl 2` then `device_load …, r14_r15, 0` loads element `lane`.
* A register base with an element-scaled index register (`r12_r13, r1`) loads element `lane`.
* A negative sign-extended offset (`base + 1024 + sx(lane − 64) << 2`) loads element `192 + lane`.

Not established: 64-bit shifts, multiplies of two 64-bit values, 64-bit compares and
`icmpsel`, and conversions (Mesa lowers all of these to 32-bit sequences); shifts 1 and 3;
carry from the address low word into the high word inside a load (the BO does not straddle
a 4 GiB boundary).

## Reproducer and evidence

`make test-int64` (hardware), `make verify-int64` (offline, 0 failures).
Runners: `scripts/run_drm_int64.py`, `scripts/run_drm_pointer.py`.
[Evidence](../../results/2026-10-11-int64/README.md).

## Relationship to existing knowledge

Mesa keeps exactly `iadd64` and `imul_2x32_64` native (`agx_compile.h` `lower_int64_options`)
and maps unsigned operands to the `abs` source bit (`agx_compile.c` umul_2x32_64). Neither
Mesa nor applegpu documents a hardware test of the 64-bit forms or the extension rule;
both are measured here.

## Compiler implications (PTX)

* `add/sub.s64/.u64` are one instruction; `cvt.u64.u32`/`cvt.s64.s32` fold into the source
  extension bit for free.
* `mul.wide.u32/.s32` and `mad.wide` are one `imadd`; `mul.hi.u32/.s32` is its high word.
* Address computation `base + (idx << k)` for k ≤ 4 is one `iadd`, and the load can take
  the 64-bit register base directly; `ld.global [r + imm]` needs the immediate folded into
  the add.
* `mul.lo.u64`, 64-bit shifts and 64-bit compares need multi-instruction sequences, as in
  Mesa's `nir_lower_int64`.
