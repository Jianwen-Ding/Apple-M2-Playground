# B47: shift amounts 32 to 255 in `bfi`, `bfeil`, `extr` and `asr` (2026-10-21)

Blocker B47 of `AGX-Performance-Simulator/tasks/ptx-re-blockers.md`. M2 Max (G14C), direct DRM (`record_suite.run`),
battery power. 0 faults; hang budget unchanged.

**Result: pass. Every form takes the low 7 bits of a register shift amount (bits 7 and up are ignored), exactly as the
simulator and applegpu's G13 notes model it.** For s mod 128 >= 32, `bfi 0, x, s` and `bfeil 0, x, s` give 0 (and
return the base operand unchanged when it is not 0), `extr lo, hi, s` gives `((hi:lo) >> s)` up to 63 and 0 from 64,
and `asr x, s` fills with the sign bit from 32 on. The backend's 64-bit variable shifts need no masking.

Probe (`b47.py sim|gpu`): one 256-thread workgroup; lane i runs `op r2, ..., r1` with r1 = i, so every amount 0..255
is tested once per case. Values 0x80000001, 0xffffffff, 0x12345678; `extr` with hi = 0x9abcdef0; `bfi` / `bfeil`
with base 0 and 0x0f0f0f0f. The oracle in `b47.py` applies B47's formulas to the amount modulo 128, 64 and 32.

| Case (each value) | mod 128 | mod 64 | mod 32 |
| --- | --- | --- | --- |
| bfi base 0 / base 0x0f0f0f0f | 256 / 256 | 192-198 | 64-82 |
| bfeil base 0 / base 0x0f0f0f0f | 256 / 256 | 192-198 | 64-82 |
| extr | 256 | 128 | 64 |
| asr (0xffffffff fits every model) | 256 | 194-198 | 70-82 |

`gpu.json` and `sim.json` hold every result word; they are identical (18 cases x 256 amounts). Together with the 70
recorded bitfield coverage cases (`scripts/bitfield_question.py`: all match the 7-bit model), this closes B47.
