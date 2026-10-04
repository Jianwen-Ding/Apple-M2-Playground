# First controlled AGX instruction patch — G14C B1

**Hardware observation:** changing bit 0 of the 32-bit immediate in an exported
six-byte AGX instruction changed every active uint32 output from `0x12345678`
to `0x12345679`. Counts 33 and 257 passed exact host readback with all guards,
padding and untouched tail intact. Unchanged imports immediately before and
after returned `0x12345678`. This confirms the locally decoded move-immediate
field's behavior in this shader on G14C B1; it is not discovery of a previously
unknown opcode or a claim about all AGX generations.

Reproduce the bounded combined suite:

```sh
python3 -B scripts/run_vulkan_compute.py --probe-mov
```

The [baseline report](../baseline/vulkan-binary-roundtrip.md) explains validation,
identity, buffer oracle, synchronization and bounds. The external
[patcher](../../scripts/patch_agx_shader.py) refuses any input except the pinned
control SHA256, verifies the wrapper and known instruction, and emits scratch
binaries plus versionable hex/JSON evidence. No compiler runs on the mutated
instruction and the import path has no SPIR-V fallback.

## Source/model hypothesis before hardware execution

The installed ICD reports Mesa 25.3.6; its SHA256 remains the baseline's exact
hash. The official [Mesa 25.3.6 release archive](https://archive.mesa3d.org/mesa-25.3.6.tar.xz)
was fetched into scratch: 43,485,532 bytes, SHA256
`59217efeac3b64e7ced958324b9db7494f1e0741aeb22d780276514cc1b8f206`.
Version-matched `src/vulkan/runtime/vk_shader.c` describes a 72-byte wrapper
with whole-blob SHA1 after zeroing the digest at bytes 48–67.
`src/asahi/vulkan/hk_shader.c` describes stage and shader metadata followed by
aligned uint32 code/data lengths and raw code/data. The measured constant blob
matches wrapper magic, driver ID 26, UUID, version 0, length 2572, and computed
SHA1. A single plausible terminal code/data length pair is at `0x8b4`:
336 code bytes and zero additional data bytes, starting code at `0x8bc`.

This upstream source is a **serialization hypothesis matched to actual bytes
and importer behavior**, not proof of the exact distribution build's source
or patches. No newer local checkout's ABI was substituted. We did not resolve
all metadata struct members or generalize a parser: the patcher pins the
complete input blob and preserves metadata byte for byte.

Local applegpu revision `4c5bae61086b8067231120c98b4756d7696d399c` is an
existing reverse-engineered G13 model. Its decoder hypothesized:

```text
code+0x80: get_sr r1.cache, sr80
code+0x84: iadd r1, r1.discard.sx, u4.sx
code+0x8c: mov_imm r0l, 0
code+0x90: if_icmp r0l, ult, r1, u5, 1
code+0x96: 620978563412  mov_imm r2, 305419896, 0b0
code+0x9c: iadd r1, 8, r1.sx
code+0xa4: device_store 0, i32, x, r2, u6_u7, r1, unsigned, 0
code+0xac: wait 0
code+0xae: pop_exec r0l, 1
code+0xb4: stop
```

Decode boundaries were walked from the observed main start `0x80`. Preamble
at `0x100` is preserved and separately disassembled. The initial whole-code
inspection also decoded leading constant data as instructions; those bytes
are **not executed main code** and those misleading decodes are not used as
instruction evidence. Main/preamble-only disassembly is the retained evidence.

## One justified field and observed result

The model's `MovImm32InstructionDesc` identifies immediate bits 16–47. Target
is blob offset `0x952`, six bytes long. Only immediate bit 0 was varied:

| Item | Before | After |
| --- | --- | --- |
| Instruction bytes | `620978563412` | `620979563412` |
| Decoded immediate | `0x12345678` | `0x12345679` |
| Destination/control fields | `Dt=2, D=4, kill=0` | unchanged |
| Opaque blob SHA256 | `b79bd25941bdea1a0095b219fe0333ac5c18822225de811c9308a38702e9e098` | `e1ea5f9ca2822860c244627acd8406faf7a1b87ffe175f88234e67646b7698bb` |
| Wrapper SHA1 | `ae0599204787fefb3bf5885b33bc84900a497ee9` | `6a99fa47793b712229b3f8e89c4e6b4e0bdf9e3d` |

Blob byte `0x954` changes from `0x78` to `0x79`; the only other changed bytes
are in the wrapper SHA1. Code length, all metadata, destination, execution
mask/control, register usage, load/store setup, constant data and preamble
remain identical. The patcher checks a one-bit instruction XOR (`1<<16`),
identical decoded non-immediate fields and unchanged instruction length.

| Bounded child | Shader import | Exact hardware readback |
| --- | --- | --- |
| Unchanged before, count 33 | VK_SUCCESS | 33 × `0x12345678`; all other words unchanged |
| Patched, count 33 | VK_SUCCESS | 33 × `0x12345679`; all other words unchanged |
| Same patched bytes, count 257 | VK_SUCCESS | 257 × `0x12345679`; all other words unchanged |
| Unchanged after, count 33 | VK_SUCCESS | 33 × `0x12345678`; all other words unchanged |
| Same instruction change, stale SHA1 | 1000482000 | No dispatch/readback; rejected at shader creation |

Each import uses a fresh child/device. Each successful queue submit and fence
wait returns VK_SUCCESS. A coherent allocation and explicit barriers precede
host readback. Counts cross workgroup boundaries and exercise masked excess
lanes. The stale-SHA control confirms integrity rejection; it does not prove
a general serialization ABI. The instruction's field interpretation has now
been supported by hardware in this exact context; other decoder labels remain
model hypotheses unless separately tested.

Exact control/patched/stale blobs as hex, their hashes, disassembly, source
excerpts and raw API/readback records are in the
[finding evidence](../../novel-results/2026-10-04-first-agx-instruction/README.md).
Binary executables and binary artifacts stay in scratch. There is no patch
path blocker at this milestone. The narrowly pinned patcher deliberately
rejects other blobs and driver/model hashes.

Next work, after coordinator review: vary another immediate bit or a bounded
integer-ALU operand in a separate one-field experiment, retaining the same
unchanged controls and exact oracle. Existing index code decodes `imadd` then
`xor`; that is a candidate, not a proven ALU finding. Expand register/operand
coverage before attempting arbitrary instructions or special registers. No
random opcode/SR fuzzing, vendor edits, commits, pushes or subagents occurred.
