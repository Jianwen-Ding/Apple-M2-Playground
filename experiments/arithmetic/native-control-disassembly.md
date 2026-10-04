# Native control instruction review — 2026-10-04

Subsequent execution: the formerly proposed index addend edit now has a separate
[passing hardware report](imadd-addend.md). The original review below remains
an offline record of the pre-execution hypothesis.

**Independent offline placement review; this review did not execute modified
instructions.** The separate [move experiment](first-agx-instruction.md) now
has hardware evidence; the index imadd proposal below remains unexecuted. No GPU work,
vendor edits, shared-file edits, commits or pushes were performed in this review.

Reviewed current `tests/vulkan_compute.c`, `scripts/run_vulkan_compute.py` and
`scripts/agx_instruction_candidates.py` plus the execution owner's retained run:
`/scratch/apple-m2-playground/vulkan-compute-runs/20261004T214520738226Z/`.
Read the workspace/probe ownership instructions and repo methodology first.
This report is the sole versioned file owned by this review.

## Exact sites and predicted output

Both binaries are 2,572 bytes; the 336-byte native payload starts at container
`0x8bc`. Main entry is native `0x80`, preamble entry `0x100`.

| Control / proposed single field edit | Native instruction offset / container offset | Exact instruction bytes before → after | Prediction |
| --- | --- | --- | --- |
| Constant: `mov_imm r2, 0x12345678, kill=0` → immediate `0x12345679` | `0x96` / `0x952`; change byte `0x954`, `78→79` | `620978563412` → `620979563412` | Every active output word equals `0x12345679` |
| Index: `imadd r2.cache, r1.cache.sx, u8.sx, 0` → addend `1` | `0x96` / `0x952`; change byte `0x957`, `00→01` | `9e09820659000000` → `9e09820659010000` | `(((i * 0x9e3779b9) + 1) mod 2^32) XOR 0x12345678` |

These are instruction-relative bit 16 and bit 40 respectively. Each preserves
length, destination, operand classes, cache hints, sign-extension, shift,
saturation and negation. Neither proposal changes addresses, bounds or control.
The second is a separate future variation, not part of the preferred move test.

Pinned container SHA256:

- Constant: `b79bd25941bdea1a0095b219fe0333ac5c18822225de811c9308a38702e9e098`
- Index: `d0b99dace1de6eb2467c64ce872e8f5c02458d1edae0a3f74b9ed2c17cff0ba3`

The current candidate script provides generic templates, not these offsets.
Its default `mov-bit0` destination is r0; this real shader uses r2. Its generic
imadd uses ordinary zero-extended registers, whereas this site has cached,
sign-extended register/uniform operands. Use exact baseline equality and decoded
fields above rather than substituting a whole generic instruction.

## Register flow and safety argument (software/source interpretation)

Both mains start with `get_sr r1.cache, sr80` at `0x80`, then
`iadd r1, r1.discard.sx, u4.sx` at `0x84`. Mesa/applegpu interpret this as grid
index plus dispatch base. At `0x8c` r0l becomes zero; `if_icmp` at `0x90` checks
unsigned `r1 < u5` and establishes the store's execution mask.

Constant main: the move at `0x96` defines r2. At `0x9c`,
`iadd r1, 8, r1.sx` computes the output element index. At `0xa4`,
`device_store 0, i32, x, r2, u6_u7, r1, unsigned, 0` consumes r2 solely as
store data; r1 is the element offset and u6_u7 the base address. Then wait at
`0xac`, pop_exec at `0xae`, stop at `0xb4`. No later instruction consumes r2
as an address, bound, descriptor or execution mask.

Index main: imadd at `0x96` defines r2, XOR at `0x9e` updates r2 with u9.
Address add is `0xa4`; store is `0xac`; wait/pop/stop are `0xb4/0xb6/0xbc`.
Changing only immediate C leaves r1 and u6_u7 unchanged. Sign extension of the
32-bit multiplicands does not affect the low 32 product bits, so the host
modulo oracle remains valid. Predicted modified values include i=0:
`305419897`, i=1: `2349019074`, i=32: `3571147097`, i=256: `625864569`.
These are predictions, not observed modified readbacks.

## Executable code versus constants, preamble and metadata

Mesa 25.3.6 was read from the pinned archive
`https://archive.mesa3d.org/mesa-25.3.6.tar.xz`, SHA256
`59217efeac3b64e7ced958324b9db7494f1e0741aeb22d780276514cc1b8f206`.
Reviewed members were extracted into this review's scratch directory; existing
owner snapshots of compile/header/serialization/blob sources matched archive
members byte-for-byte. This verifies release-source provenance, not independent
reconstruction of the installed driver build.

