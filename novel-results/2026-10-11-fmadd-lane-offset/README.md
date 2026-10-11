# fmadd has a 10-byte form with a lane-offset operand; ALU gap and constant bits mapped

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute.

## Claim

1. **Bit 53 of fmadd32 (0x3a) and fmadd16 (0x36) selects a 10-byte form.** applegpu and Mesa
   only know 6/8 bytes (bit 15). With bit 53 set, two more bytes (bits 64–79) belong to the
   instruction; the following code stays in sync only if it is skipped by 10 bytes.
2. **In that form, bits 75–79 are a lane offset k for source A.** Lane i reads A from lane i − k.
   B and C are read from the lane itself. k = 0 is a plain fma.
   * By default the shift stays inside 16-lane halves: lanes whose source would be below the
     start of their half (lanes 0..k−1 and 16..16+k−1) read A = 0. k ≥ 16 makes every A 0.
   * **Bit 68** lets the shift cross from lane 15 to lane 16 (32-lane shift). This read is only
     reliable when bit 68 is set *and* the source was written several instructions earlier:
     immediately after the write, lane 16 reads 0 even with bit 68; without bit 68 the result
     depends on the following code (0 when an ALU write follows, lane 15's value when a `wait`
     follows; deterministic over 8 repeats each).
   * **Bit 72** confines the shift to groups of 2 lanes, **bit 73** to groups of 4. Lanes whose
     source is outside the group read 0 (fmadd16) or an undefined value (fmadd32).
     Bit 74 set alone looked like the default 16-lane grouping, but lane 0 read an undefined value.
   * Bits 64–67 and 69–71 had no observable effect with k = 1 for any of A, B or C.
3. **Bit 52 of the 8-byte fmadd32 changes the operation** (fmadd16: no effect). Over 31 float
   triples on all lanes: if B = 1.0 the result is A; else if A = 1.0 the result is 1.0;
   otherwise the result is C exactly (C is not added in the first two cases; a zero C takes the
   sign of A). A register brute force found no source redirection that explains it, so the
   multiplier is not simply reading another register. Purpose unknown.
4. **All other applegpu gap bits tested are inert.** 210 of 213 single-bit flips over 53 instructions
   (integer, bitfield, shifts, bitop, float add/mul/fma, transcendental, compare-select,
   ballots, SIMD/quad shuffles and reductions, `wait` bits 9–15) changed nothing: no
   register, lane or length change and no fault.

5. **Constant-bit flips (93 single flips of applegpu's fixed bits beyond the opcode byte, `const1`).**
   60 inert, 26 turn into another known instruction, 2 switch mov_imm between its 16/32-bit forms,
   5 hang the GPU (recovered):
   * bfi / bfeil / extr / asr / shlhi / shrhi / asrh are one opcode (0x2e) with a 3-bit selector
     (bits 27, 26, 15) = 000 / 001 / 010 / 011 / 100 / 101 / 111. **Code 110 hangs.**
   * `bitop` bit 15 and `wait` bit 7 hang.
   * Ballot bit 48 switches between the SIMD and quad forms; `simd_shuffle` bit 15 makes it a `simd_op`.
   * `intl` bits 26 / 27 give bitrev / popcount of A (the iunop ops with a B operand present);
     bit 15 makes the encoding a `convert` whose mode comes from register A (see the sub-op finding).

## Relationship to existing knowledge

applegpu (`fmadd32`/`fmadd16`: sizes 6/8, length bit 15) and Mesa (`agx_opcodes.py:218`
`ffma (0x3A, 6, 8)`; `agx_pack.c` extend word in the top 16 bits) describe no 10-byte form and
no lane operand. Mesa's own 10-byte ALU form (icmpsel/fcmpsel) uses bytes 8–9 for register
extensions; for fmadd those bytes instead carry the lane offset (register extensions stay at
54–61, and bits 64–74 showed no register effect). Expected values were computed independently
from the preloaded per-lane registers (`D.pre(r) + 16·lane`) and Python float arithmetic.

## Use for the PTX backend

* A disassembler must treat bit 53 of fmadd32/fmadd16 as a second length bit.
* The lane-offset operand is a fused `shfl.up` + fma for one source:
  `__shfl_up_sync(v, k) * b + c` in one instruction, within 2, 4, 16 or (bit 68) 32 lanes,
  with out-of-range lanes reading 0 (fmadd16) instead of keeping their own value as PTX
  requires. Use it only for scans and stencils where 0 is the correct fill, and keep the source
  write at least 6 instructions before the read for 32-lane shifts.
* Never emit bit 52. A compiler gains nothing from the remaining gap bits; keep them zero.

## Reproduce / verify

* `make verify-alu-bitflip`: 50 offline checks of the retained records.
* Hardware: `CONFIRM_GPU_FAULTS=1 python3 -B scripts/run_drm_bitflip.py` (full gap sweep,
  ~4 min), then `scripts/analyze_bitflip.py <record.json>`. The fmadd experiments use the
  `--raw` / `--baseline` options (commands in the commit log of this finding).
* [Evidence](../../results/2026-10-11-alu-bitflip/README.md).

Not established: whether other ALU instructions have hidden 10-byte forms reached through
constant bits (only gap bits were flipped); the meaning of bit 74 and of bits 72+73 together;
whether the undefined values read by fmadd32 come from another register; what bit 52 is for.
