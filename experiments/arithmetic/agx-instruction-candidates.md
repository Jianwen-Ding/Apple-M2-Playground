# Small AGX integer instruction candidate set

**OFFLINE ONLY; G14C B1 hardware validity untested.** Six immediate-only edits,
not a shader binary or instruction-placement proof. The execution agent must
establish import/roundtrip and the actual register/control ABI before using them.
No GPU submission or vendor edit was performed here.

Reproducer/export (canonical script, scratch JSON):

```sh
make instruction-candidates  # Offline only; default r0/r1 templates
python3 -B scripts/agx_instruction_candidates.py \
  --output /scratch/apple-m2-playground/agx-instruction-candidates.json
```

JSON includes exact bytes, XOR, changed bits, baseline/modified decoder text and
fields, fixed host-oracle fixtures, placement constraints and source hashes.
`--dst-r32`/`--src-r32` select distinct registers 0..31; defaults below are r0/r1.
Reference roots are configurable through `APPLEGPU_ROOT`/`MESA_ROOT` or explicit
`--applegpu-root`/`--mesa-root`; relative/tilde paths are normalized and imported
modules must match the configured applegpu root. Only low registers are admitted
so moves remain 6 bytes. Arithmetic stays 8 bytes.

[Retained candidate JSON and provenance](../../results/2026-10-04-agx-instruction-candidates/README.md)
preserve the reviewed output; no result depends only on scratch.

| ID / baseline → modified decoder operands | Baseline bytes (little endian) | Modified bytes | Changed bits, LSB=0 |
| --- | --- | --- | --- |
| mov-small: `mov_imm r0, 1, 0b0` → `r0, 2, 0b0` | `620101000000` | `620102000000` | 16,17 |
| mov-bit0: `mov_imm r0, 305419896, 0b0` → `r0, 305419897, 0b0` | `620178563412` | `620179563412` | 16 |
| add-small: `iadd r0, r1, 1` → `r0, r1, 2` | `0e01421200000000` | `0e01422200000000` | 28,29 |
| add-split-immediate: `iadd r0, r1, 63` → `r0, r1, 64` | `0e0142f203000000` | `0e01420200010000` | 28–33,40 |
| mul-low-coefficient: `imadd r0, r1, 2, 0` → `r0, r1, 3, 0` | `1e01422200000000` | `1e01423200000000` | 28 |
| mad-addend: `imadd r0, r1, 2, 0` → `r0, r1, 2, 1` | `1e01422200000000` | `1e01422200010000` | 40 |

Software cross-check: local applegpu assembler/decoder
`4c5bae61086b8067231120c98b4756d7696d399c` agrees byte-for-byte with a separate
restricted transcription of Mesa's `agx_pack.c` bitfields and `agx_opcodes.py`
constants at `e5f0687867f5c5e88619175d9b0442f8560e8d53`. This is **one assembler
plus source-bitfield agreement**, not two independently built encoders. Source
hashes are exported; changing Mesa's inspected formulas requires review.

Mesa opcodes are 0x62/0x0e/0x1e; `imad` corresponds to applegpu `imadd`.
Register values in Mesa count 16-bit halves (r1=2). Destination fields begin
at bit 7; source short fields at 16+12*s. Move immediate occupies bits 16–47.
Immediate operands split low six bits and high two bits: iadd B uses 28–33
and 40–41; imadd B uses 28–33 and 56–57; C uses 40–45 and 54–55.
All candidates preserve zero shift, saturation/negation off, ordinary register
hints, source zero extension (Mesa `.abs=true`), destination width and kill=0.

Host oracle: mov returns the literal; add returns `(x+B) mod 2^32`; imadd
returns `(x*B+C) mod 2^32`, relevant to PTX mov/add/mul.lo/mad.lo.u32.
Exported inputs: 0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 0x12345678.
Known wrap fixtures: add 1→2 at x=0xffffffff gives 0→1; multiply 2→3 at
x=0x80000000 gives 0→0x80000000. These are mathematical expectations,
not emulator or hardware outputs. No mul.hi/64-bit/saturation claim is made.

Placement gate: locate a fully decoded matching baseline ALU instruction in
executable shader code, with full-byte equality and confirmed initialized source
register. Its destination must feed only checked output **data**, never addresses,
bounds, loops, masks or descriptors. Preserve allocation metadata, control flow,
waits, memory instructions, epilogue and container boundaries. Apply only the
exported XOR, then re-decode; equal size preserves later instruction offsets but
does not establish a compatible opaque-container ABI. Never globally search/replace
hex bytes. Baseline and one variation need guarded exact readback plus unchanged
controls before and after. Applegpu describes G13; only that hardware experiment
can promote these candidates to G14C observations.

Verification: all six byte/size/remainder/allowed-bit checks pass for r0/r1 and
r31/r30; known wrap fixtures and Python syntax pass. Next: execution agent selects
one actual compiled arithmetic site, binds its register/data ABI, imports unchanged
bytes as control, then tests one immediate variation with host readback oracle.
