# Mesa `fuse_ubfe` is unsound for variable shifts on AGX (verdict A, hardware-decided)

Status: decided on hardware 2026-10-12 (M2 Max G14C, Asahi `asahi-verify`), evidence retained in
AGX-Performance-Simulator `results/2026-10-12-asahi-verify/` (`bitfield-question.txt`, report §Q1).
No new GPU work in this note; it records the verdict as a novel discovery.
**Not reported upstream: the owner explicitly deferred the upstream report, and it must not be
filed by an AI.**

## The question

Mesa's `agx_nir_algebraic.py` rule `fuse_ubfe` turns `(x >> s) & mask` into `ubitfield_extract`,
emitted as AGX `bfeil` with an immediate mask and the *unmasked* shift `s`. NIR drops a preceding
`& 31` first (`ushr` is modulo-32 by definition), so `s` can be a variable holding 32-63. That
fusion is only correct if masked-`bfeil` takes its shift modulo 32. Nothing recorded showed it.

## The hardware verdict: A (7 bits, like the full-width form)

70 recorded bitfield cases (`bfi` / `bfeil` / `extr` / `shlhi` / `shrhi`, immediate shifts 0-127,
masks `0x1` to `0x7FFFFFFF`), run against both semantics (`scripts/bitfield_question.py`):

- Full-width and unmasked forms: shift taken modulo 32 under both hypotheses (66/70 agree).
- **All 4 masked forms fail the modulo-32 reading** (`bfeil_r14_r6_r7_r8` with masks `0x1`,
  `0xFF`, `0xFFFF`, `0x7FFFFFFF`): a masked `bfeil` takes 7 shift bits, so shifts of 32+
  extract bit 0 (zero) instead of wrapping.

## Consequences (all measured, same root cause)

- `viterbi`: states 32-63 read 0, ~30% of bits wrong; `viterbifix` (explicit masked
  `bitfieldExtract`, which the compiler keeps) passes and is the workaround.
- `shiftfuse` (3 of 10 columns), `lz4dec`, `bitap`, `cdc`: fail on hardware, pass in the
  simulator only under the refuted hypothesis B. The simulator keeps hypothesis A (7-bit)
  as the default; `AGX_BFEIL_MASKED_SHIFT32=1` remains available for what-if runs.
- Ordinary code that triggers it: `(w >> ((i & 3) * 8)) & 255` (byte extract), `& 3` variants —
  the driver is conformant, so this is a miscompile of valid shaders, not a spec edge.

## Suggested upstream report (deferred, do not file)

Against Mesa (`agx_nir_algebraic.py`, `fuse_ubfe`): restrict the fusion to constant shifts
(`'#b`), or emit `ubitfield_extract(a, iand(b, 31), bits)`. Include note 37's root cause
(`tasks/spirv-08-applications.md` in AGX-Performance-Simulator), the `viterbifix` workaround,
and the `bitfield-question.txt` verdict. This is outward-facing and needs the owner's explicit
go-ahead; an AI must not file it.

## Reproduce / verify

`make verify-bfeil-verdict` (offline: checks the retained verdict file — all 4 masked cases fail
modulo-32 and pass 7-bit — plus the `asahi-verify` report line; needs the AGX-Performance-Simulator
checkout next to this repo).