`agx_compile.c:33,3552–3560` places rodata before the aligned main (`0x80`
alignment). `agx_compile.h` explicitly separates main/preamble offsets and
rodata's half-uniform mapping. The constant payload starts with `78563412`;
the index payload starts with `b979379e78563412`. These are rodata, not main
instructions. A disassembler starting at zero fails on the constant and prints
a misleading threadgroup-store for the index. Do not use that apparent opcode.
Constant rodata maps two halfwords to half-uniform 16 (u8); the index maps four
halfwords there (u8 multiplier, u9 XOR literal). Editing those bytes would test
constant delivery rather than an immediate instruction field.

Preamble native `0x100..0x14f` loads root/descriptor data and stores uniforms;
stop is `0x13e`, followed by trap padding. It is executable, distinct from main
and from serialized metadata. Leave it unchanged. Main metadata sizes are 70
bytes constant / 78 bytes index, including trap padding after stop. A bounded
walk from main through those sizes reaches `0xc6` / `0xce` exactly.

`hk_shader.c:1673–1695` serializes stage, hk info, agx info, aligned u32 code/data
lengths, then native/data bytes. `blob.c` aligns scalar lengths; byte copies
insert no alignment. On these controls the stage byte is at `0x48` (value 5), hk metadata
starts `0x49`, agx metadata starts `0x419`, and lengths `(336,0)` are at `0x8b4`.
The hk-info span (976 bytes) and total agx-info span are measured containment
facts, not independently built full C ABI sizes. Independently deriving the
agx prefix from `VARYING_SLOT_MAX=64`, four-byte coefficient bindings and C
alignment locates main_size/has_preamble/preamble_offset/main_offset at
agx-relative `1060/1064/1068/1072`; each matches these blobs. The rodata tuple
at relative `1120` agrees with the source mapping and payload contents.
Do not generalize these offsets to other stages or driver builds.

The wrapper in `vk_shader.c:223–358` is 72 bytes. SHA1 lives at `[48:68)`;
validation hashes the entire container with those 20 bytes zeroed. Preserve
magic, driver ID, UUID, version, size, padding, all metadata and payload bytes
except the one approved instruction byte; recompute only wrapper SHA1.
An instruction edit with stale SHA1 is expected to fail import before dispatch.
Recomputed integrity establishes container validity, not instruction safety.

## Independent cross-check and retained hardware evidence

Mesa `agx_pack.c:284–326,420–543` and `agx_opcodes.py:223–225` independently
explain the exact bytes. For the move, opcode=0x62; destination half-register
value=4 (r2), packed D=`2|(4<<2)`; immediate occupies bits 16–47. The six-byte
result is exactly `620978563412`; toggling immediate bit 0 gives the proposal.
For imad, opcode=0x1e, cached D=`1|2|(4<<2)`, cached r1.sx A=`0x682`, uniform
u8.sx B=`0x590`, immediate C=0. Source fields start at 16/28/40; changing C to
1 gives `9e09820659010000`. Shift and extension fields stay zero. This is an
independent restricted source transcription, not a separately built Mesa encoder.
Applegpu decoded both variants with zero unknown remainder and reassembled the
modified texts byte-for-byte. Applegpu's G13 model agreement alone is not G14C
hardware confirmation.

Read-only review rederived all **1,376 words across 11 retained readbacks**:
source constant/index at count33, unchanged imports at counts1/32/33/257, and
count33 no-dispatch. Every active value, eight leading guards, rounded inactive
lanes, eight trailing guards and 16 control words matched. Both original
container SHA1s, pinned SHA256s and complete native containment matched.
These retained successful readbacks are existing hardware evidence for delivery
and unchanged controls; this review did not rerun them or observe patched bytes.

[Selected independent review JSON](../../results/2026-10-04-vulkan-binary-roundtrip/integration-review/native-control-review.json)
now preserves decoded instructions, source hashes, predicted values and original
unchanged-control checks in Git. Historical scratch reproducer:

```sh
python3 -B /scratch/apple-m2-playground/native-control-review/review.py
```

Output is `review.json` with source hashes, full main decoding, fields, exact
patch locations, predicted values and per-readback checks. It writes no shader
binary and performs no driver calls. Scratch is regenerable, not canonical.
One initial extraction requested generated `util/shader_stats.h`, absent in the
release archive; extraction stopped and was corrected to actual source members.
No GPU failure/reset was induced. No unbounded decode or arbitrary opcode scan
was used.

## Coordinator handoff

The completed move experiment satisfies the initial delivery/one-field control;
future variations should independently parse/check entry metadata, enforce pinned
full input hash, decode the main boundary and require full target-byte equality.
First run unchanged import/control, then only the constant immediate bit edit
with refreshed SHA1 at count33, checking **all** words against `0x12345679` plus
unchanged guards/padding/control. A stale-integrity import is a useful bounded
negative gate. Follow with unchanged import/control; stop on any fault, timeout,
identity mismatch or unexpected word. Counts1/32/257 are useful subsequent
coverage. Preserve exact input/output hashes and execution environment before
promoting additional native semantics. Index C=1 remains a separate bounded
follow-up proposal with no modified-readback observation in this report.
